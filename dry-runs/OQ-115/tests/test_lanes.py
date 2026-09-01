import unittest

from router.lanes import pick_lane


CONFIG = {
    "lane_a": {
        "tiers": {
            "fast": {"model": "a-fast", "daily_cap_tokens": 1000},
            "balanced": {"model": "a-bal", "daily_cap_tokens": 500},
            "frontier": {"model": "a-front", "daily_cap_tokens": 200},
        }
    },
    "lane_b": {
        "tiers": {
            "fast": {"model": "b-fast", "daily_cap_tokens": 800},
            "balanced": {"model": "b-bal", "daily_cap_tokens": 400},
            "frontier": {"model": "b-front", "daily_cap_tokens": 100},
        }
    },
}


class TestPickLane(unittest.TestCase):
    def test_picks_lane_with_most_headroom(self):
        state = {
            "lane_a": {"fast": {"used_tokens": 900}},
            "lane_b": {"fast": {"used_tokens": 0}},
        }
        choice = pick_lane("fast", "low", 100, CONFIG, state)
        self.assertEqual(choice.lane, "lane_b")
        self.assertEqual(choice.tier, "fast")
        self.assertEqual(choice.fallback_mode, "normal")

    def test_low_stakes_downgrades_tier_when_frontier_exhausted_but_fast_has_room(self):
        # Both lanes' frontier tier is exhausted, but fast tier still has
        # plenty of headroom -- this is exactly the scenario a shared
        # (non-per-tier) budget couldn't distinguish.
        state = {
            "lane_a": {"frontier": {"used_tokens": 200}},
            "lane_b": {"frontier": {"used_tokens": 100}},
        }
        choice = pick_lane("frontier", "low", 50, CONFIG, state)
        self.assertEqual(choice.fallback_mode, "downgraded_no_headroom")
        self.assertNotEqual(choice.tier, "frontier")
        self.assertIn(choice.model, ("a-bal", "b-bal", "a-fast", "b-fast"))

    def test_high_stakes_never_downgrades_tier_goes_over_budget_instead(self):
        state = {
            "lane_a": {"frontier": {"used_tokens": 200}},
            "lane_b": {"frontier": {"used_tokens": 100}},
        }
        choice = pick_lane("frontier", "high", 50, CONFIG, state)
        self.assertEqual(choice.fallback_mode, "over_budget_escalation")
        self.assertEqual(choice.tier, "frontier")
        self.assertIn(choice.model, ("a-front", "b-front"))

    def test_normal_case_no_fallback_needed(self):
        state = {}
        choice = pick_lane("balanced", "medium", 50, CONFIG, state)
        self.assertEqual(choice.fallback_mode, "normal")
        self.assertEqual(choice.lane, "lane_a")  # more absolute headroom (500 vs 400)

    def test_everything_exhausted_still_returns_a_choice_over_budget(self):
        state = {
            "lane_a": {t: {"used_tokens": 10_000} for t in ("fast", "balanced", "frontier")},
            "lane_b": {t: {"used_tokens": 10_000} for t in ("fast", "balanced", "frontier")},
        }
        choice = pick_lane("balanced", "low", 50, CONFIG, state)
        # Distinct label from the stakes=='high' over-budget case: this one
        # means "tried to downgrade, nothing cheaper had room either" --
        # not "refused to downgrade by policy".
        self.assertEqual(choice.fallback_mode, "over_budget_no_cheaper_tier_available")


if __name__ == "__main__":
    unittest.main()
