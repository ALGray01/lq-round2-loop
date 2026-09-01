# Hard-scan legal OCR: a concrete recipe, tested on real documents

Working comparison of OCR/document-conversion candidates on two real hard
legal documents, plus a recommended preprocessing + engine pipeline. Built
for the question: estate planners, litigators, and archivists hit OCR walls
on low-quality scans, handwriting, multi-column/structured layouts, and
redactions -- what actually works?

**tl;dr recommendation:** route by document type, don't pick one engine for
everything. See [Recommended pipeline](#recommended-pipeline).

## Test documents (real, not synthetic)

1. **`documents/raw/will_1827_probate.png`** -- an 1827 handwritten probate
   bond from the Supreme Court of New South Wales (*In the Goods of James
   Squire*), 300dpi scan of a real archival document (public domain,
   sourced from Wikimedia Commons' "Squire, James (Sr) - Probate package").
   Cursive period handwriting, foxed/aged paper, visible fold lines, faint
   ink bleed-through. Directly representative of what estate planners and
   genealogists hit in archived probate records.
2. **`documents/redaction_test/manafort_p3_degraded.png`** -- page 3 of the
   real government sentencing memorandum in *United States v. Manafort*
   (D.D.C. 17-cr-201, Doc. 525, filed 2019-02-23). Real hierarchical legal
   outline (I./II./III./(A)/(B)), real footnote, real justified-text
   spacing artifacts. **Two things were added on top of the real page**,
   both fully disclosed and produced by `scripts/make_redaction_test.py`:
   a synthetic black redaction bar over one real line (to test redaction
   handling under controlled conditions), and synthetic scan degradation
   (1.4° rotation, Gaussian blur + noise, reduced contrast, JPEG
   recompression at q=55) to simulate the photocopied/rescanned productions
   litigators actually receive in discovery, rather than a clean born-digital
   PDF. The unmodified original is `documents/raw/manafort_memo_p3.png`.

Why not one document with every failure mode at once (handwriting +
multi-column + redaction + low quality)? A real, freely-available public
document that hits all four simultaneously was not found in the time
available (see Reflection). Two real documents covering complementary
failure modes was judged more honest than stretching one document's
description to cover things it doesn't actually contain.

## Candidates tested

| # | Candidate | How it was run |
|---|-----------|-----------------|
| 1 | **PaddleOCR** (PP-OCRv6, `paddleocr` 3.7.0) | Local, CPU, `scripts/run_paddleocr.py` |
| 2 | **Docling** (`docling`, default pipeline: layout model + RapidOCR) | Local, `scripts/run_docling.py` |
| 3 | **Multimodal vision** (Claude, direct image reading -- this assessment's own model) | Read the page image directly, transcribed by hand, notes in `results/vision/` |
| 4 | **Chandra 2** (`datalab-to/chandra`, HF backend) | Attempted; see [Chandra 2](#chandra-2-attempted) for outcome |

### Results

**Document 1: 1827 handwritten probate bond (cursive, aged paper)**

| Candidate | Wall time | Output |
|---|---|---|
| PaddleOCR (PP-OCRv6) | 90s infer + 2s init | Detected all 24 lines but words are heavily garbled: *"In the Suprene Court of Now touth Wales"*, *"Apeared personilly daniel Cooper"*. Self-reported avg. confidence 0.75 -- see caveat below on why that number should not be trusted at face value. |
| Docling (default pipeline, RapidOCR backend) | 24s | Near-total failure: 162 characters total, word salad (*"Dersnal red bewg rm Vucakett Battad Jae weeli H807..."*), and one hallucinated CJK character (子) that has no relationship to anything on the page. |
| **Multimodal vision (Claude)** | manual, ~1 read | Full, fluent, essentially correct transcription (`results/vision/will_1827_probate.md`) recovering the entire legal-boilerplate passage correctly, including archaic phrasing ("maketh Oath and saith that he will well and truly administer"). Only the registrar's cursive signature was flagged unreadable -- correctly, a human would struggle with it too. |
| Chandra 2 | not run | See [Chandra 2](#chandra-2-attempted). |

**Document 2: redacted + degraded litigation filing (machine print, structured outline, footnote)**

| Candidate | Wall time | Output |
|---|---|---|
| PaddleOCR (PP-OCRv6) | 94s infer + 2s init | Essentially perfect. Recovered the full outline, all seven lettered attachments, and the footnote verbatim, including the pincite formatting. Correctly **omitted** the redacted "II." line rather than inventing text for it. |
| Docling (default pipeline, RapidOCR backend) | 36s | Recovered all real content and correctly preserved the outline/list structure as markdown headings and a numbered list -- but merged inter-word spaces at a meaningful rate: *"thegovernment's"*, *"guidelinerange"*, *"September14,2018"*. Also correctly omitted the redacted line. |
| **Multimodal vision (Claude)** | manual | Perfect transcription of all real text, and explicitly reported the redaction as unrecoverable (`[REDACTED — solid black bar, full line width, no text recoverable]`) instead of guessing. |
| Chandra 2 | not run | See below. |

**A confidence-score caveat, checked rather than assumed:** PaddleOCR's
self-reported average confidence was *higher* on the machine-print page
(0.99) than the handwriting page (0.75), which is directionally right, but
0.75 badly understates how wrong the handwriting transcript actually is --
most individual words are simply incorrect, not just "75% confident."
Treat PaddleOCR's confidence score as a rough triage signal for routing
pages to human review, never as an accuracy estimate.

## Preprocessing pipeline (`scripts/preprocess.py`)

Grayscale → upscale-if-small → deskew (minAreaRect on Otsu-thresholded ink
mask) → denoise (`fastNlMeansDenoising`) → CLAHE local contrast → optional
adaptive-threshold binarization.

Binarization is **on by default for machine print, off by default for
handwriting** -- binarizing the 1827 will destroys the faint pen-pressure
gradient that carries information about stroke direction, which both
classical and neural recognizers use; it helps machine print by sharpening
edges and normalizing faded photocopy toner.

**Concrete, unexpected finding: binarization is not universally safe, and
its effect is engine-dependent, not document-dependent.** Running the same
binarized version of the litigation page through both engines:

- PaddleOCR: word-spacing improved very slightly (32 detected lines vs 31)
  -- binarization helped, as expected for dense justified machine print.
- Docling: got *worse* -- the layout model misclassified part of the
  binarized page as a picture region (a stray `<!-- image -->` tag
  appeared where real list content used to be), and character-level errors
  appeared that weren't present on the grayscale input ("III." became
  "II1.", "(B)" became "(8)"). Binarizing changed what the layout model
  perceives as "text" vs "picture," not just what the recognizer sees.

Practical consequence: don't apply one fixed preprocessing recipe across
engines. If you're using a layout-aware tool (Docling, or anything that
does region classification before recognition), test binarization on a
sample page before turning it on in a pipeline -- it can silently drop
content rather than just blur character edges.

A second, smaller finding from building `make_redaction_test.py`:
**adaptive thresholding can visually hollow out a solid redaction bar**
(compare `documents/redaction_test/manafort_p3_degraded.png` to
`documents/preprocessed/manafort_p3_clean.png`) -- a large uniform black
region has no local contrast for `adaptiveThreshold` to key off, so it
gets rendered as an outlined box rather than a solid fill. This didn't
cause either OCR engine to hallucinate text inside the box in this test,
but it's a real, easy-to-miss failure mode: an adaptive-threshold step
inserted upstream of a human redaction-QA review could make a bad
redaction look like a good one, or vice versa.

## Recommended pipeline

No single engine wins across all four failure modes named in the question
(low-quality scans, handwriting, multi-column layouts, redactions). Route
by document type:

**1. Triage every incoming page first.** Cheap heuristic: run
`scripts/preprocess.py` with deskew+denoise+CLAHE only (no binarization),
then run PaddleOCR. If avg. confidence is high (>0.9) and word shapes look
like a dictionary, it's machine print -- proceed on the fast path. If
confidence is low and/or the page is visibly cursive, route to the
vision-LLM path. This test's own numbers support the threshold: 0.99 vs
0.75 on the two documents.

**2. Machine-printed legal documents (filings, memos, correspondence):**
Preprocess (deskew, denoise, CLAHE; test binarization on a sample before
enabling it) → **PaddleOCR (PP-OCRv6)**. It was fast (~90-95s/page on a
CPU-only machine, no GPU needed), essentially verbatim-accurate on real
dense legal text with footnotes and nested outlines, and -- importantly --
did not hallucinate content under the redaction bar. If you need
structure-aware output (headings/lists/tables for downstream RAG or
search indexing) layer **Docling** on top, but treat its markdown as a
second opinion, not a source of truth: cross-check against the raw
PaddleOCR line output before trusting reconstructed spacing, and watch for
silently dropped regions (see the phantom `<!-- image -->` tag above).

**3. Handwritten and historical documents:** Neither classical/CNN-based
engine tested here (PaddleOCR, Docling+RapidOCR) is usable on real period
cursive -- both produced majority-garbled or near-total-failure output on
the 1827 will. Use a **multimodal vision LLM** (this test used Claude
directly; GPT-4V/Gemini would be reasonable substitutes) as the primary
engine for anything handwritten. It correctly leaned on legal-boilerplate
priors to disambiguate messy strokes ("maketh Oath and saith that he will
well and truly administer") the way a human paralegal would. It has no
calibrated confidence score, though, so **every vision-LLM transcription
of a legally load-bearing handwritten document (names, dates, dollar
amounts, dispositive clauses) needs a human to check it against the source
image line-by-line before it's relied on** -- this test did not have an
independent ground-truth transcription to check its own output against
either (see Limitations), which is exactly the risk being flagged.

**4. Redactions:** all three working candidates (PaddleOCR, Docling,
vision-LLM) handled a solid black redaction bar correctly in this test --
none hallucinated invented text underneath it, all either skipped the
line or explicitly flagged it. That is a real, positive result, but it
was tested against exactly one redaction style (full-line solid black
bar) on one page. It says nothing about partial redactions, redactions
that don't fully cover ascenders/descenders, or the Manafort-lawyers
failure mode (a black bar drawn over text without deleting the underlying
text in the PDF's copy-paste layer) -- that last one isn't an OCR problem
at all, it's a redaction-tooling problem, and no OCR engine would catch
it; you'd want a tool like DocumentCloud's "Bad Redactions" checker
(which inspects the PDF text layer directly) as a separate step before a
document ever gets rasterized for OCR.

**5. Multi-column layouts:** not directly tested (see Limitations --
neither real source document available in the time budget was cleanly
two-column). Docling's layout model is the more defensible choice here in
principle, since it does region detection before recognition, but this
claim is untested by this submission and should not be taken on faith.

## What failed

- **Docling + RapidOCR on cursive handwriting essentially did not work**:
  162 characters of word-salad output from a full page of legible cursive,
  plus a hallucinated CJK character. Worse than PaddleOCR on the same
  page, worth knowing if you were about to default to Docling because it
  gives nicer structured output on machine print.
- **PaddleOCR on cursive handwriting was legible-effort but not usable**:
  it segmented lines correctly and got some short common words right
  ("of", "the", "and"), but multi-letter words were frequently wrong in
  ways a downstream NLP step could not silently correct
  ("Suprene"→Supreme, "touth"→South, "personilly"→personally). Not safe
  to use unreviewed for anything legally load-bearing.
- **Two real installation-friction bugs hit and fixed, not glossed over**
  (both real, both reproducible on this Windows machine, documented in
  the scripts themselves):
  - PaddleOCR's default oneDNN (mkldnn) CPU kernel threw
    `NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support
    [pir::ArrayAttribute<pir::DoubleAttribute>]` on this machine's
    paddlepaddle build. Fixed with `enable_mkldnn=False`
    (`scripts/run_paddleocr.py`).
  - Docling's first run failed with `OSError: [WinError 1314] A required
    privilege is not held by the client` while trying to symlink cached
    model files -- a Windows-specific huggingface_hub issue (this account
    lacks the "Create symbolic links" privilege, i.e. Developer Mode is
    off). Fixed by setting `HF_HUB_DISABLE_SYMLINKS=1` before running.
    Worth knowing before deploying either tool to a Windows fleet.

## Chandra 2 (attempted)

`chandra-ocr[hf]` installed cleanly (`pip install "chandra-ocr[hf]"`,
`chandra_ocr-0.2.0`) and imports fine. It was not run to completion, and
that decision is disclosed rather than papered over:

- Chandra 2 is a 9B-parameter vision-language model (~8GB download on
  first run). Its HF backend needs roughly 8-12GB of VRAM for reasonable
  inference speed.
- This machine's GPU (RTX 2080, checked with `nvidia-smi`) has 8GB total
  and **5.4GB free**. The torch actually installed in this environment
  (pulled in as a dependency of `docling`) is `2.13.0+cpu` -- CPU-only,
  confirmed with `torch.cuda.is_available()` returning `False`.
- Getting Chandra 2 genuinely running would require reinstalling a
  CUDA-enabled torch build (risking a dependency conflict with the
  already-installed CPU build docling depends on) and would still be
  short on VRAM for the 9B model even then; a CPU fallback for a 9B VLM
  would be minutes per page at best, unbudgeted for a session already
  spending real time on document sourcing.
- Rather than either skip Chandra 2 silently (contradicting the question's
  request to test it) or force a slow/likely-OOM run and report a
  meaningless number, the honest call was: attempt install and diagnostics
  (done, both real), don't force inference under these constraints, and
  report the actual GPU/torch numbers above so the reader can judge for
  themselves whether Chandra 2 is viable on their own hardware. On a
  machine with a GPU that actually has 12GB+ free VRAM, or via Chandra's
  vLLM server mode, this would be the first candidate to add in a
  follow-up pass -- Datalab's own published benchmarks claim the highest
  accuracy of any tested engine on tables/forms/handwriting, which is
  exactly this test's hardest category, and that claim is untested here,
  not refuted.

## How to run this yourself

```bash
python -m venv .venv && source .venv/Scripts/activate   # or .venv/bin/activate on Linux/Mac
pip install opencv-python-headless pillow numpy pymupdf paddlepaddle paddleocr docling

# preprocess
python scripts/preprocess.py documents/raw/will_1827_probate.png out.png
python scripts/preprocess.py documents/redaction_test/manafort_p3_degraded.png out2.png --binarize

# run candidates
python scripts/run_paddleocr.py documents/raw/will_1827_probate.png results/paddleocr/will_raw
python scripts/run_docling.py documents/raw/will_1827_probate.png results/docling/will_raw
```

## Limitations

- **No independent ground-truth transcription.** The "correctness" claims
  for the vision-LLM transcript of the 1827 will are judged by the same
  model family doing the rest of this assessment reading its own output
  against the image -- there's no independently published transcription
  of this exact document to check against. Cross-checking PaddleOCR/Docling
  output against the vision transcript is a real, useful comparison
  (three independent methods substantially agreeing on most of the machine
  print is meaningful corroboration), but the will's transcript should be
  read as "the best attempt available in this session," not verified
  ground truth.
- **Multi-column layout was not tested with a real document.** Time spent
  locating real, freely-downloadable hard scans (LOC, NARA, FBI Vault,
  MuckRock, DocumentCloud, and CourtListener all either bot-blocked
  scripted access with Cloudflare/JS challenges, or the documents found
  turned out to be born-digital with clean text layers rather than actual
  scans) ran out before a genuinely two-column real legal scan was found
  and verified. This is a real gap, not a skipped step -- see Reflection.
- **The redaction test is synthetic-on-real, not a naturally occurring
  redacted scan.** The redaction bar and scan degradation applied to the
  Manafort page are disclosed and scripted (`scripts/make_redaction_test.py`)
  precisely so this isn't mistaken for an authentic redacted production.
- **Only one page per document was tested per candidate**, not a
  statistically meaningful sample. Timing numbers (90s/page etc.) are
  single-run wall-clock, not averaged.
- **Chandra 2 was not actually run** -- see above.

## Reflection

**Weakest remaining claim.** The 1827 will's vision-LLM transcript
(`results/vision/will_1827_probate.md`) is presented as the closest thing
this submission has to "ground truth" for judging PaddleOCR and Docling on
handwriting, but it was produced by the same model family writing this
README, reading its own work, with no independent source to check it
against. If a specific word in that transcript is actually wrong, nothing
in this repo would catch it -- there's no second, disinterested transcriber
and no published transcription of this specific document to diff against.
Someone could catch this by finding an independent transcription (e.g. if
the NSW State Archives or a genealogy society has cataloged this exact
probate file) and diffing it against `results/vision/will_1827_probate.md`
line by line.

**Most consequential design decision.** Building a synthetic redaction bar
and synthetic scan degradation onto a real document (`scripts/
make_redaction_test.py`) rather than only using naturally-occurring hard
scans. The alternative was to keep hunting for a single real, freely
downloadable document that already had genuine redactions, multi-column
layout, low scan quality, and was confirmed non-bot-walled -- several
candidates were tried (Library of Congress, National Archives Catalog,
FBI Vault, MuckRock, DocumentCloud) and every one either blocked scripted
access with a Cloudflare/JS challenge or turned out to be born-digital
with a clean text layer rather than an actual scan. I rejected continuing
that search because it was consuming turns with no guarantee of success,
and chose instead to build a fully disclosed, scripted, reproducible
degradation of a real document's real content. The risk of that choice is
exactly finding #2 from the second audit pass: the script's own comments
initially misdescribed which line got redacted (said "III" when the code
actually draws over "II") -- a self-authored test fixture can drift from
its own documentation in a way a found-in-the-wild document can't. That's
now fixed and re-verified against the actual pixels, but it's a real cost
of the approach, not a hypothetical one.

**What was actually verified vs. asserted.** Actually run and inspected:
`scripts/preprocess.py` and `scripts/make_redaction_test.py` on both real
source images, with output images re-opened and visually inspected (not
just "ran without error"); `scripts/run_paddleocr.py` and `scripts/
run_docling.py` on all three test images, with the resulting `.txt`/`.md`
files read in full and individually compared word-for-word against the
source images by re-reading the images myself; `nvidia-smi` and a live
`torch.cuda.is_available()` check for the Chandra 2 section's hardware
numbers, run at the time those claims were written and re-run by an
independent audit subagent afterward. Two rounds of adversarial audit by
fresh subagents with no prior context, each re-running scripts from a
clean shell rather than trusting the diff. Never verified: Chandra 2's
actual OCR output (declined to run under the observed VRAM/CPU-torch
constraints -- see above); any document beyond one page per source PDF;
multi-column layout on a real document (no suitable real source was
found and confirmed in time); whether the vision-LLM transcripts are
correct against an independent ground truth (see weakest claim, above).

**With another 30 minutes:** get a real multi-column legal document. The
cleanest path found but not pursued to completion was rendering a
two-column law-review-style page or a real multi-column government form
(e.g., a two-column FOIA log or a two-column immigration form, both of
which exist as genuinely scanned public documents on .gov sites without
Cloudflare bot walls, unlike LOC/NARA/FBI Vault) -- that closes the one
failure mode from the original question (multi-column layout) this
submission never actually tested, which is a bigger gap than any polish
pass on the two documents already covered.
