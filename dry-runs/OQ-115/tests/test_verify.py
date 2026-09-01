import unittest

from router.verify import verify_output


class TestVerify(unittest.TestCase):
    def test_clean_text_passes(self):
        r = verify_output(
            "The general rule is that indemnification clauses should be "
            "mutual absent a specific reason for asymmetry. See Smith v. "
            "Jones, 410 U.S. 113 (1973)."
        )
        self.assertTrue(r.passed)
        self.assertEqual(r.findings, [])

    def test_future_dated_citation_is_flagged(self):
        # A citation dated after "today" (2026) cannot be real. This is a
        # true-negative fixture proving the checker isn't a rubber stamp.
        r = verify_output("As established in Doe v. Roe, 500 F.3d 1 (2099).")
        self.assertFalse(r.passed)
        self.assertTrue(any("future" in f for f in r.findings))

    def test_implausible_volume_is_flagged(self):
        r = verify_output("See Doe v. Roe, 12000 F.3d 1 (2010).")
        self.assertFalse(r.passed)
        self.assertTrue(any("implausibly large" in f for f in r.findings))

    def test_dangling_case_name_is_flagged(self):
        r = verify_output(
            "As the court held in Doe v. Roe, the contract was unenforceable "
            "on public policy grounds, and no further authority is needed."
        )
        self.assertFalse(r.passed)
        self.assertTrue(any("no reporter/year" in f for f in r.findings))

    def test_absolute_claim_is_flagged(self):
        r = verify_output("We guarantee you will win this motion outright.")
        self.assertFalse(r.passed)
        self.assertTrue(any("absolute claim" in f for f in r.findings))

    def test_certainty_reinforcing_no_doubt_is_still_flagged(self):
        # "no doubt" contains the hedge word "no" but REINFORCES certainty
        # rather than qualifying it -- a naive hedge lookback would wrongly
        # wave this through. It must still be flagged.
        r = verify_output("There is no doubt we guarantee a win here.")
        self.assertFalse(r.passed)
        self.assertTrue(any("absolute claim" in f for f in r.findings))

    def test_certainty_reinforcing_no_question_is_still_flagged(self):
        r = verify_output("No question, we guarantee this outcome for you.")
        self.assertFalse(r.passed)
        self.assertTrue(any("absolute claim" in f for f in r.findings))

    def test_negated_hedge_language_is_not_flagged(self):
        # "we CANNOT guarantee" is responsible hedging, the opposite of an
        # unqualified claim -- flagging it would be backwards and would
        # punish exactly the caution the checker is supposed to encourage.
        r = verify_output(
            "We cannot guarantee an outcome, but the arguments are strong."
        )
        self.assertTrue(r.passed)
        self.assertEqual(r.findings, [])

    def test_zero_volume_citation_is_flagged(self):
        r = verify_output("See Doe v. Roe, 0 F.3d 100 (2010).")
        self.assertFalse(r.passed)


if __name__ == "__main__":
    unittest.main()
