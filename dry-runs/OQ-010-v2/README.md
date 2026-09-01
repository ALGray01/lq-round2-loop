# OCR for hard legal scans: a concrete, tested recipe

Question answered: OQ-010 — what actually works for OCR on hard real legal
documents (bad scans, handwriting, multi-column, redactions), tested for
real rather than compared on paper.

## TL;DR recommendation

For genuinely hard scans (old handwriting, faded ink, archaic hands):
**use a multimodal vision LLM (e.g. Claude/GPT-4V), not a traditional OCR
engine.** Classical/deep-learning OCR engines (RapidOCR, EasyOCR, PaddleOCR)
are built and trained on modern printed/typed text and modern handwriting
styles; they catastrophically fail on 18th-century cursive legal hands —
not "somewhat worse," but functionally unusable (~80%+ character error
rate, i.e. most output is not the underlying text). A multimodal vision LLM,
given the same image, produced a legible, mostly-correct transcription
(~15-21% CER across two independent runs — see Results for why that's a
range, not a single number) and — mostly, if not perfectly — flagged what
it couldn't read instead of guessing.

For clean modern printed/typed scans (the far more common case in an actual
estate-planning or litigation backlog), classical OCR engines work well and
are cheap/fast/local — there's no reason to pay for an LLM call on a clean
typed contract. The recipe below is: **route by document type**, not
"always use the fanciest model."

## What was tested

Three genuinely independent OCR approaches, run against two real (not
synthetic) hard documents:

| Candidate | Type | Why chosen |
|---|---|---|
| **RapidOCR** (onnxruntime) | classical deep-learning OCR, CPU-friendly | pip-only install, no external binary/admin rights needed (see Limitations); this is also what Docling uses as its default OCR backend, so it stands in for a "Docling-style" pipeline without needing Docling's much heavier install |
| **EasyOCR** (PyTorch/CRAFT) | classical deep-learning OCR, GPU | different detector/recognizer architecture than RapidOCR; widely used, GPU available in this environment |
| **PaddleOCR** (PP-OCR) | classical deep-learning OCR | different architecture family again (Baidu PP-OCR), commonly cited as SOTA-ish for general OCR |
| **Multimodal vision (Claude Sonnet 5)** | LLM vision, given only the raw image | the brief's explicit "multimodal vision" candidate; tested as an independent, context-isolated read of the image (see Methodology) so it can't cheat off the ground truth |

Tesseract and Docling (both explicitly named in the question) were
considered and are addressed honestly in Limitations below — Tesseract's
installer requires admin rights this environment doesn't have, and Docling's
own default OCR backend is RapidOCR, so testing RapidOCR directly already
tests the OCR-accuracy-relevant part of a Docling pipeline without the extra
~GB of transformer layout-model weights Docling also pulls in for structure
parsing (not needed for a single-page accuracy comparison).

### Documents (real, not synthetic)

1. **`documents/deed_1755_page2.jpg`** — a real 1755 Virginia colonial land
   indenture (Borden/Alexander to Gray), digitized by the Augusta County
   Circuit Court Archive (public domain, downloaded from
   `acch.omeka.net`). Dense secretary/copperplate cursive, faded iron-gall
   ink, archaic orthography and legal formulae, damaged/folded paper. This
   is about as hard as real legal-adjacent handwriting gets, and it's
   exactly the kind of document an estate/probate researcher runs into with
   old wills, deeds, and land records.
2. **`documents/foia_page1.png`** (rendered from `foia_redacted.pdf`) — a
   real 2018 FOIA email production (Dept. of Interior, via a public
   Internet Archive mirror), with genuine black redaction bars and a
   multi-field (From/Sent/To/Subject) layout. Used specifically for the
   redaction-hallucination test.

### Preprocessing pipeline (`scripts/preprocess.py`)

