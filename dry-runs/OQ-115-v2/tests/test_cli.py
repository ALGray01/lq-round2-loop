import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from router import cli


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "cap_state.json"
        # Isolate CLI runs from the repo's real router/cap_state.json.
        self.patcher = patch("router.cap_tracker.DEFAULT_STATE_PATH", self.state_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmpdir.cleanup()

    def run_cli(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(argv)
        return code, buf.getvalue()

    def test_missing_model_registry_is_a_clean_cli_error_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_path = Path(tmp) / "does_not_exist.json"
            with patch("router.models.DEFAULT_REGISTRY_PATH", missing_path):
                code, _ = self.run_cli(["route", "--text", "x", "--stakes", "low"])
                self.assertEqual(code, 1)

    def test_route_command_outputs_valid_json(self):
        code, out = self.run_cli(["route", "--text", "Draft an NDA for a vendor", "--stakes", "medium"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIn("chosen_model", payload)
        self.assertEqual(payload["task_type"], "transactional_drafting")

    def test_invalid_task_type_is_a_clean_cli_error_not_a_traceback(self):
        with self.assertRaises(SystemExit) as ctx:
            self.run_cli(["route", "--text", "x", "--stakes", "low", "--task-type", "not_a_real_type"])
        self.assertEqual(ctx.exception.code, 2)

    def test_negative_tokens_is_a_clean_cli_error_not_silent_corruption(self):
        with self.assertRaises(SystemExit) as ctx:
            self.run_cli(["record-usage", "--model", "claude-haiku", "--tokens", "-500"])
        self.assertEqual(ctx.exception.code, 2)

    def test_record_usage_then_stats_round_trip(self):
        code, _ = self.run_cli(["record-usage", "--model", "claude-haiku", "--tokens", "1234"])
        self.assertEqual(code, 0)

        code, out = self.run_cli(["stats"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["claude-haiku"]["used"], 1234)

    def test_stats_surfaces_usage_recorded_under_an_unregistered_model_id(self):
        # Regression: round-2 attacker found that usage recorded under a
        # typo'd/unregistered model id persisted correctly but never showed
        # up in `stats`, which used to only iterate tracker.caps.
        code, _ = self.run_cli(["record-usage", "--model", "claude-0pus-typo", "--tokens", "500000"])
        self.assertEqual(code, 0)

        code, out = self.run_cli(["stats"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIn("claude-0pus-typo", payload)
        self.assertEqual(payload["claude-0pus-typo"]["used"], 500000)


if __name__ == "__main__":
    unittest.main()
