import tempfile
import unittest
from pathlib import Path

from router.router import Router
from router.taxonomy import TaskType


class TestRouterEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "cap_state.json"
        self.router = Router(cap_state_path=self.state_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_explicit_task_type_override_bypasses_classifier(self):
        result = self.router.route(
            text="some ambiguous text that wouldn't obviously classify",
            stakes="high",
            task_type="citation_checking",
        )
        self.assertEqual(result.decision.task_type, TaskType.CITATION_CHECKING)
        self.assertEqual(result.classification.confidence, 1.0)

    def test_to_dict_is_json_serializable(self):
        import json
        result = self.router.route(text="Draft an NDA for a vendor", stakes="medium")
        json.dumps(result.to_dict())  # raises if not serializable

    def test_record_usage_affects_subsequent_routing(self):
        # Push claude-sonnet over its cap, then confirm a medium-stakes drafting
        # request (which would normally pick it) routes elsewhere instead.
        before = self.router.route(text="Draft an NDA for a vendor", stakes="medium")
        self.assertEqual(before.decision.chosen_model_id, "claude-sonnet")

        self.router.record_usage("claude-sonnet", 8_000_000)
        after = self.router.route(text="Draft an NDA for a vendor", stakes="medium")
        self.assertNotEqual(after.decision.chosen_model_id, "claude-sonnet")
        self.assertTrue(after.decision.warnings)


if __name__ == "__main__":
    unittest.main()
