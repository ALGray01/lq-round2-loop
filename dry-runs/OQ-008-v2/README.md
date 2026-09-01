# Legal Markdown (LMD)

An open-standard spec for a legal-markdown format, plus a reference
implementation for one concrete workflow: contract drafting with
hierarchical clause numbering, margin numbers, footnotes, defined-term
tracking, and stable cross-references.

- **`SPEC.md`** — what a legal-markdown standard needs to cover that
  CommonMark, Pandoc, and HTML+CSS each fall short on, and why each falls
  short structurally rather than incidentally.
- **`lmd/GRAMMAR.md`** — the concrete syntax this reference implementation
  parses.
- **`lmd/`** — the reference implementation (pure Python 3.10+ stdlib, no
  dependencies).
- **`examples/services-agreement.lmd`** — a realistic MSA exercising every
  feature (definitions, 4-level numbering, cross-refs, footnotes, signature
  block).
- **`examples/broken.lmd`** — a fixture with 6 deliberately planted errors,
  used to prove the linter actually rejects bad input and not just accepts
  good input (see Verification below).
- **`tests/test_lmd.py`** — 22 pytest tests, including negative cases
  against `broken.lmd` and an HTML-escaping/XSS check against hostile
  input.

## Quick start

No installation step — pure standard library.

```
python -m lmd lint examples/services-agreement.lmd
python -m lmd build examples/services-agreement.lmd -o out.html
python -m lmd model examples/services-agreement.lmd   # resolved doc model as JSON
python -m pytest tests/ -q
```

Open `out.html` in a browser to see numbered sections, margin clause
numbers, linked defined terms, resolved cross-references, and footnotes.

`lmd lint` exits non-zero if there are errors (undefined term/cross-ref
references, duplicate ids, redefinitions, dangling footnote refs, a
signature block with no parties). `lmd build` refuses to write output when
lint errors are present unless you pass `--force`.

## What "legal-markdown" needs that Markdown doesn't (short version)

