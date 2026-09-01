import unittest

from router.policy import decide_tier


class TestPolicy(unittest.TestCase):
    def test_citation_check_low_stakes_is_fast_no_verification(self):
        d = decide_tier("citation_check", "low")
        self.assertEqual(d.tier, "fast")
        self.assertFalse(d.verification_required)

    def test_litigation_reasoning_always_frontier(self):
        for stakes in ("low", "medium", "high"):
            d = decide_tier("litigation_reasoning", stakes)
            self.assertEqual(d.tier, "frontier")

    def test_high_stakes_forces_frontier_even_for_mechanical_task(self):
        d = decide_tier("citation_check", "high")
        self.assertEqual(d.tier, "frontier")
        self.assertTrue(d.verification_required)

    def test_medium_stakes_raises_fast_to_balanced(self):
        d = decide_tier("citation_check", "medium")
        self.assertEqual(d.tier, "balanced")
        self.assertFalse(d.verification_required)

    def test_verification_only_mandatory_at_high_stakes(self):
        for task_type in ("contract_review", "transactional_drafting", "legal_research"):
            self.assertFalse(decide_tier(task_type, "low").verification_required)
            self.assertFalse(decide_tier(task_type, "medium").verification_required)
            self.assertTrue(decide_tier(task_type, "high").verification_required)

    def test_unknown_task_type_raises(self):
        with self.assertRaises(ValueError):
            decide_tier("not_a_real_task_type", "low")

    def test_unknown_stakes_raises(self):
        with self.assertRaises(ValueError):
            decide_tier("legal_research", "extreme")


if __name__ == "__main__":
    unittest.main()
