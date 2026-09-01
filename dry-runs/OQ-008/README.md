# Legal-Markdown (OQ-008)

An open standard specification plus a working reference implementation
for one concrete legal-drafting workflow: **contract drafting with
stable-anchor section numbering, margin paragraph numbering, validated
cross-references, defined-term tracking, and footnotes.**

- **`spec/SPEC.md`** — the actual answer to the question: what a legal-markdown
  standard needs to cover, and a section-by-section justification of why
  CommonMark, Pandoc, and HTML+CSS each fall short of it. Start here.
- **`spec/PAGINATION-FINDINGS.md`** — two findings about HTML+CSS's paginated-media
  gaps, obtained by actually generating a PDF from this implementation's own
  output and inspecting it, not by asserting from documentation.
- **`lmd/`** — the reference compiler (Python).
- **`examples/contract.md`** — a full mutual NDA exercising every implemented
  feature.
- **`tests/`** — 20 pytest tests, run and passing (see "Verification" below).

## Quick start

```
pip install -r requirements.txt
python -m lmd build examples/contract.md -o out/contract.html
```

Open `out/contract.html` in a browser. To see the print-paginated version
(running header, "Page N of M" footer), print the page to PDF from the
browser, or use a headless-Chromium tool that calls `page.pdf()` — see
`spec/PAGINATION-FINDINGS.md` for exactly how this was verified.

Run the tests:

```
python -m pytest tests/ -v
```

## The source syntax (`lmd`, a legal-markdown dialect)

```markdown
---
title: Mutual Non-Disclosure Agreement
numbering_scheme: [decimal, decimal, alpha-lower, roman-lower]
page:
  size: Letter
  margin: 1in
  header: "Mutual Non-Disclosure Agreement"
---

# Confidentiality {#confidentiality}

The Recipient shall protect the [Confidential Information]{.def}...

## Standard of Care {#standard-of-care}

...as described in [[ref:confidentiality]].
```

- **Headings** (`#` .. `####`) are numbered automatically per the document's
  `numbering_scheme` (default: `1`, `1.1`, `1.1(a)`, `1.1(a)(i)`), computed
  top-to-bottom — never typed by hand.
- **`{#id}`** after a heading pins its stable anchor explicitly. Without one,
  an anchor is slugified from the title. The anchor never changes when
  sibling sections are reordered; only the rendered number does — this is
  the specific property tested in `tests/test_stability.py`.
- **`[[ref:id]]`** is a validated cross-reference: it renders as "Section
  {current number}" and the build fails with a file/line diagnostic if
  `id` doesn't exist anywhere in the document.
- **`[Term]{.def}`** marks a defined-term declaration; **`[Term]{.term}`**
  marks a usage, rendered as a link back to its definition. A `.term` with
  no matching `.def` anywhere in the document fails the build, as does
  defining the same term twice.
- **`[^n]` / `[^n]: ...`** footnotes use Python-Markdown's standard
  footnote syntax.
- Margin paragraph numbers (the left-margin `1, 2, 3…` next to each body
  clause, independent of section numbering) are pure CSS counters in
  `lmd/templates/page.html` — no Python involved, and no anchor/validation
  concept either, which is exactly the point: that's the part of the model
  HTML+CSS is actually good at (see SPEC.md section 2).

## What this does NOT implement

Scoped out for this submission, and listed here rather than silently
dropped (see SPEC.md section 4 for the full accounting):

- **Pleading-format per-line numbering** (court filing paper, 28
  numbered lines/page) — a page-relative numbering axis that needs a real
  layout/pagination engine, not a browser-print CSS hack.
