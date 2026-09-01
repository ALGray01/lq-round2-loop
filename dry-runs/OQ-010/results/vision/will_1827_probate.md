# Candidate: Multimodal vision (Claude, direct image reading)

Source: `documents/raw/will_1827_probate.png` (300dpi render of page 4 of
the real 1827 NSW Supreme Court probate bond for James Squire, from the
Wikimedia Commons "Squire, James (Sr) - Probate package" scan). Read
directly with no OCR engine -- this is a human-style visual transcription
produced by the vision-language model doing the rest of this assessment,
used as the "multimodal vision" candidate the question calls for.

Method: image given to the model at full resolution, transcribed once,
uncertain words marked `[?]`.

## Transcription

In the Supreme Court of New South Wales.

In the Goods of James Squire late of
Kissing Point deceased. —

Appeared personally Daniel Cooper of
Sydney in the Colony of New South Wales
Merchant and being duly sworn upon
the Holy Evangelists of Almighty God maketh
Oath and saith that he will well and
truly administer all and every the goods of
the said Deceased and pay his debts so
far as his goods will extend, and the law will bind him, and that
he will Exhibit a full true and perfect
Inventory of the said goods of the said
deceased and render a true account
of his administration into the Supreme
Court of Civil Judicature for the Territory
of New South Wales when he shall be
thereunto lawfully required and that
he believes the said goods do not exceed
the value of Two thousand pounds. —

Sworn in open Court
this seventh day of June
in the year of our Lord
1827.

~~Before me~~ [struck through]
By An[?] Bo[?]st[?] [registrar's signature, illegible flourish]

## Notes

- Every word transcribed with high confidence except the final signature
  line, which is a stylized personal signature (registrar/deputy)
  overlapping a struck-through "Before me" -- genuinely illegible even to
  a human reader without external knowledge of who signed 1827 NSW probate
  bonds.
- Period letterforms (long descenders, looped "th", the archaic terminal
  flourish on words like "Deceased") required treating this as connected
  cursive rather than isolated character recognition -- this is the kind
  of context-dependent reading a general-purpose vision-language model is
  comparatively good at, because it can use whole-word and whole-phrase
  legal-formula priors ("maketh Oath and saith that he will well and truly
  administer...") the way a human paralegal familiar with probate boilerplate
  would, rather than recognizing letter-by-letter.
- No hallucination guardrail here beyond the model's own uncertainty
  marking -- this transcript has NOT been cross-checked against an
  independent published transcription of this exact document, which is a
  real limitation of using vision-LM output as ground truth (see
  README limitations).