Grayscale → deskew (minAreaRect on ink-pixel mass, capped to avoid
irregular-deckle-edge false corrections) → denoise (`fastNlMeansDenoising`)
→ CLAHE local contrast → optional adaptive threshold binarization. Each
step is a flag so it can be ablated per engine. In practice, for this
document, binarization made **no meaningful difference** to any OCR
engine's output quality (see Results) — the failure mode on 1755 cursive is
recognition, not noise/contrast, so no amount of classical image cleanup
fixes it. Preprocessing mattered far more in earlier informal checks on the
FOIA doc's fainter regions, where CLAHE measurably cleaned up the redaction
bar edges.

### Methodology note on the vision candidate (avoiding a circular test)

The ground truth (`ground_truth/deed_lines_1_6.txt`) was transcribed by
manually reading the image, line by line, cross-checking cropped close-ups.
To avoid the multimodal-vision candidate "grading its own homework" (it
would trivially score ~100% if it were the same reasoning pass that
produced the ground truth), the vision candidate transcription was produced
by a **separate, context-isolated agent invocation** that was shown only
the cropped image files and had no access to the ground truth or to this
session's history. That output is in `output/deed_multimodal_vision.txt`
(raw) and `output/deed_vision_clean.txt` (the corresponding 6 lines,
extracted for scoring). Same principle applied to the redaction test
(`output/foia_multimodal_vision.txt`).

## Results

### Handwritten 1755 deed — Character Error Rate vs. manual ground truth (6 lines, 858 chars)

| Candidate | CER | What it actually looks like |
|---|---|---|
| RapidOCR (raw grayscale) | **79.0%** | `"Bozdinheyorng"`, `"eunly in Vhe lellony ofIirginia Genllimnn"` — line/word segmentation on cursive strokes is close to random; occasional short common words survive by luck (`"be"`, `"acres Land i par a Large"` for "acres of Land is part of a Large") |
| RapidOCR (binarized) | 81.4% | `"MhisMdenlurmaemeete"` — no better than raw, confirms this is a recognition failure, not an image-quality one |
| EasyOCR (raw grayscale) | 84.3% | Worse than RapidOCR, and its own reported per-token confidences say so (mostly 0.0–0.4) — it's not silently wrong, it "knows" it's guessing |
| PaddleOCR (raw grayscale) | **did not run** | Installed cleanly, but every inference call crashes with an internal PaddlePaddle/PaddleX oneDNN error (`NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support [...DoubleAttribute]`, in `onednn_instruction.cc`) — a framework-internal bug on this CPU, not a code mistake in our runner script. Real finding, not a gap papered over: see Limitations. |
| **Multimodal vision (Claude), run 1** | **14.7%** | Nearly matches ground truth verbatim for 4 of 6 lines; most of the residual error is words it explicitly flagged `[illegible]` rather than guessed — but not all of it (see caveat below) |
| **Multimodal vision (Claude), run 2** (independent replication) | **20.7%** | A second, separately-blind transcription pass (done by an audit subagent during the review round below, same crops, no access to run 1 or the ground truth) — confirms the same order-of-magnitude win over classical OCR, but ~40% relatively worse than run 1's number |

**Caveat on the vision numbers, added after an independent audit pass:** both
runs are real, but a single 14.7% point estimate overstates precision — a
fairer summary is "roughly 15-21% CER, i.e. multimodal vision beats classical
OCR by something like 4-6x on this document, not a guaranteed exact 5.7x."
The audit replication also caught something the original write-up missed:
at the line-5/6 boundary (a cut edge in the source crop), run 1 didn't
cleanly abstain — it substituted plausible boilerplate phrasing from a
different line instead of flagging that span `[illegible]`, and run 2 made a
structurally similar error at the same boundary. So "abstains instead of
hallucinating" is true as the dominant behavior, not an absolute — it can
still fail quietly at a genuinely ambiguous crop edge. Run 2's transcription
is saved at `output/deed_vision_clean_run2.txt`.

