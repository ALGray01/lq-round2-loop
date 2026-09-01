import tempfile
import unittest
from pathlib import Path

from router.cap_tracker import CapTracker
from router.models import ModelProfile
from router.policy import select
from router.taxonomy import Stakes, TaskType

# A small synthetic registry, independent of the real models.json tuning,
# so these tests assert against numbers we control by hand.
CHEAP_WEAK = ModelProfile("cheap-weak", "test", reasoning=2, drafting=2, factual_accuracy=2,
                           speed=5, context_window_tokens=100_000, cost_per_1m_blended_usd=1.0)
MID = ModelProfile("mid", "test", reasoning=3, drafting=3, factual_accuracy=3,
                    speed=3, context_window_tokens=100_000, cost_per_1m_blended_usd=15.0)
STRONG_EXPENSIVE = ModelProfile("strong-expensive", "test", reasoning=5, drafting=5, factual_accuracy=5,
                                 speed=1, context_window_tokens=100_000, cost_per_1m_blended_usd=30.0)
REGISTRY = [CHEAP_WEAK, MID, STRONG_EXPENSIVE]


def fresh_tracker(caps=None) -> CapTracker:
    # mkdtemp (not TemporaryDirectory) since these helper-created dirs just need
    # to outlive the CapTracker within a single test; the OS temp dir reaps them.
    path = Path(tempfile.mkdtemp()) / "cap_state.json"
    return CapTracker(state_path=path, caps=caps or {})


class TestPolicySelection(unittest.TestCase):
    def test_low_stakes_prefers_cheap_over_strong(self):
        decision = select(REGISTRY, TaskType.GENERAL, Stakes.LOW, fresh_tracker(), estimated_tokens=100)
        # cost_weight=1.0 at low stakes should pull the choice toward the cheap model
        # despite it having the weakest raw capability.
        self.assertEqual(decision.chosen_model_id, "cheap-weak")

    def test_high_stakes_prefers_strong_ignoring_cost(self):
        decision = select(REGISTRY, TaskType.GENERAL, Stakes.HIGH, fresh_tracker(), estimated_tokens=100)
        self.assertEqual(decision.chosen_model_id, "strong-expensive")
        self.assertTrue(decision.human_review_required)

    def test_high_stakes_overrides_cap_instead_of_downgrading(self):
        tracker = fresh_tracker(caps={"strong-expensive": 50})
        tracker.record_usage("strong-expensive", 50)  # exhausted
        decision = select(REGISTRY, TaskType.GENERAL, Stakes.HIGH, tracker, estimated_tokens=100)
        self.assertEqual(decision.chosen_model_id, "strong-expensive")
        self.assertTrue(decision.cap_exceeded)
        self.assertTrue(any("over its tracked token cap" in w for w in decision.warnings))

    def test_low_stakes_substitutes_away_from_capped_model(self):
        tracker = fresh_tracker(caps={"cheap-weak": 50})
        tracker.record_usage("cheap-weak", 50)  # exhausted
        decision = select(REGISTRY, TaskType.GENERAL, Stakes.LOW, tracker, estimated_tokens=100)
        self.assertNotEqual(decision.chosen_model_id, "cheap-weak")
        self.assertFalse(decision.cap_exceeded)
        self.assertTrue(any("substituted next-best" in w for w in decision.warnings))

    def test_below_capability_floor_is_flagged(self):
        # At high stakes the floor is 4.0; even the best of an all-weak registry
        # should trip the floor warning rather than pretend it's adequate.
        weak_registry = [CHEAP_WEAK, MID]
        decision = select(weak_registry, TaskType.GENERAL, Stakes.HIGH, fresh_tracker(), estimated_tokens=100)
        self.assertTrue(decision.below_capability_floor)
        self.assertTrue(any("below the recommended floor" in w for w in decision.warnings))

    def test_citation_checking_always_requires_verification(self):
        decision = select(REGISTRY, TaskType.CITATION_CHECKING, Stakes.LOW, fresh_tracker(), estimated_tokens=100)
        self.assertTrue(decision.requires_external_verification)
        self.assertTrue(decision.human_review_required)

    def test_rationale_names_the_chosen_model_and_top_weighted_field(self):
        decision = select(REGISTRY, TaskType.CITATION_CHECKING, Stakes.HIGH, fresh_tracker(), estimated_tokens=100)
        self.assertIn(decision.chosen_model_id, decision.rationale)
        self.assertIn("factual_accuracy", decision.rationale)  # citation_checking's dominant weight

    def test_context_window_filter_excludes_too_small_models(self):
        small_context = ModelProfile("small-context", "test", reasoning=5, drafting=5, factual_accuracy=5,
                                      speed=5, context_window_tokens=1000, cost_per_1m_blended_usd=1.0)
        registry = [small_context, MID]
        decision = select(registry, TaskType.GENERAL, Stakes.LOW, fresh_tracker(),
                           estimated_tokens=100, min_context_tokens=50_000)
        self.assertEqual(decision.chosen_model_id, "mid")


if __name__ == "__main__":
    unittest.main()
