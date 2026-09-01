import json
import unittest
from unittest import mock

from router.backends import AnthropicBackend, BackendError, MockBackend, get_backend


class TestMockBackend(unittest.TestCase):
    def test_response_is_labeled_mock_and_matches_task_type(self):
        backend = MockBackend()
        text, tokens = backend.complete(
            "task_type=citation_check. stakes=low.", "check this cite", "some-model"
        )
        self.assertIn("[MOCK:some-model]", text)
        self.assertIn("Citation check", text)
        self.assertGreater(tokens, 0)

    def test_critic_prompt_gets_critic_template(self):
        backend = MockBackend()
        text, _ = backend.complete(
            "You are a legal verification reviewer for task_type=litigation_reasoning",
            "draft text",
            "some-model",
        )
        self.assertIn("Verification review", text)


class TestGetBackend(unittest.TestCase):
    def test_no_api_key_returns_mock(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsInstance(get_backend("anthropic"), MockBackend)

    def test_non_anthropic_provider_always_mock(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "x"}, clear=False):
            self.assertIsInstance(get_backend("openai"), MockBackend)


class TestAnthropicBackend(unittest.TestCase):
    def test_missing_key_raises(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(BackendError):
                AnthropicBackend()

    def test_complete_parses_response_with_network_mocked(self):
        # No real API key was available in this build environment, so this
        # test exercises AnthropicBackend's request/response handling with
        # the actual network call monkeypatched -- it proves the parsing
        # logic works, NOT that the live API was called. See README.
        fake_response_body = json.dumps(
            {
                "content": [{"type": "text", "text": "hello from claude"}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        ).encode("utf-8")

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return fake_response_body

        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake-key"}):
            backend = AnthropicBackend()
            with mock.patch("urllib.request.urlopen", return_value=FakeResp()):
                text, tokens = backend.complete("system", "user", "claude-sonnet-5")
        self.assertEqual(text, "hello from claude")
        self.assertEqual(tokens, 15)


if __name__ == "__main__":
    unittest.main()
