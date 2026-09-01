import unittest

from memory_lab.retrieval import confident_top


class TestConfidentTop(unittest.TestCase):
    def test_rejects_exact_tie(self):
        # e.g. scenario1 Q5/Q8: every candidate scores identically (stopword-only overlap)
        self.assertIsNone(confident_top([("a", 0.052), ("b", 0.052), ("c", 0.052)]))

    def test_accepts_clear_leader(self):
        self.assertEqual(confident_top([("a", 0.40), ("b", 0.05)]), ("a", 0.40))

    def test_accepts_weak_but_dominant_match(self):
        # e.g. scenario2 R2-Q7: absolute score is low (sparse corpus) but clearly ahead
        self.assertEqual(confident_top([("a", 0.119), ("b", 0.084)]), ("a", 0.119))

    def test_rejects_thin_margin_below_rel_margin(self):
        # ratio here is ~1.13 (0.043/0.038), rounded from the real R2-Q5
        # scores (0.0426.../0.0384... = 1.11) -- either way, below REL_MARGIN=1.3
        self.assertIsNone(confident_top([("a", 0.043), ("b", 0.038)]))

    def test_rejects_empty(self):
        self.assertIsNone(confident_top([]))

    def test_rejects_zero_score(self):
        self.assertIsNone(confident_top([("a", 0.0)]))

    def test_single_candidate_above_floor_accepted(self):
        self.assertEqual(confident_top([("a", 0.3)]), ("a", 0.3))

    def test_single_candidate_at_or_below_floor_rejected(self):
        self.assertIsNone(confident_top([("a", 0.02)]))


if __name__ == "__main__":
    unittest.main()
