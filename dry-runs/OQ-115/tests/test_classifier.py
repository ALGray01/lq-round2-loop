import unittest

from router.classifier import classify


class TestTaskTypeClassification(unittest.TestCase):
    def test_litigation_reasoning(self):
        c = classify("Draft the argument section for our motion to dismiss.")
        self.assertEqual(c.task_type, "litigation_reasoning")

    def test_transactional_drafting(self):
        c = classify("Please draft an NDA for our new vendor relationship.")
        self.assertEqual(c.task_type, "transactional_drafting")

    def test_contract_review(self):
        c = classify("Can you review this contract and flag risky clauses?")
        self.assertEqual(c.task_type, "contract_review")

    def test_legal_research(self):
        c = classify("What is the standard for piercing the corporate veil in Delaware?")
        self.assertEqual(c.task_type, "legal_research")

    def test_citation_check(self):
        c = classify("Please verify the citation: 410 U.S. 113 (1973), Bluebook format.")
        self.assertEqual(c.task_type, "citation_check")

    def test_no_signal_falls_back_to_legal_research_with_zero_confidence(self):
        c = classify("hello, can you help me with something today")
        self.assertEqual(c.task_type, "legal_research")
        self.assertEqual(c.task_type_confidence, 0.0)
        self.assertEqual(c.task_type_signals, [])


class TestStakesClassification(unittest.TestCase):
    def test_default_low(self):
        c = classify("Summarize the general rule on adverse possession.")
        self.assertEqual(c.stakes, "low")
        self.assertEqual(c.stakes_source, "default")

    def test_high_stakes_text_signal(self):
        c = classify("This is the final version to be filed with the court tomorrow.")
        self.assertEqual(c.stakes, "high")
        self.assertEqual(c.stakes_source, "text_heuristic")

    def test_medium_stakes_text_signal(self):
        c = classify("Please prep a draft to send to the client for review.")
        self.assertEqual(c.stakes, "medium")

    def test_explicit_stakes_is_respected(self):
        c = classify("Summarize the rule.", explicit_stakes="high")
        self.assertEqual(c.stakes, "high")
        self.assertEqual(c.stakes_source, "explicit")

    def test_text_cannot_downgrade_explicit_stakes(self):
        # Explicit stakes=high from caller metadata; text tries to sound
        # casual/low-stakes. Stakes must NOT be downgraded by text content.
        c = classify(
            "just a quick casual note, nothing formal, no big deal",
            explicit_stakes="high",
        )
        self.assertEqual(c.stakes, "high")

    def test_text_can_escalate_above_explicit_low(self):
        c = classify(
            "This is the final version to be filed with the court.",
            explicit_stakes="low",
        )
        self.assertEqual(c.stakes, "high")
        self.assertEqual(c.stakes_source, "explicit+escalated_by_text")


if __name__ == "__main__":
    unittest.main()
