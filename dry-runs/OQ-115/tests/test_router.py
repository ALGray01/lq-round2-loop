import tempfile
import unittest
from pathlib import Path

from router.lanes import load_config
from router.router import route_request


class TestRouteRequestIntegration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "lanes_state.json"
        self.log_path = Path(self.tmpdir.name) / "routing_log.jsonl"
        self.config = load_config()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_low_stakes_citation_check_routes_fast_no_verification(self):
        decision = route_request(
            "Please verify the citation: 410 U.S. 113 (1973), Bluebook format.",
            config=self.config,
            state={},
            state_path=self.state_path,
            log_path=self.log_path,
        )
        self.assertEqual(decision.classification.task_type, "citation_check")
        self.assertEqual(decision.tier_decision.tier, "fast")
        self.assertIsNone(decision.verification)
        self.assertTrue(self.log_path.exists())
        self.assertTrue(self.state_path.exists())

    def test_high_stakes_litigation_escalates_and_verifies(self):
        decision = route_request(
            "Final version of the motion to dismiss argument, to be filed "
            "with the court tomorrow.",
            config=self.config,
            state={},
            state_path=self.state_path,
            log_path=self.log_path,
        )
        self.assertEqual(decision.classification.task_type, "litigation_reasoning")
        self.assertEqual(decision.classification.stakes, "high")
        self.assertEqual(decision.tier_decision.tier, "frontier")
        self.assertIsNotNone(decision.verification)
        self.assertIn("passed", decision.verification)

    def test_log_file_has_one_line_per_call(self):
        route_request("Draft an NDA.", config=self.config, state={}, state_path=self.state_path, log_path=self.log_path)
        route_request("Research the standard for X.", config=self.config, state={}, state_path=self.state_path, log_path=self.log_path)
        lines = self.log_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)

    def test_state_persists_and_accumulates_across_calls(self):
        route_request("Draft an NDA.", config=self.config, state={}, state_path=self.state_path, log_path=self.log_path)
        import json
        state1 = json.loads(self.state_path.read_text(encoding="utf-8"))
        route_request("Draft another NDA.", config=self.config, state_path=self.state_path, log_path=self.log_path)
        state2 = json.loads(self.state_path.read_text(encoding="utf-8"))
        def total(state):
            return sum(
                tier_entry["used_tokens"]
                for lane_entry in state.values()
                for tier_entry in lane_entry.values()
            )

        total1 = total(state1)
        total2 = total(state2)
        self.assertGreater(total2, total1)


if __name__ == "__main__":
    unittest.main()