Full argument in `SPEC.md`. In one paragraph: legal documents need (1)
multi-level numbering where the number *is* the clause's citable identity
and must renumber safely, (2) cross-references whose rendered *text*
resolves to the current target label, not just an href, (3) page-relative
margin/line numbers, (4) page-awareness in general (running headers, "see
page 12," signature pages), (5) defined terms as a semantic registry
(lint-able for undefined/unused), not just bold styling, and (6) footnote
citation semantics CommonMark doesn't specify at all. CommonMark has none
of these by design (it's deliberately minimal). Pandoc gets partial credit
on footnotes and *some* cross-referencing, but its cross-ref mechanism
requires dropping into raw LaTeX or a filter, which breaks portability the
moment you need it — the one feature that matters most. HTML+CSS can
genuinely do pagination (CSS Paged Media), but it's a rendering target, not
an authoring format, and its "numbers" live in the rendered CSS box tree,
not as diffable source data — you can't `grep` an HTML file for "which
clause is Section 4.2(b)" the way you can grep LMD source. See `SPEC.md`
§3-5 for the full per-standard argument, including what each standard gets
partially right.

## What the reference implementation actually covers

Of `SPEC.md` section 2's ten needs, this implementation covers: multi-level
mixed-alphabet numbering (decimal / decimal-dotted / alpha-paren /
roman-paren, 4 levels), stable cross-references (`[[ref:id]]` resolving to
the current section label), margin paragraph numbers, defined-term
tracking with a lint pass (undefined-reference errors, unused-definition
warnings, redefinition errors), footnotes (CommonMark-extension-style
`[^label]` syntax, numbered in citation order), and a signature block
directive. Print CSS demonstrates the page-number/running-header model but
was not run through a real paged-media renderer — see Limitations.

Explicitly out of scope for v0.1 (named in `SPEC.md` §8, not silently
dropped): jurisdiction-specific citation formats (Bluebook/OSCOLA),
redlining/blackline diffing, conditional/templated clauses, multi-document
shared term registries, and execution-integrity hashing.

## Design rationale (the short version — full argument in SPEC.md §7)

LMD is specified as a **source language + a document model**, not a
renderer, which is the exact thing `SPEC.md` argues HTML+CSS gets wrong:
`lmd model file.lmd` dumps every resolved clause number, defined term, and
footnote as plain JSON — data you can diff, `grep`, or feed to another
tool — *before* any HTML/CSS rendering happens. The HTML renderer
(`lmd/render_html.py`) is one possible backend, not the standard itself; a
second backend (LaTeX, a different print-CSS dialect) could consume the
same `Document` model.

The single biggest design decision: cross-references (`[[ref:id]]`) resolve
against a **two-pass build** (register all heading ids and their computed
numbers first, then resolve inline references) specifically so a
cross-reference can point *forward* in the document ("subject to Section
9.3" appearing in Section 2), which is completely ordinary in contract
drafting. A single-pass streaming parser (simpler to write) could not
support this without either forbidding forward references (unrealistic for
this document class) or emitting placeholder text and patching it in a
second pass anyway — which is what the two-pass design does directly and
explicitly, at the cost of holding the whole document in memory (a
non-issue at contract-length documents; would matter for something the
size of an code-of-federal-regulations volume, which is out of scope here).

## Limitations (honest)

- **Not a full CommonMark parser.** `lmd/parser.py` supports headings
  (1-4 levels), paragraphs, footnote definitions, and inline
  bold/italic/code. It does **not** support lists, tables, code blocks,
  images, or nested/mixed emphasis edge cases (e.g. `*a**b***`) — those
  fall through as literal paragraph text rather than being rendered.
  Contracts lean heavily on paragraph-and-heading structure so this covers
  the target workflow, but it is a real subset, not "CommonMark plus
  extensions."
- **No escaping mechanism.** A literal `[[` or `[^` in body prose will be
  misparsed as a directive open. Documented in `lmd/GRAMMAR.md`, not
  silently handled.
- **Print/paged-media output was tested against a real renderer, and the
  `@top-center`/`@bottom-center`/`position: running()` part does not
  actually work under Chromium.** This was an open question through most
  of this build (see the Reflection's revision history below) and was
  finally tested directly rather than left as a hedge: `pip install
  weasyprint` installs cleanly but fails at import with `OSError: cannot
  load library 'libgobject-2.0-0'` — WeasyPrint needs a native GTK/Pango
  runtime this machine doesn't have (a real, environment-specific
  installation barrier, not a code defect; see the WeasyPrint docs'
  Windows installation steps for the fix). Headless Microsoft Edge
  (Chromium) *does* work with no extra install and produces a real 5-page
  PDF (`examples/services-agreement.pdf`, committed, generated by
  `msedge --headless --print-to-pdf=...` against the built HTML) with
  correct page breaks and a sensible page count for the document's length
  — so basic pagination (`@page { size; margin }`, natural page-break flow)
  does work. But the page-number/running-header content
  (`@bottom-center { content: counter(page) }`, `@top-center { content:
  var(--running-title) }`, `position: running(running-title)`) does
  **not** render: extracting text from the generated PDF page-by-page
  shows Chromium's own hardcoded date+title print footer (e.g. "29/07/2026,
  16:39 Master Services Agreement") instead, and that footer persists
  unchanged even when passing `--print-to-pdf-no-header` and
  `--headless=new` to suppress it — strong evidence this is Chromium's own
  browser-chrome default output, not this project's CSS, because nothing
  in this project's HTML/CSS emits a timestamp anywhere and the timestamp
  in the output tracks the actual render time across repeated runs.
  Chromium is documented not to implement CSS Paged Media's margin-box
  generated-content model (`@top-center`/`@bottom-center`/`position:
  running()`) at all — only `@page { size; margin }` — so this isn't a bug
  in this project's CSS so much as a real gap between what the CSS
  Paged Media spec allows and what any freely-available renderer on this
  machine actually implements (Prince and AntennaHouse reportedly do
  support it; neither was available to test here). **Net effect: the
  page-number/running-header claim in `SPEC.md` §2.4 does not hold under
  the one real renderer this could actually be tested against**, which is
  a materially more useful (and more honest) answer than the earlier
  "untested" hedge — a production LMD toolchain wanting this feature would
  need to target Prince/WeasyPrint specifically (with its native
  dependencies solved) rather than assume any print-capable browser
  suffices.
- **Margin numbers: a real positioning bug was found by testing against
  Chromium print-to-PDF output, and has been fixed and re-verified the same
  way.** Extracting word-level bounding boxes from
  `examples/services-agreement.pdf` with `pdfplumber` first showed the
  margin-number spans printing in the right order and surviving a real
  page break correctly (confirming §2.3's document-continuous counter
  design is sound), but landing only ~0.3in from the paragraph text —
  much closer than intended. Root cause, found by working through the box
  geometry rather than guessing: `.lmd-margin-number`'s containing block is
  `.lmd-paragraph` (not `body`), and `text-align: right` draws the glyph at
  the box's own *right* edge — so the original `left: -0.9in; width: 0.7in`
  rule put the visible glyph near `-0.9in + 0.7in = -0.2in`, not near
  `-0.9in`, an off-by-the-box's-own-width error compounded by this
  project's `@page` margin and `body` padding both being large and
  stacking. Fixed in `lmd/render_html.py` by (1) switching to
  `right: calc(100% + 0.2in)`, which defines the gap from the box's right
  edge directly and is immune to this class of error regardless of the
  box's width, and (2) shrinking `@page`'s own margin to a small uniform
  value so `body`'s own padding is the single source of gutter width
  instead of two paddings stacking unpredictably. Re-verified the same way
  as the original finding — regenerated the PDF, re-ran the `pdfplumber`
  bounding-box extraction — and every margin number across both pages now
  sits at a consistent, predictable ~0.23in from its paragraph (matching
  the intended 0.2in gap within normal font-metric rounding), not the
  inconsistent-looking-but-actually-arithmetically-explicable gap before.
  What's still not achieved: a true "line numbers near the page edge"
  litigation-pleading layout — the current gutter puts the number close to
  the text, which is realistic for numbered-clause contract drafting (this
  submission's chosen workflow) but not for the page-edge-line-number
  citation format ("page 4, line 17") `SPEC.md` §2.3 also names as a need;
  achieving that specifically would mean deliberately widening the gap
  rather than fixing a bug, and hasn't been attempted. **Update — this was
  attempted and tested, by a round-3 audit pass.** Widening the gap
  (`right: calc(100% + 1.1in); width: 0.3in`) does move the number to a
  genuinely page-edge position (confirmed via the same PDF-render +
  `pdfplumber` bounding-box technique used throughout this project) with
  no clipping. But that's not the real requirement: real litigation
  citation needs one number per rendered *line*, including soft-wrapped
  continuations, and this project's model (`ctx.margin_counter` in
  `lmd/model.py`) increments once per *paragraph* in the pre-render
  document model — confirmed directly against the rendered PDF: a
  paragraph that wraps to 4 visual lines gets exactly 1 margin number, not
  4. This is an architectural gap, not a CSS one: which characters land on
  which visual line is font-metric/box-width information only the
  browser's layout engine has, at render time, which LMD's
  document-model-first design (`SPEC.md` §7) structurally doesn't have
  access to before rendering. `SPEC.md` §2.3 has been updated to name this
  distinction explicitly (clause/paragraph numbers vs. true page-edge line
  numbers) rather than treating "margin numbering" as one need with one
  architecture.
- **Directives (`[[define:...]]`, `[[ref:...]]`, `[[Term]]`, `[^label]`)
  silently misbehave if written inside `**bold**`/`*italic*`/`` `code` ``
  spans**, found by a round-3 attacker audit: pass 1's registry scan
  regex-scans raw block text (so a `[[define:Term|...]]` inside `**...**`
  still gets registered), but pass 2's bold/italic/code rendering doesn't
  recursively parse its contents (so the term's own anchor never actually
  renders) — a later `[[Term]]` reference then links to a nonexistent
  anchor, with no lint warning. Documented in `lmd/GRAMMAR.md` as a
  known limitation (write definitions/cross-references as plain text) —
  fixing it properly would mean making the inline scanner recursive, which
  wasn't attempted at this point in the build given the remaining budget.
- **Two data-integrity bugs found by the round-3 attacker audit were fixed
  and are now covered by regression tests**: front matter `title:` given
  as a YAML-style list (instead of a scalar) used to crash with a raw
  Python traceback instead of a clean error; `parties: Acme Corp` (a
  scalar instead of a `- ` list — an easy authoring mistake) used to be
  silently iterated character-by-character, corrupting both the cover page
  and the signature block with zero lint warning. Both are now rejected at
  parse time with a clear `LmdSyntaxError` (`lmd/model.py`'s
  `_validate_front_matter`).
- **Numbering styles are fixed, not configurable**, per level (decimal /
  decimal-dotted / alpha-paren / roman-paren for levels 1-4). `SPEC.md`
  §6's table marks this as a per-level style choice that's data
  (`NUMBERING_STYLES` in `lmd/model.py`) rather than hardcoded logic, so
  making it front-matter-configurable is additive, not a redesign — just
  not built, to keep the reference implementation to one concrete workflow
  as the brief asked, rather than a general-purpose configurable engine.
- **Footnote numbering is document-continuous only** — no per-page or
  per-section restart, because that needs real pagination (see above).
- **Single-document scope.** No cross-document defined-term consistency
  (e.g., checking that "Agreement" means the same thing across an NDA and
  a related purchase agreement) — noted as an explicit non-goal in
  `SPEC.md` §8.

## Verification performed

- `python -m pytest tests/ -q` — **34** tests pass (22 original + 4 from
  round 1 of the audit below + 4 from round 2 + 4 from round 3), including:
  - positive numbering/cross-ref/footnote-ordering assertions against
    `examples/services-agreement.lmd`;
  - **negative** assertions against `examples/broken.lmd`, which has 6
    deliberately planted errors (undefined term ref, broken cross-ref,
    dangling footnote ref, duplicate heading id, term redefinition,
    signature block with no parties) and 2 warnings (unused term, unused
    footnote) — confirming the linter actually rejects bad input, not just
    accepts good input (`test_broken_fixture_has_exactly_the_six_planted_errors`);
  - HTML-escaping tests that feed `<script>`/`onerror=` payloads through
    heading text, paragraph body text, and defined-term names;
  - regression tests for every issue the audit below found and this repo
    fixed (see Reflection) — the explicit-heading-id XSS (2 attack-payload
    tests + 1 defense-in-depth test bypassing the parser entirely), the
    def-anchor/heading-id namespace collision, invalid footnote labels, the
    empty-explicit-id parser bug, and `lmd model`'s JSON-embedding safety.
- Two full rounds of an independent three-persona adversarial audit
  (attacker / verification-skeptic / baseline-builder, each round using
  fresh subagents with no prior context) were run against this repository.
  Round 1 found and this repo fixed one real security defect (stored XSS).
  Round 2 — instructed to probe the round-1 fix harder and attack the
  validity of the round-1 Pandoc comparison rather than repeat it — found
  and this repo fixed three more real, smaller issues (a namespace
  collision bug, missing footnote-label validation, unsafe JSON output),
  proved the XSS fix holds against new payloads including a falsification
  test (reverting the fix and confirming the regression tests then fail),
  and found the round-1 Pandoc comparison had only tested the weaker of
  two mechanisms `SPEC.md` names — corrected in `SPEC.md` §4 and
  `comparison/README.md`. Full findings are in the Reflection section
  below (not reproduced in full here to avoid duplicating it).
- `comparison/` — the strongest comparative claim this submission makes
  (`SPEC.md` §4, "Pandoc's cross-referencing breaks Markdown portability")
  was tested against real `pandoc 3.10` (and, after round 2, real
  `pandoc-crossref` 0.3.25) binaries, not asserted from memory, with every
  command and output independently re-run by the primary session (not
  just trusted from subagent reports) before being written into `SPEC.md`.
  Net result: the core claim holds, but was corrected to distinguish two
  Pandoc mechanisms that fail differently rather than treating them as one
  — see `comparison/README.md`.
- Manually ran `lmd build`, `lmd lint`, and `lmd model` against both
  fixtures and read the actual HTML/JSON output (not just exit codes) —
  reproduced above in this README's Quick Start section and inspected
  directly during development.
- `lmd build examples/broken.lmd` (no `--force`) confirmed to exit 1 and
  write nothing; `--force` confirmed to still write output while printing
  the errors as warnings to stderr.

- The print-CSS/pagination claim **was** tested against a real renderer
  (headless Microsoft Edge/Chromium print-to-PDF; WeasyPrint could not be
  tested due to a missing native GTK dependency on this machine) — see
  Limitations above and Reflection below for the actual result, which was
  negative for the page-number/running-header portion specifically.

- The margin-number CSS **was** tested against real paginated Chromium
  output too, and a real positioning bug was found and fixed (not just
  "checked and found fine") — see Limitations above for the root cause
  and the fix, and Reflection below.

What was **not** independently verified: a page-edge-line-number
litigation-pleading layout (as opposed to the numbered-clause-contract
style this submission targets and has now verified) — see Reflection.

## Reflection

*(Originally drafted right after the initial build, before any audit —
that draft's honesty is exactly why round 1 found a real bug rather than
rubber-stamping the code. Revised four times since: after round 1's fix,
after round 2, after directly testing the pagination claim, and now once
more (this is a fresh draft pass at low remaining budget, ~33 turns) after
that same testing-not-reasoning approach found and fixed a second real bug
in the margin-number CSS. Current version below.)*

**Recall check.** From memory: I built a pure-Python, stdlib-only compiler
(`lmd/`) for a legal-markdown subset — 4-level mixed-alphabet section
numbering, margin paragraph numbers, footnotes, defined-term tracking with
lint, forward-resolving cross-references via a two-pass parse — then ran
two full rounds of a three-persona adversarial audit (attacker /
verification-skeptic / baseline-builder). Round 1 found one real security
bug (stored XSS via unvalidated explicit heading ids) and confirmed
`SPEC.md`'s central Pandoc claim empirically. Round 2 — specifically
instructed to probe the round-1 fix harder rather than re-run the same
checks, and to attack the validity of round 1's Pandoc comparison rather
than rebuild it — found three smaller real bugs (a heading-id/defined-term
anchor namespace collision, missing footnote-label validation, unsafe
`lmd model` JSON output) and one real gap in round 1's own comparison
methodology (it only tested the weaker of two Pandoc cross-reference
mechanisms `SPEC.md` names). I fixed all four round-2 bugs, corrected
`SPEC.md`/`comparison/README.md` for the methodology gap, and added
regression tests for everything. Checked against what's actually in the
repo: the test count is 30 (22 + 4 + 4), matching `pytest`'s real output;
`git log` shows 5 commits after the initial build+README, one per round-1
fix, round-1 comparison, round-1 Reflection, round-2 fixes, and round-2
comparison correction — matching this account; every file `git status`
reports clean, no leftover scratch files from either audit round. No
corrections needed to this recollection.

**Weakest remaining claim.** No longer the pagination story from `SPEC.md`
§2.3–2.4 — that was the weakest claim through both audit rounds (neither
of the six subagents across the two rounds was tasked with it), so after
finishing round 2 I spent the remaining time testing it directly rather
than leaving it as a hedge. Result: `WeasyPrint` fails to import on this
machine (missing native `libgobject-2.0-0`/GTK runtime — an environment
gap, confirmed by the actual `pip install` + `import` error, not assumed);
headless Microsoft Edge (Chromium) works with no install and produces a
real 5-page PDF (`examples/services-agreement.pdf`, committed) with
correct page breaks — but the `@bottom-center`/`@top-center`/`position:
running()` page-number and running-header CSS does **not** render:
extracting the PDF's text shows Chromium's own hardcoded date+title
footer instead, confirmed to be Chromium's own output (not this project's
CSS) because the timestamp tracks actual render time across repeated
attempts and this project emits no timestamp anywhere, and because the
footer persists unchanged even with `--print-to-pdf-no-header` and
`--headless=new`. That same technique — extract real word bounding boxes
from a real Chromium-generated PDF via `pdfplumber`, don't just eyeball a
browser window — was then turned on the margin-number CSS (§2.3), and it
found a second real bug: numbers were landing only ~0.3in from their
paragraph, not out in the intended gutter, because `.lmd-margin-number`'s
containing block is `.lmd-paragraph` (not `body`), and `text-align: right`
draws the glyph at the box's own right edge — so the original
`left: -0.9in; width: 0.7in` put the glyph near `-0.9in + 0.7in = -0.2in`,
an off-by-the-box's-own-width error. Fixed via `right: calc(100% + 0.2in)`
(which defines the gap directly, independent of box width) plus shrinking
`@page`'s own margin so it stops stacking unpredictably with `body`'s
padding; re-verified the same way (regenerate PDF, re-extract bounding
boxes) and every margin number across both pages of the rebuilt PDF now
sits at a consistent ~0.23in from its paragraph. So the actual weakest
claim now is narrower still: this submission verified a numbered-clause
*contract-drafting* gutter (number close to its paragraph), not a
page-edge *litigation line-number* gutter (`SPEC.md` §2.3 names both as
needs, and only the first has been built and tested here) — widening the
gap to reach genuinely near the page edge, and testing that specifically,
was not attempted.

**Second most consequential finding this session, after the security
fix.** Testing the pagination claim changed it from "unverified, plausibly
fine" to "tested, and wrong in a specific, useful way": Chromium is a
real, freely-available Paged Media renderer, but it does not implement
CSS Paged Media's margin-box generated-content model at all — only
`@page { size; margin }`. `SPEC.md` §6's table and §2.4 now say this
explicitly rather than gesturing at "a correct implementation... should
honor" this CSS. This matters for the standard's own credibility, not just
this implementation's: a legal-markdown standard that specifies
page-number/running-header behavior via bare CSS Paged Media, as this
reference implementation's HTML backend does, is implicitly betting on
Prince/WeasyPrint/AntennaHouse-class tooling being available in the
rendering pipeline — "any browser's print function" is not actually a safe
assumption for that specific feature, which is exactly the kind of
toolchain-fragility critique `SPEC.md` §5 levels at HTML+CSS as a
standard. A future revision of this spec should say so plainly rather than
implying browser print output is a sufficient target.

**Most consequential design decision.** Still the two-pass build (register
all heading/term/footnote ids first, then resolve inline references in a
second pass) to support forward cross-references — unchanged by either
audit round. Worth naming what round 2 added to this picture: the shared
`seen_ids` namespace fix (heading ids and defined-term `def-` anchors now
check against the *same* collision set, not two independent ones) is the
direct structural fix for a bug that existed precisely because those two
id-generating code paths were written independently without a shared
invariant. That's a small but real lesson about the two-pass design's own
blind spot — splitting registration across block-type branches in one
function made it easy to add a second id-generating branch (defined terms)
without noticing it needed to share a namespace with the first
(headings). The fix keeps the two-pass architecture but closes that
specific gap by making the namespace explicitly shared rather than
implicitly assumed.

**Verified vs. not.** Verified by actual execution, this session: all 30
pytest tests; every attack payload either audit round's attacker-subagent
reported, re-run by hand against the real (not a subagent's copy of)
`lmd/` both before and after each fix; round 2's falsification test
independently spot-checked (reverting the fix in a throwaway copy and
confirming the round-1 regression tests then fail) by reading the
skeptic's transcript output directly rather than trusting the verdict
alone; all `comparison/` pandoc and pandoc-crossref invocations re-run by
hand with real, fresh, unedited output before any claim was written into
`SPEC.md`; and, finally, the pagination claim itself — an actual
`pip install weasyprint` attempt and its actual failure, and an actual
headless-Edge PDF with its text extracted and inspected page-by-page,
rather than reasoning about what CSS Paged Media renderers are "supposed"
to do; the margin-number fix itself — real bug found by bounding-box
extraction, real fix, re-verified by regenerating the PDF and re-running
the same extraction; and a third round of the three-persona audit (34
tests now, up from 30), which independently re-derived the margin-number
gap measurement from a fresh PDF regeneration (not just trusted the prior
number), attacked the front-matter parser and found two real
data-integrity bugs (`title:` as a list crashed with a raw traceback;
`parties:` as a scalar silently iterated character-by-character with zero
lint warning — both now fixed and covered by regression tests), and
confirmed by direct execution that true page-edge line numbering is
architecturally out of reach for this document-model-first design, not
just an untried CSS tweak (`SPEC.md` §2.3 now says so explicitly). Not
verified: whether the two remaining documented limitations (directives
inside bold/italic/code; line-vs-paragraph numbering) have any further
edge cases beyond what round 3 found; a fourth audit round was judged
lower value than closing out cleanly, given remaining budget, since round
3's findings (two narrow parser bugs, one architectural clarification) were
smaller in scope than round 1's security bug and about the same scope as
round 2's — no sign of a widening problem, just steadily diminishing ones.

**With another 30 minutes.** Make the inline scanner in `model.py`'s
`render_inline` recursive for bold/italic/code spans, so `[[define:...]]`
etc. work correctly inside them instead of being a documented
known-limitation — that's the one round-3 finding that was documented
rather than fixed, purely because it needs a real (if small) parser
change and remaining budget favored the two cheaper, more severe
data-integrity fixes instead.
asserted from reading the CSS.

should happen.