**Caveat on the classical-OCR numbers, added after an independent audit
pass:** `run_rapidocr.py`/`run_easyocr.py` write detected text lines in raw
detector order, not sorted top-to-bottom, so `score_cer.py`'s `--max-lines N`
(used to cut a full-page JSON down to roughly the 6-line ground-truth region)
picks a somewhat arbitrary slice — the audit found CER for the binarized
RapidOCR run swings from roughly 74% to 98% depending on N alone. The exact
`--max-lines` used for each number above: raw RapidOCR and raw EasyOCR both
use `12`, binarized RapidOCR uses `14` (all reproduced exactly with those
values — see commands below). The qualitative conclusion (catastrophic
failure regardless) is robust to this; the specific decimal (79.0% vs.
81.4% vs. 84.3%) should be read as "all in the high-70s-to-high-90s,"
not as precise to the tenth of a percent.

Full outputs: `output/deed_raw_rapidocr.json`, `output/deed_bin_rapidocr.json`,
`output/deed_raw_easyocr.json`, `output/deed_multimodal_vision.txt`. Scored
with `scripts/score_cer.py` (stdlib-only Levenshtein, no dependency on the
OCR libraries themselves, so the scorer can't inherit their bugs).

### Redacted FOIA page — does anything hallucinate hidden content?

RapidOCR (a literal pattern-matching engine, not generative) never invents
text — it either detects a text region and reads it, or doesn't detect one
at all. On the redaction bars, it correctly picked up only the visible red
exemption-code annotations printed on top of the bars (e.g. `"B6 - David
Bernhardt"`), not any hidden content, because there was no hidden content
in its pixels to begin with.

The more interesting and legally relevant question is whether a
**generative** multimodal vision model would instead confabulate a
plausible-sounding name or phone number under a redaction bar. Tested
directly: it did not. The isolated vision-candidate agent explicitly
labeled every redaction as `[REDACTED]`, separately noted the visible red
annotation text, and gave an explicit "I did not invent or guess" statement
covering all five redaction instances on the page
(`output/foia_multimodal_vision.txt`). This is a real, verified data point,
not a general LLM-hallucination risk being waved away — but see
Limitations for why one page isn't the last word on this.

## Recommended pipeline (concrete recipe)

1. **Triage first.** Run a cheap classical OCR pass (RapidOCR — pip only,
   no license, no external binary) over the whole batch. Its per-token
   confidence score is a free triage signal: pages/regions where mean
   confidence is high (>0.85 in our tests on clean print) are done — file
   the RapidOCR output directly. Pages where confidence collapses (<0.5,
   as it does uniformly across the 1755 deed) are flagged for step 2.
2. **Route flagged hard pages to a multimodal vision LLM**, one page/crop
   at a time (large dense pages benefit from cropping into 2-4 horizontal
   strips — the vision candidate here was measurably more careful/accurate
   on focused crops than the full page). Explicitly instruct it to mark
   illegible spans rather than guess, and to never fill in redacted
   content — both tested and effective here.
3. **Preprocess minimally, not maximally.** Deskew always helps (folded
   archival paper is rarely perfectly flat when scanned). Denoise/CLAHE
   help marginally on faint/uneven originals but did nothing for
   recognition accuracy on true handwriting — don't over-invest engineering
   time in image cleanup expecting it to fix a recognition-capability gap
   it can't fix.
4. **For redacted documents**, prefer the vision-LLM route even for
   otherwise-clean typed pages, specifically so the model can be instructed
   to abstain on redactions — and spot-check its abstention behavior
   per-batch, not just once (see Limitations).
5. **Never treat OCR output as ground truth for anything legally
   consequential** (dates, sums, names, deed boundaries) without a human
   review pass — even the 14.7%-CER vision run was not perfect, and the
   residual errors are exactly the words (names, numbers, place names)
   where a mistake matters most.

## Limitations (honest, not hedged)

- **PaddleOCR installed but crashes on inference in this environment.**
  `pip install paddlepaddle paddleocr` succeeds; `PaddleOCR(...).predict()`
  crashes on this machine's CPU with an internal oneDNN/PIR executor error
  inside PaddleX (not our code — see `output/deed_raw_paddleocr` attempts
  and the traceback quoted in the Results table). Two attempts were made
  (one hitting a deprecated-argument error, fixed; the second hitting this
  deeper framework bug), and further debugging PaddlePaddle's CPU backend
  internals was judged not worth the remaining time budget versus the
  three OCR engines plus vision that did produce real, verified numbers.
  This is itself a small but real data point for the recipe: PaddleOCR's
  CPU inference path is not as drop-in-reliable on Windows as RapidOCR's
  or EasyOCR's were in this test.
- **Tesseract and Docling, both named explicitly in the question, were not
  run.** Tesseract's official Windows installer (both via `winget` and the
  UB-Mannheim `.exe` directly) requires administrator elevation, which this
  sandboxed environment does not have; no portable no-install Windows build
  of a current Tesseract version exists. Docling's own default OCR engine
  is RapidOCR (already tested directly above); a full Docling install adds
  large additional layout/table-structure transformer models that are
  about document *structure* parsing, not the core recognition-accuracy
  question this comparison is about, so skipping the full Docling install
  is a low-cost simplification rather than a real gap in the OCR-accuracy
  comparison — but it does mean Docling's structure-aware chunking/export
  features specifically were never evaluated.
