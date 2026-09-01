import unittest

from router.classifier import KeywordClassifier
from router.taxonomy import TaskType


class TestKeywordClassifier(unittest.TestCase):
    def setUp(self):
        self.clf = KeywordClassifier()

    def test_litigation(self):
        c = self.clf.classify("Draft a motion for summary judgment ahead of the hearing")
        self.assertEqual(c.task_type, TaskType.LITIGATION_REASONING)

    def test_transactional_drafting(self):
        c = self.clf.classify("Draft an employment agreement for our new VP of Sales")
        self.assertEqual(c.task_type, TaskType.TRANSACTIONAL_DRAFTING)

    def test_contract_review(self):
        c = self.clf.classify("Please review this contract and flag risky clauses vs our playbook")
        self.assertEqual(c.task_type, TaskType.CONTRACT_REVIEW)

    def test_legal_research(self):
        c = self.clf.classify("Research the case law on adverse possession in this jurisdiction")
        self.assertEqual(c.task_type, TaskType.LEGAL_RESEARCH)

    def test_citation_checking(self):
        c = self.clf.classify("Verify this citation before we file the reply brief")
        self.assertEqual(c.task_type, TaskType.CITATION_CHECKING)

    def test_falls_back_to_general_on_unrelated_text(self):
        c = self.clf.classify("What's a good name for our office holiday party this year?")
        self.assertEqual(c.task_type, TaskType.GENERAL)
        self.assertEqual(c.confidence, 0.0)

    def test_confidence_is_bounded(self):
        for text in [
            "Draft a motion for summary judgment",
            "check this citation and confirm pincite and shepardize and verify the cite",
        ]:
            c = self.clf.classify(text)
            self.assertGreaterEqual(c.confidence, 0.0)
            self.assertLessEqual(c.confidence, 1.0)

    def test_bare_litigation_keyword_does_not_fire_on_admin_team_names(self):
        # Regression: a second, genuinely blind held-out eval (see README)
        # found "litigation" (as a bare keyword) misclassified a purely
        # administrative request into litigation_reasoning, purely because
        # a team was named "the litigation team" -- worse than falling back
        # to general, since it actively assigns the wrong (and more
        # expensive) task type rather than just missing.
        c = self.clf.classify("can you help me set up a shared drive folder structure for the litigation team")
        self.assertEqual(c.task_type, TaskType.GENERAL)

    def test_short_keyword_does_not_match_inside_a_longer_word(self):
        # Regression: an independent held-out eval (see README) found that
        # naive substring matching made "nda" match inside "defeNDAnt",
        # misclassifying any text about a defendant as NDA-drafting work.
        c = self.clf.classify("need help prepping questions for the defendant's deposition")
        self.assertNotIn("nda", c.matched_keywords)

    def test_plural_form_of_a_keyword_still_matches(self):
        c = self.clf.classify("partner wants every citation in this memo verified before it goes out")
        self.assertEqual(c.task_type, TaskType.CITATION_CHECKING)
        c2 = self.clf.classify("go through the lease agreements and flag anything unusual")
        self.assertIn(c2.task_type, (TaskType.CONTRACT_REVIEW, TaskType.TRANSACTIONAL_DRAFTING))

    def test_match_count_outranks_a_shorter_lists_higher_fraction(self):
        # Regression: scoring by fraction-of-list-matched alone let a
        # category with a SHORTER keyword list win on one weak match against
        # a category with a longer list and the same single match (e.g. one
        # "brief" hit at 1/17 beat citation_checking's one "cite" hit at
        # 1/18, purely because that list happened to be one entry longer).
        # A synthetic keyword map isolates the ranking logic from taxonomy.py
        # wording that might change independently of this behavior.
        keyword_map = {
            TaskType.LITIGATION_REASONING: ("alpha",),                         # 1 keyword, matches 1 -> 1/1
            TaskType.CONTRACT_REVIEW: ("beta", "gamma", "delta", "epsilon"),    # 4 keywords, matches 2 -> 2/4
        }
        clf = KeywordClassifier(keyword_map=keyword_map)
        c = clf.classify("alpha beta gamma")
        # CONTRACT_REVIEW has the lower fraction (0.5 vs 1.0) but more actual
        # matches (2 vs 1); match count should win.
        self.assertEqual(c.task_type, TaskType.CONTRACT_REVIEW)
        self.assertEqual(set(c.matched_keywords), {"beta", "gamma"})


if __name__ == "__main__":
    unittest.main()
