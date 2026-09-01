import unittest

from memory_lab.architectures import AnswerResult
from eval.scorer import score
from scenario.queries import QUERIES

BY_ID = {q.id: q for q in QUERIES}


class TestScorerTrueNegatives(unittest.TestCase):
    """FAILURE-CLASSES.md item 4: prove the scorer actually fails wrong
    answers, not just passes right ones. Every case here feeds the scorer a
    deliberately incorrect AnswerResult and asserts `correct is False`.
    """

    def test_fails_stale_fact_after_supersession(self):
        q = BY_ID["Q1-supersession-current"]
        wrong = AnswerResult(fact_id="dr-hearing-1", snippet="stale", matter_ids_touched=[q.matter_id])
        result = score(q, wrong)
        self.assertFalse(result.correct)

    def test_fails_when_forbidden_matter_touched(self):
        q = BY_ID["Q4-leakage-same-predicate"]
        leaking = AnswerResult(fact_id="dr-hearing-2", snippet="leaked", matter_ids_touched=[q.forbidden_matter])
        result = score(q, leaking)
        self.assertFalse(result.correct)
        self.assertTrue(result.leaked)

    def test_fails_when_true_negative_query_returns_a_fact_anyway(self):
        q = BY_ID["Q5-no-cross-matter-fact"]
        hallucinated = AnswerResult(fact_id="se-value-2", snippet="hallucinated", matter_ids_touched=[q.matter_id])
        result = score(q, hallucinated)
        self.assertFalse(result.correct)

    def test_fails_episodic_query_with_wrong_snippet(self):
        q = BY_ID["Q7-episodic-recall"]
        irrelevant = AnswerResult(fact_id=None, snippet="the weather was nice today", matter_ids_touched=[q.matter_id])
        result = score(q, irrelevant)
        self.assertFalse(result.correct)

    def test_passes_correct_current_fact(self):
        q = BY_ID["Q1-supersession-current"]
        right = AnswerResult(fact_id="dr-hearing-2", snippet="hearing_date is 2026-03-15", matter_ids_touched=[q.matter_id])
        result = score(q, right)
        self.assertTrue(result.correct)

    def test_fails_true_negative_query_with_irrelevant_episodic_snippet(self):
        # Found by direct testing, not assumed: HybridMemory's episodic
        # fallback can confidently recall a real but wholly irrelevant turn
        # (fact_id=None) for a query that should find nothing at all. A
        # scorer that only checks `fact_id is None` misses this -- see
        # README "Generalization check, round 2".
        q = BY_ID["Q8-not-yet-known"]
        irrelevant_recall = AnswerResult(
            fact_id=None,
            snippet="We should track the contract dispute hearing and keep an eye on deadlines.",
            matter_ids_touched=[q.matter_id],
        )
        result = score(q, irrelevant_recall)
        self.assertFalse(result.correct)

    def test_passes_true_negative_query_with_genuinely_empty_snippet(self):
        q = BY_ID["Q8-not-yet-known"]
        genuinely_nothing = AnswerResult(fact_id=None, snippet="", matter_ids_touched=[q.matter_id])
        result = score(q, genuinely_nothing)
        self.assertTrue(result.correct)


if __name__ == "__main__":
    unittest.main()