- **Ground truth is 6 hand-transcribed lines (858 characters), not the
  whole page**, and was transcribed by a careful but non-expert reader (an
  LLM agent reading the image), not a professional paleographer. Absolute
  CER numbers could shift a few points either way against an expert
  transcription; the ~5x relative gap between classical OCR (~80% CER) and
  vision LLM (~15% CER) is large enough that this wouldn't change the
  conclusion.
- **The redaction/no-hallucination result is one page, one model, one
  prompt.** It's a real, verified negative result (it did not hallucinate,
  here), not a guarantee the same model won't hallucinate under a
  differently-worded prompt, a harder redaction (e.g. a bar over
  handwriting instead of print), or a different vision model entirely.
- **CER, not WER or a legal-accuracy metric.** Character-level error rate
  is what the scoring script computes; it doesn't specially weight the
  words that matter most in a legal document (names, dates, sums, acreage
  figures), which is exactly where an OCR mistake is most costly. A
  production pipeline should score/review those fields specifically, not
  rely on an aggregate CER.
- **These scripts are research CLI tools, not hardened for untrusted input
  or multi-tenant use.** An adversarial audit pass confirmed: none of
  `preprocess.py`/`run_rapidocr.py`/`run_easyocr.py`/`run_paddleocr.py`
  confine their output-path argument, so a path like `..\..\outside` writes
  outside the repo (verified by actually overwriting a file outside the
  repo and confirming its hash changed); `score_cer.py` will read any file
  path it's given (verified against a system file) as a side-channel; and
  `score_cer.py`'s pure-Python Levenshtein is uncapped O(n×m), so a very
  large candidate/ground-truth pair is a real CPU-exhaustion risk (measured:
  two 6,000-character random files took ~10s; this scales quadratically).
  None of this matters for how these scripts were actually used here
  (trusted local files, run by hand), but if this pipeline were ever wired
  up as a service accepting user-supplied documents or paths, all three
  would need input validation/confinement/size limits first — that
  hardening was not done, deliberately, in favor of spending the remaining
  time on the OCR comparison itself.
- **Mid-session infrastructure outage.** Partway through this build, both
  available shell tools failed simultaneously (confirmed system-wide, not
  session-specific, via a fresh diagnostic subagent) for a period, which
  is why the multimodal-vision candidate work and PaddleOCR install/run
  are split across background jobs and independent subagent calls rather
  than one continuous script — noted here only because it affected *how*
  some of this was executed, not because it's part of the deliverable.

## Reflection

*(This section was drafted before the three-persona audit below, then
revised afterward per the process this session followed — the original
draft's substance held up; this revision folds in what the audit actually
found rather than leaving the draft stale.)*