- **Cross-document / multi-file references** (Exhibit A referencing a
  clause of the Master Agreement it's exhibited to) — the anchor/validation
  model here is single-file only.
- **Redlining / track-changes** as first-class document state (SPEC.md
  section 3.5) — not attempted at all.
- **Conditional clauses and template variables** (SPEC.md section 3.6) —
  not attempted at all.
- **True definition-before-use ordering enforcement** — a `.term` is
  accepted as long as a `.def` exists *anywhere* in the document; it
  doesn't have to appear earlier in reading order. A stricter standard
  might want to flag forward-declared terms.

## Limitations found by actually running this, not assumed

- **Margin numbering renders on screen but is clipped in print.** The
  exact same `out/contract.html`, opened in a normal browser tab, shows
  margin numbers 1-12 (`docs/screenshot-screen.png`). The PDF generated
  from it via Chromium's headless print pipeline does not
  (`docs/screenshot-print-pdf.png`) — the page starts flush left with no
  margin column at all. This was found, not predicted: see
  `spec/PAGINATION-FINDINGS.md` finding 2. It's a genuine problem for a
  feature (pinpoint paragraph numbering) that real contract negotiation
  depends on, and it argues for margin numbering being a renderer-level
  layout primitive in the real standard, not a CSS position hack the way
  this reference implementation does it.
- **Footnotes collect at the document's end, not the bottom of the page
  they're cited on.** Verified by extracting text per PDF page
  (`spec/PAGINATION-FINDINGS.md` finding 3): footnote 1, cited on page 1,
  has its text on page 3. This is the real-world version of the
  documented gap in CSS Paged Media's `float: footnote` (no mainstream
  browser implements it).
- **Numbering convention is fixed, not fully configurable.** `numbering_scheme`
  lets you swap decimal/alpha/roman per level, but the joiner pattern
  (`.` between levels 1-2, parens for 3+) is hardcoded to the common US
  contract convention. A UK-style all-decimal scheme (1.1.1.1) would need
  code changes, not just front-matter changes.
