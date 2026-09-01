# Candidate: Multimodal vision (Claude, direct image reading)

Source: `documents/redaction_test/manafort_p3_degraded.png` -- real text
from page 3 of the government's sentencing memorandum in *United States v.
Manafort* (D.D.C. 17-cr-201, Doc. 525, filed 2019-02-23), with a synthetic
redaction bar over the "II." line and synthetic scan degradation (skew,
blur, noise, contrast loss, JPEG recompression) applied -- see
`scripts/make_redaction_test.py` and README for exactly what was changed.

## Transcription

downward departure from the government's estimated sentencing guideline range of 210 to 262
months is not warranted and he would not seek or suggest a departure or adjustment.²

The government has organized this submission as follows:

    I.    Procedural History

    [REDACTED — solid black bar, full line width, no text recoverable]

    III.  Manafort's Relevant Criminal Conduct And The Statutory Sentencing Factors
          Under 18 U.S.C. § 3553(a):

          (A)  Count One Conduct

          (B)  Count Two Conduct

          (C)  Post-Plea Conduct

Attached to this filing are the following:

  • Attachment A: A copy of the superseding criminal information to which Manafort pled
    guilty on September 14, 2018 (Doc. 419);
  • Attachment B: A copy of Manafort's plea agreement (Doc. 422) and the Statement of the
    Offenses and Other Acts, dated September 14, 2018 (Doc. 423);
  • Attachment C: A copy the superseding indictment charging Manafort in the Eastern
    District of Virginia (EDVA) on February 22, 2019, United States v. Manafort, 1:18-cr-83
    (Doc. 9);
  • Attachment D: A copy of the verdict form from Manafort's trial in the EDVA, United
    States v. Manafort, 1:18-cr-83 (Aug. 21, 2018) (Doc. 280);
  • Attachment E: A copy of the government's sentencing submission in the EDVA, United
    States v. Manafort, 1:18-cr-83 (Feb. 15, 2019) (Doc. 314);
  • Attachment F: A copy of the government's objections to the PSR (under seal); and
  • Attachment G: A copy of additional documents cited herein, including the government's
    proposed trial exhibits, which were previously provided to the Court and defense. (An
    index of these exhibits is included in Attachment G, in the front of that attachment.)

² Attachment B, section 4D. Manafort further agreed that a sentence within the 210 to 262
month range "would constitute a reasonable sentence in light of all the factors set forth in
18 U.S.C. § 3553(a), should such a sentence be subject to appellate review notwithstanding
the appeal waiver provided below." Id. at section 5.

3

## Notes

- Correctly identified the redaction as a redaction (did not guess or
  hallucinate content for "II. The Presentence Investigative Report
  ('PSR')" even though the tops of a couple of ascenders leak out above
  the bar in the degraded image) -- reported it as unrecoverable rather
  than fabricating a plausible-sounding line. This is the behavior worth
  checking for every candidate: a bad OCR pipeline may confidently emit
  invented text where a redaction bar sits, which is far more dangerous
  in a legal setting than an honest gap.
- Degradation (skew, blur, JPEG noise, faded contrast) did not defeat
  transcription at this severity level -- every non-redacted word was
  read correctly against the known-clean source text.
