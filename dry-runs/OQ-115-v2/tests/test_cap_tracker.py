import json
import tempfile
import unittest
from pathlib import Path

from router.cap_tracker import CapTracker


class TestCapTracker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "cap_state.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_starts_with_zero_usage(self):
        t = CapTracker(state_path=self.state_path, caps={"m1": 1000})
        self.assertEqual(t.status("m1").used, 0)
        self.assertEqual(t.status("m1").remaining, 1000)
        self.assertTrue(t.has_headroom("m1", 999))
        self.assertFalse(t.has_headroom("m1", 1001))

    def test_record_usage_persists_across_instances(self):
        t1 = CapTracker(state_path=self.state_path, caps={"m1": 1000})
        t1.record_usage("m1", 400)
        t1.record_usage("m1", 400)

        t2 = CapTracker(state_path=self.state_path, caps={"m1": 1000})
        self.assertEqual(t2.status("m1").used, 800)
        self.assertEqual(t2.status("m1").remaining, 200)

    def test_exhausted_flag(self):
        t = CapTracker(state_path=self.state_path, caps={"m1": 100})
        t.record_usage("m1", 100)
        self.assertTrue(t.status("m1").exhausted)
        t2 = CapTracker(state_path=self.state_path, caps={"m1": 100})
        t2.record_usage("m1", 50)  # over cap on purpose
        self.assertTrue(t2.status("m1").exhausted)
        self.assertEqual(t2.status("m1").remaining, 0)  # clamped, not negative

    def test_unknown_model_has_unbounded_headroom(self):
        t = CapTracker(state_path=self.state_path, caps={"m1": 100})
        self.assertTrue(t.has_headroom("unknown-model", 10_000_000))

    def test_negative_tokens_rejected_not_silently_inflating_headroom(self):
        # Regression: a negative record_usage() call used to make `remaining`
        # exceed the real cap (used went negative, remaining = cap - used > cap).
        t = CapTracker(state_path=self.state_path, caps={"m1": 1000})
        t.record_usage("m1", 1000)  # exhaust it
        with self.assertRaises(ValueError):
            t.record_usage("m1", -999_999)
        self.assertTrue(t.status("m1").exhausted)
        self.assertEqual(t.status("m1").remaining, 0)  # unchanged by the rejected call

    def test_corrupted_state_file_degrades_to_zero_usage_instead_of_crashing(self):
        self.state_path.write_text("{not valid json!!", encoding="utf-8")
        t = CapTracker(state_path=self.state_path, caps={"m1": 1000})  # must not raise
        self.assertEqual(t.status("m1").used, 0)
        self.assertEqual(t.status("m1").remaining, 1000)

    def test_malformed_schema_in_state_file_ignores_bad_entries_only(self):
        self.state_path.write_text(
            json.dumps({"caps": {"m1": -5, "m2": 500}, "usage": {"m1": "not-a-number", "m2": 100}}),
            encoding="utf-8",
        )
        t = CapTracker(state_path=self.state_path, caps={"m1": 1000, "m2": 1000})
        self.assertEqual(t.status("m1").used, 0)      # bad usage entry dropped
        self.assertEqual(t.caps["m1"], 1000)           # bad (negative) cap entry dropped, default kept
        self.assertEqual(t.status("m2").used, 100)     # valid entries still load
        self.assertEqual(t.caps["m2"], 500)

    def test_infinite_or_nan_cap_in_state_file_does_not_bypass_enforcement(self):
        # Regression: round-2 attacker found that a corrupted state file with
        # caps["m1"] = Infinity (or a plain JSON literal like 1e400, which
        # overflows to float('inf')) passed the old `value >= 0` check and
        # silently made a known model's cap unbounded, defeating enforcement.
        self.state_path.write_text(
            json.dumps({"caps": {"m1": float("inf"), "m2": 1e400, "m3": float("nan")}, "usage": {}}),
            encoding="utf-8",
        )
        t = CapTracker(state_path=self.state_path, caps={"m1": 1000, "m2": 1000, "m3": 1000})
        # All three bad entries dropped; real configured defaults kept instead.
        self.assertEqual(t.caps["m1"], 1000)
        self.assertEqual(t.caps["m2"], 1000)
        self.assertEqual(t.caps["m3"], 1000)
        self.assertFalse(t.has_headroom("m1", 2000))  # cap is finite again, enforceable

    def test_save_is_atomic_no_leftover_temp_file(self):
        t = CapTracker(state_path=self.state_path, caps={"m1": 1000})
        t.record_usage("m1", 10)
        leftovers = list(self.state_path.parent.glob(".cap_state_*"))
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