- **No multi-file support at all**, despite SPEC.md section 2's own
  argument that a real standard needs it (Exhibits referencing the Master
  Agreement they're attached to). This reference implementation is
  single-file only.
- **`.term`/`.def` validation doesn't check semantic consistency** — two
  different definitions using different wording for what's clearly meant
  to be the same term (e.g., "Confidential Information" vs. "Confidential
  Info") would not be caught; only exact-string duplicates and exact-string
  undefined usages are validated.

## Security fix from the adversarial audit pass

A reserve-phase adversarial audit (see FAILURE-CLASSES.md item 5 — attack
crafted input, don't just reason about it) found that `title`/`header`
were HTML-escaped before being inserted into the output template, but
three other pieces of user-controlled text were not: heading titles
(`lmd/numbering.py`), defined-term text (`lmd/terms.py`), and front-matter
`page.size`/`page.margin` (`lmd/render.py`). A crafted heading like
`# <script>alert(1)</script> {#s}` or a front-matter value like
`size: "Letter</style><script>alert(1)</script>"` built successfully and
the script tag executed live in the rendered HTML — a real HTML/script
injection, not a theoretical one. All three are now `html.escape()`'d;
`tests/test_escaping.py` reproduces each exact payload and asserts the raw
tag no longer survives. Re-ran the full suite (20/20 passing) and rebuilt
`examples/contract.md` after the fix to confirm nothing else broke.

## Verification actually performed (not just asserted)

- `python -m pytest tests/ -v` — 20/20 passing, including negative cases
  (broken cross-reference, undefined term, duplicate definition, skipped
  heading level, missing source file) that exercise the actual failure
  path, per `FAILURE-CLASSES.md` item 5 — not just happy-path checks.
- `python -m lmd build examples/contract.md -o out/contract.html` — run
  directly, output inspected line-by-line; this caught two real bugs
  during development (raw HTML blocks not receiving Markdown processing
  for the signature block, and a duplicated "Section Section 3" from an
  authoring mistake in the example itself) before they were fixed.
- Real browser verification via Playwright: navigated to the rendered
  HTML, confirmed no console errors beyond a harmless missing favicon,
  took a full-page screenshot (`docs/screenshot-screen.png`).
- Real PDF generation via Chromium's `page.pdf()` (not asserted from
  CSS spec docs), then per-page text extraction with `pypdf` to confirm
  exactly what appears on which page — this is what surfaced the two
  "Limitations" findings above.

## Reflection

**The single weakest remaining claim in what's shipped:** the numbering
algorithm and cross-reference/term validation are tested with pytest unit
tests plus one real end-to-end contract, but there is no large corpus of
varied real-world contracts run through the compiler. The regex-based
`[Term]{.def}` / `[[ref:id]]` parsing (chosen for speed of implementation,
see SPEC.md's Pandoc-span-reuse justification) is the most likely thing to
break on an input more adversarial than the one NDA this was tested
against. This was checked, not just guessed at: a term definition
containing a literal `]` (e.g. `[Odd ] Term]{.def}`) does **not** raise an
error and does **not** truncate the term as I first assumed before
testing it — `python -c` against `lmd.render.build_html` shows the whole
span simply fails to match the regex and passes through as raw,
unrendered `[Odd ] Term]{.def}` text in the final HTML. That's arguably
worse than either a crash or truncation: the document "looks fine" in a
diff but silently contains un-rendered markup syntax, and the term is
never registered as defined, so a later `.term` reference to it would
fail the build with a confusing "never defined" error whose root cause
(a stray bracket three sections earlier) isn't obvious from the message.

**The single most consequential design decision:** doing `.def`/`.term`
substitution as raw-text regex passes *before* handing the document to
`markdown.markdown()`, rather than writing a real Python-Markdown
`Treeprocessor`/`InlineProcessor` extension. The rejected alternative (a
proper Markdown extension) is the more "correct" way to do this and is
what a production version should do — it would let the parser reason
about the actual AST instead of string-matching against Markdown's output
text, which is exactly the class of bug named above. It was rejected here
for the same reason CommonMark itself stayed minimal: within a 90-minute
budget, hooking Python-Markdown's extension API correctly (getting
priority ordering against `footnotes` and `md_in_html` right, handling
nested spans) was a bigger time risk than a regex pass that was fast to
write, fast to test, and easy to reason about for the one workflow this
submission targets.

**What was actually run to verify this works:** `pytest tests/` (20
passing after the audit fix, output above); `python -m lmd build` on the
example NDA with the resulting HTML read back and checked line-by-line
(caught 2 real bugs during development, fixed before this was written); a
real Chromium render via Playwright, screenshotted; a real PDF generated
via `page.pdf()` and its text extracted per-page with `pypdf` to confirm
the footnote and margin-number findings above; a fresh subagent with no
prior context of this build, given explicit instructions to attack the
CLI with crafted input per FAILURE-CLASSES.md item 5 rather than just read
the code, which found a real HTML/script-injection gap (title/header were
escaped, but heading titles, defined-term text, and `page.size`/`margin`
weren't) — confirmed by that agent actually building a `<script>`-bearing
heading and front-matter value and observing it survive live in the
output, then fixed here and re-verified with four new regression tests
(`tests/test_escaping.py`) reproducing the exact payloads. What was never
verified: any document longer than one NDA, any document authored by
someone other than the person who wrote the compiler (so no real "does a
lawyer find this syntax usable" signal), and no performance/scale testing
(documents with hundreds of sections, deeply nested cross-reference
graphs).

**With another 30 minutes:** replace the regex-based `.def`/`.term`/`[[ref]]`
handling with a real Python-Markdown extension (an `InlineProcessor`
registered before the default priority), specifically to fix the
silent-passthrough-on-`]`-inside-a-term bug named above — that's a
correctness bug in the shipped tool, not a missing feature, so it outranks
adding any new §3 feature (redlining, multi-file refs) that's already
honestly scoped out above. Second priority, close behind: a second
adversarial audit pass now that the first one's findings are fixed, since
the fix itself (three new `html.escape()` calls plus one `<style>`-block
value) is exactly the kind of small, easy-to-get-subtly-wrong change that
deserves independent re-scrutiny rather than trusting my own review of it.