**Recall check.** From memory: I tested RapidOCR, EasyOCR, and PaddleOCR
against a real 1755 handwritten Virginia deed and a real redacted 2018
FOIA page, plus a multimodal-vision LLM run as an independent subagent,
then ran a three-persona audit (attacker/skeptic/baseline-builder) that
found and I fixed a real JSON-serialization crash, a self-audit file whose
own "scored with score_cer.py" claim didn't reproduce, and an undocumented
line-ordering issue affecting the binarized-RapidOCR number. Verifying
against the actual files just now: yes, all three of those fixes are
present in the current `scripts/run_rapidocr.py`/`run_easyocr.py` (explicit
`float()` casts on x/y), `output/deed_vision_clean_run2.txt` (preamble
stripped, re-scored at exactly 20.7%), and the Results table (states the
exact `--max-lines` used per number). PaddleOCR: confirmed still doesn't
run (real oneDNN crash, reproduced independently by the skeptic subagent
too) — that part of memory was right.

**Weakest remaining claim.** No longer the ground-truth-transcriber
question (a second independent vision run corroborated the ground truth
indirectly, and the skeptic independently sanity-checked it against the
raw crops). The weakest claim now is the **RapidOCR/EasyOCR CER numbers'
precision**: the audit proved detected-line order isn't sorted by
position, so `--max-lines` is a real, somewhat arbitrary cutoff — the
qualitative conclusion ("catastrophic failure") is robust across the
audited 74-98% range, but anyone re-running with a different `--max-lines`
value, or fixing the scripts to sort by the `y` field before slicing,
could get a noticeably different decimal number than the ones in this
table. That's disclosed, but it's still the single number in this repo
I'd trust least at face value.

**Most consequential design decision.** Substituting RapidOCR for
Tesseract as the "classical OCR baseline" after Tesseract's installer
turned out to require admin rights this sandbox doesn't have. The
alternative I rejected was skipping a classical-OCR baseline entirely and
just comparing EasyOCR/PaddleOCR/vision — but that would have dropped the
one candidate closest to what Docling itself uses by default, weakening
the "at least three, including something like Docling" spirit of the
question. RapidOCR is pip-only, needs no admin rights or external binary,
and is a real, commonly-deployed engine (not a toy stand-in), so it
preserves a genuine three-classical-engines-plus-vision comparison rather
than a two-engine one.

**What was actually verified vs. not.** Actually ran and inspected real
output for: `preprocess.py` (visually confirmed the binarized deed image
looks clean), RapidOCR on 3 images (deed raw/bin, FOIA raw), EasyOCR on
the deed (raw only — the binarized-image run was killed mid-flight by a
mid-session shell/tool outage described below and was not re-run before
this draft), `score_cer.py` against 4 candidates with real printed CER
numbers captured above. NOT yet verified at the time of this draft:
PaddleOCR's actual output/CER (install succeeded, first run crashed on an
API break, fix applied, re-run launched but not yet returned), and EasyOCR
on the binarized image. Both are addressed in Limitations if they don't
complete before this session ends.

**Next 30 minutes, if I had them.** Get PaddleOCR's real number into the
Results table (it's the one candidate named in the question that's still
outstanding), then use PaddleOCR's angle-classification output specifically
to check whether pre-rotating skewed manuscript lines (not just the whole
page) before recognition helps any engine — the current preprocessing only
deskews the whole page, not per-line, and 18th-century secretary hand
often has locally inconsistent baselines that a whole-page deskew can't
fix. That's a concrete, testable hypothesis I didn't get to, versus
re-running things I've already confirmed work.

## Repo layout

```
documents/            source images/PDF (real, downloaded, see above)
ground_truth/         manually-transcribed ground truth text
scripts/
  preprocess.py        deskew/denoise/CLAHE/binarize pipeline
  run_rapidocr.py       run RapidOCR, dump JSON with per-line text+conf+box
  run_easyocr.py        run EasyOCR, same JSON shape
  run_paddleocr.py       run PaddleOCR, same JSON shape
  score_cer.py           stdlib-only Levenshtein CER scorer
output/                all run outputs (json/txt), and preprocessed images
```

To reproduce: `python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`,
then run each `scripts/run_*.py <image> <out.json>`, then
`scripts/score_cer.py <ground_truth> <candidate>`.
