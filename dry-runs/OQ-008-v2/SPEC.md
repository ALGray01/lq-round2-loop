# Legal Markdown (LMD): a specification

Status: draft v0.1. Companion reference implementation: `lmd/` in this repo.

## 1. The problem

Lawyers already draft in something markdown-shaped: numbered clauses, bolded
defined terms, footnoted citations, cross-references to "Section 4.2(b)
above." What they don't have is a *portable, diffable, tool-independent
plain-text format* for it — so drafting happens in Word, where numbering is
a native minefield (auto-number fields silently desyncing across edits is
the single most common Word complaint among transactional lawyers), review
happens via Track Changes (a proprietary binary-adjacent diff nobody can
`git diff`), and every downstream tool (redlining, contract analytics, clause
libraries, e-signature) re-parses a `.docx` XML tree instead of reading text.

Markdown solves the plain-text/diffability half of this problem for
software docs. It does not solve it for legal documents, because the two
document classes need genuinely different things from their markup. This
spec identifies exactly what's missing, argues why the three standards
closest to "already solves this" (CommonMark, Pandoc, HTML+CSS) each fall
short for reasons that are structural rather than incidental, and specifies
the subset of features an open legal-markdown standard needs. Section 5
narrows this to the concrete slice implemented as a reference: contract
drafting with hierarchical numbering, margin numbers, footnotes, defined
terms, and cross-references.

## 2. What legal documents need that general prose doesn't

1. **Multi-level, mixed-alphabet hierarchical numbering.** Legal instruments
   number at 3-5 nested levels using a *different counter alphabet per
   level* — decimal (1, 2, 3), then decimal-decimal (1.1, 1.2), then
   lowercase alpha in parens ((a), (b)), then lowercase roman ((i), (ii)),
   sometimes cycling back to uppercase alpha. The numbering is not
   decorative — "Section 4.2(b)" *is* the clause's identity; it's cited by
   that string elsewhere in the same document, in amendments, in litigation
   over the document, in other contracts ("as defined in Section 4.2(b) of
   the Merger Agreement"). Renumbering must be safe: insert a clause at 4.2
   and everything from old-4.2 onward shifts, and every citation to it
   anywhere in the document must shift too.

2. **Stable cross-references, not just links.** A cross-reference in a
   contract renders as prose ("subject to Section 9.3") that must track the
   *current* number of the target through edits, and must survive being
   read on paper (no href, no click) — the rendered text itself must be
   correct. This is a strictly harder requirement than HTML anchors, which
   only need `href` to resolve; the legal case needs the *visible label* to
   resolve too, at every render.

3. **Margin/line numbering independent of paragraph numbering.** Litigation
   documents (pleadings, deposition transcripts, some jurisdictions' court
   filings) require sequential line numbers printed in the margin,
   unrelated to the document's own paragraph/section numbers, that must
   match the paginated, page-broken layout exactly — "page 4, line 17" is a
   citation format in itself, and it only means something relative to a
   fixed page size and font. This is fundamentally a *pagination* feature,
   which text-flow formats (markdown, HTML without a paged renderer) don't
   have because they don't have pages. **This need has two distinct
   sub-cases the reference implementation found (by testing, not
   reasoning) require different architectures, not just different CSS:**
   clause/paragraph margin numbers (one number per drafted paragraph,
   computable entirely from document structure before any rendering
   happens) versus true page-edge *line* numbers (one number per
   soft-wrapped visual line, which depends on font metrics and box width
   that only a layout/rendering engine resolves, at render time). LMD's
   document-model-first design (§7) can do the former — and does, in the
   reference implementation — but structurally cannot do the latter
   without either feeding rendered layout information back into the
   numbering pass (reintroducing the "numbers only exist inside a
   renderer's internal state" problem §5 uses to disqualify HTML+CSS as
   *the* standard) or building a text-layout engine of its own. See
   `README.md`'s Limitations for the concrete evidence.

4. **Page-awareness.** CommonMark and HTML have no concept of a page at
   all — that's a feature for web content and a structural gap for legal
   content, where "see page 12," running headers restating the caption on
   every page, "signature page follows," and exhibit page breaks are
   ordinary requirements. Page-dependent citation is common in litigation
   ("Tr. 45:12", "Ex. A p. 3") and unavoidable in anything meant to be
   printed, filed, or bound.

5. **Defined-term tracking as a first-class semantic, not styling.** A
   contract's Definitions section establishes that "Agreement" means a
   specific thing; every other capitalized use of "Agreement" is a
   *reference* to that definition, not just bold text. This has two
   consequences no prose-markup standard handles: (a) it's a linting
   surface — used-but-undefined and defined-but-unused terms are real bugs
   lawyers currently catch by eye, and (b) it's precedent for cross-document
   consistency in a suite of related agreements (the same defined term
   should mean the same thing across an NDA, a term sheet, and a purchase
   agreement produced from the same deal).

6. **Footnote semantics beyond "a note at the bottom."** Legal footnotes
   (and endnotes) often have citation-specific numbering rules — restart per
   page, restart per section, or run continuously — and Bluebook/OSCOLA-style
   short-form citations that depend on a footnote having been used before
   (ibid., id., supra note 4). CommonMark has no footnote syntax at all
   (it's a per-implementation extension — GFM doesn't have one, Pandoc's,
   PHP Markdown Extra's and MultiMarkdown's all differ slightly), so there
   is no baseline to build citation semantics on top of.

7. **Court/pleading formats.** Many US state and federal courts mandate
   physical layout — numbered lines (see #3), specific caption block
   layout (court name, parties, case number, judge), signature block
   placement, font/margin rules enforced by local rule. This is a
   jurisdiction-specific rendering *target*, analogous to how CSS has
   print stylesheets, but the input vocabulary (who's the caption, what's
   the case number) needs to exist in the source markup, not be inferred.

8. **Conditional/optional/alternative clauses and drafting notes.**
   Real drafting workflows keep bracketed optional language
   (`[if Buyer is a corporation, insert: ...]`), square-bracket placeholders
   for deal-specific terms, and drafter-only comments that must never
   appear in the executed version. This is close to a templating problem,
   but it's *interleaved with the legal structure* — an optional clause is
   still a numbered clause, still participates in cross-references, still
   needs to renumber correctly whether it's included or not.

9. **Redline/blackline semantics.** Contract negotiation is fundamentally a
   diff-and-accept/reject workflow. A markup that's meant to replace
   Word for this needs changes to be representable in the source text
   itself (insertions/deletions as data, not as an external diff tool's
   opinion) so that "here is exactly what changed since the last draft" is
   a property of the document, renderable inline (strikethrough/underline)
   or accepted into clean text.

10. **Execution mechanics.** Signature blocks, notarization blocks, exhibit
    and schedule namespacces that number independently of the main body
    (Exhibit A, Schedule 2.1(b)) but are cross-referenced from it, and
    (for the border case where the standard meets tooling) integrity
    concerns — an executed contract is a specific immutable text a party
    signed, and a legal-markdown toolchain that lets the "same" document
    silently re-render differently after signature is a liability, not a
    convenience.

## 3. Why CommonMark isn't sufficient

CommonMark is deliberately minimal: a precise grammar for the ~15 constructs
common to all markdown dialects, with an explicit non-goal of covering
everything any dialect ever added. That's the right design for its purpose
(an unambiguous baseline other dialects build on) and the wrong shape for
legal drafting:

- **No footnotes**, at all, in the spec. Every implementation that has them
  disagrees on syntax and numbering rules (see §2.6). There is no floor to
  build legal citation semantics on.
- **Ordered lists are single-level, single-alphabet, and disposable.**
  `<ol>` numbering is presentational and implicit — nothing about
  CommonMark's list model gives a clause a stable identity you can cite. A
  renumbered list is just a new list; there's no notion that item "4.2(b)"
  is the *same clause* as it was pre-edit, which is exactly the property
  §2.1–2.2 need.
- **No cross-reference construct.** Links (`[text](url)`) resolve an href;
  they don't have a mechanism for the *visible text* to be computed from
  and stay synchronized with a target's current position — see §2.2's
  "the label itself must be correct" requirement, which CommonMark links
  structurally cannot satisfy without a build step that mutates prose,
  which is out of spec.
- **No page concept, no margin content, no running headers.** These are
  layout concerns and CommonMark is explicitly presentation-agnostic — by
  design it renders to a single flowing HTML fragment with no notion of a
  page ever existing. §2.3–2.4 need pages to exist in the model at all.
- **No semantic term/definition construct.** Bold (`**text**`) is styling.
  There is no way to say "this bold span is *the* definition of this term"
  versus "this bold span is just emphasis," which is exactly the
  distinction §2.5's linting needs.

None of this is a defect in CommonMark — it's optimizing for a different
document class (prose for the web) where none of these are requirements.
The point is that "just use CommonMark" leaves every one of §2's ten needs
unaddressed, not partially addressed.

## 4. Why Pandoc isn't sufficient

Pandoc is the strongest existing candidate — it already has footnotes,
definition lists, a citation/bibliography system (`pandoc-citeproc`), and
(via `pandoc-crossref` and native `\label`/`\ref` passthrough to LaTeX)
some cross-referencing. It gets partial credit on §2.2 and §2.6 that
CommonMark gets none of. It still falls short:

- **Cross-referencing requires falling out of portable Markdown, or
  installing and version-pinning an external filter.** Pandoc offers two
  cross-reference mechanisms, and they fail differently — this text
  originally treated them as one, which a follow-up empirical check (see
  below) found was too strong a claim for one of the two. (1) Native raw
  LaTeX passthrough (`\label{sec:x}` / `\ref{sec:x}`) only resolves
  correctly in the LaTeX/PDF output path; a plain-Markdown `.md` file with
  `\ref{sec:x}` embedded is no longer portable prose — open it in any other
  Markdown renderer (GitHub, a static site generator, a second lawyer's VS
  Code preview) and, depending on the renderer, you either see a literal
  backslash command or the reference silently vanishes (see verification
  below) — never "Section 4.2(b)." (2) The `pandoc-crossref` filter *does*
  resolve correctly directly in HTML output, no LaTeX/PDF step required —
  but it's a separate binary that must be installed and kept version-
  matched to whichever Pandoc release renders the document, everywhere the
  document is ever rendered, and a document written for it degrades to
  visible-but-unresolved citation-style text (`[@sec:x]`) if the filter
  isn't loaded, rather than working standalone. Either way, the reference
  implementation quietly stops being *just* Markdown the moment it needs
  the one feature §2.2 requires — mechanism (1) by breaking portability
  outright, mechanism (2) by adding a mandatory, version-sensitive
  toolchain dependency that plain Markdown never needed.
  **Verified, not just argued — see `comparison/`:** running actual Pandoc
  3.10 (and, for mechanism 2, `pandoc-crossref` 0.3.25) confirms both
  halves of this. Raw `\ref{}` (mechanism 1) is actually understated above
  in one respect — under Pandoc's own default `markdown` reader (not just a
  third-party CommonMark renderer), the unresolved `\ref{}` isn't shown as
  a literal backslash at all, it's silently *dropped*, producing
  grammatically-broken prose with no visible error ("subject to the
  exclusions in Section ."). `pandoc-crossref` (mechanism 2) was *not*
  tested in the first verification pass despite being named in this
  section's prose — a follow-up audit caught that gap, installed it, and
  found it resolves cleanly (`subject to the exclusions in sec. 2.1.`)
  directly in HTML, which is why this bullet no longer describes both
  mechanisms as LaTeX/PDF-bound. The obvious "just use a plain Markdown
  link instead" counter-argument (`[Section 2.1](#sec-exclusions)`) is
  indeed more portable than either Pandoc mechanism, but isn't perfectly
  portable either: strict CommonMark doesn't recognize the `{#id}`
  heading-attribute syntax Pandoc uses to set the target id, so the link
  text still renders correctly but points at an id nothing in the document
  actually has — a dead link rather than garbled text, a real gap but a
  much softer failure mode. Full commands, real (unedited) pandoc output
  for all of this, and the exact caveats are in `comparison/README.md`.
- **No multi-alphabet nested numbering as a document-model concept.**
  Pandoc can auto-number headings (`--number-sections`), but that's flat
  decimal section numbering for the LaTeX/HTML backends; it has no notion
  of "level 3 uses lowercase-alpha-in-parens" the way legal outlines
  require, and heading numbering doesn't extend to inline clause-level
  numbering within a section body at all (§2.1). **Verified:** running
  `pandoc --number-sections` on a real 4-level heading document produces
  `1`, `1.1`, `1.1.1`, `1.1.1.1` — flat decimal at every depth, confirmed
  in `comparison/README.md` §3.
- **No margin numbers or page-relative citation.** Line numbers in the
  margin are not a Pandoc writer feature for any output format; achieving
  them means dropping into raw LaTeX (`lineno` package) or raw HTML/CSS,
  again exiting the portable subset (§2.3).
- **No defined-term semantics.** Pandoc's definition-list syntax
  (`Term\n: definition`) is close in spirit but is a block-level
  structure meant for glossaries/dictionaries, not an inline marker that a
  *later, arbitrary* occurrence of the term elsewhere in flowing prose is a
  reference to it. There's no linting surface for undefined/unused terms
  because Pandoc has no notion that plain prose text can *be* a use of a
  defined term (§2.5).
- **No redlining, no conditional clauses, no court caption model.** These
  are out of scope for Pandoc's document model entirely (§2.8–2.9); nothing
  in its filter/writer architecture is aimed at them, and building them as
  filters still can't add syntax Pandoc's reader doesn't parse in the
  first place.

Pandoc's own philosophy (a converter between formats, extensible via
filters written in Haskell/Lua/any language via JSON AST) is precisely why
it can't be the standard: filters can add *output-side* behavior once
Pandoc has already parsed a document into its AST, but they can't add new
*input syntax* the reader doesn't already tokenize, which is what §2.1-2.3
need at the source level.

## 5. Why HTML+CSS isn't sufficient

HTML+CSS is the only one of the three with a real answer to pagination:
CSS Paged Media (`@page`, `break-before`, running headers via
`position: running()`, `counter(page)`) genuinely can produce page numbers,
margin content, and running headers, and renderers like Prince, WeasyPrint,
and (increasingly) Chromium's print pipeline implement enough of it to be
usable. So HTML+CSS gets the most credit of the three on §2.3-2.4. It still
fails as *the* standard:

- **It's not an authoring format, it's a rendering target.** Nobody drafts
  a contract by hand-writing `<p style="...">` and `@page` rules; you'd
  need a markdown-like source language that *compiles to* styled HTML
  regardless, at which point HTML+CSS isn't the standard, it's one possible
  compiler backend — same as it would be for LMD's own reference
  implementation (§7).
- **Numbering and cross-referencing are still presentation-layer, not
  source-layer.** CSS counters (`counter-increment`, `content: counter(x)`)
  can render "4.2(b)"-style labels, but the *counter value* lives in the
  rendered CSS box tree, not in the source document as data. You cannot
  `grep` a `.html` file for "which clause is Section 4.2(b)" the way you
  can grep an LMD source file for its clause id — the number only exists
  after a CSS engine has laid the whole page tree out. That fails the
  "plain-text, diffable, tool-independent" requirement that's the entire
  reason to want a markdown-shaped format over Word in the first place
  (§1). A `git diff` on the HTML source shows markup churn, not clause
  renumbering.
- **No defined-term or cross-document consistency model.** CSS has no
  opinion on document semantics at all — by design, it's presentation only.
  Nothing prevents (or flags) "Agreement" being used before its
  `<dfn>`-equivalent is declared, because HTML's actual `<dfn>` element
  isn't a registry, it's just a styling hook (§2.5).
- **Fragile, heavyweight toolchain for something meant to be as simple as
  Markdown.** Getting correct paged output requires a real CSS Paged Media
  engine (a full browser or a specialized renderer like WeasyPrint/Prince),
  version-pinned and consistently available to every person in the
  drafting/review chain — a much heavier dependency than "any text editor
  plus a small compiler," which is the whole appeal of a markdown-based
  workflow (§1's Word complaint).
- **No redlining, no conditional clauses.** Same gap as Pandoc, for the
  same reason: these are source-language features, and HTML+CSS doesn't
  specify a source authoring language, only a rendering model.

## 6. What LMD specifies (summary)

An open legal-markdown standard needs, at minimum:

| Need (§2) | LMD mechanism |
|---|---|
| Multi-alphabet hierarchical numbering (1) | Heading levels 1-4 map to a configurable per-level counter style (decimal / decimal-dotted / alpha-paren / roman-paren); counters are document state, recomputed on every build |
| Stable cross-references (2) | Explicit anchor ids (`{#id}`) + `[[ref:id]]` tokens resolved to the *current* rendered label text at build time, not just a link href |
| Margin/line numbers (3) | Per-clause margin numbering, independent counter from the heading numbering, rendered via CSS Paged Media in print output |
| Page-awareness (4) | Print-target output models pages explicitly (page-break control, running header from current section, `counter(page)`). **Tested against real Chromium print-to-PDF: page breaks/count work, `counter(page)`/running-header margin-box content does not render (Chromium doesn't implement that part of CSS Paged Media) — see README.md Limitations.** |
| Defined-term tracking (5) | `[[define:Term|text]]` declares, `[[Term]]` references; both are data (a registry), not styling; a linter reports undefined-reference and unused-definition |
| Footnote semantics (6) | Standard `[^n]` footnote syntax with a specified numbering-scope rule (document-continuous in v0.1) |
| Court/pleading formats (7) | Out of scope for the v0.1 reference implementation; noted as a named extension point (front-matter `caption:` block + a pleading-paper CSS target) — see §8 |
| Conditional clauses (8) | Out of scope for v0.1; noted as an extension point |
| Redlining (9) | Out of scope for v0.1; noted as an extension point |
| Execution mechanics (10) | `[[signature-block]]` directive; exhibit/schedule namespacing out of scope for v0.1 |

Full syntax grammar, and the rationale for which of the ten needs the
reference implementation actually builds versus defers, is in
`lmd/GRAMMAR.md`. The reference implementation (`lmd/`) covers rows 1, 2,
3\*, 4\*, 5, 6, and 10\* (marked rows are partial: row 3's margin numbers
render correctly on-screen but weren't confirmed against a real paginated
layout; row 4's page-break/count mechanism was confirmed against real
Chromium print-to-PDF output but its page-number/running-header content
was not — Chromium doesn't implement that part of CSS Paged Media. See
README.md's Limitations section for exactly what was and wasn't verified,
including the actual PDF this was tested against,
`examples/services-agreement.pdf`).

## 7. Design stance: LMD is a source language, not a renderer

Consistent with §5's critique of HTML+CSS (a rendering target isn't a
standard), LMD specifies:

1. A **source grammar** — plain UTF-8 text, CommonMark-compatible for every
   construct CommonMark already covers (bold, italic, links, plain
   paragraphs), with legal-specific additions as new token types rather
   than repurposed existing syntax (so an LMD file degrades gracefully:
   opened in a plain CommonMark renderer, the legal-specific tokens appear
   as literal bracketed text instead of being silently misinterpreted).
2. A **document model** — a numbering/definition/cross-reference registry
   that's computed once per build and is *data* (inspectable, testable,
   diffable as JSON), not something that only exists inside a renderer's
   internal state. This is what HTML+CSS structurally can't give you
   (§5) and is the reference implementation's `lmd/model.py`.
3. **Output backends** are downstream of the model, and can be plural (this
   reference implementation ships HTML+print-CSS; a second backend could
   target LaTeX or a paginated-PDF renderer directly) — matching how
   CommonMark itself is one grammar with many renderers.

## 8. Non-goals of this spec (v0.1)

Explicitly deferred, not because they're unimportant but because a 90-minute
reference implementation has to pick one workflow (§6's row selection) to
do properly rather than ten shallowly:

- Jurisdiction-specific citation formats (Bluebook, OSCOLA, Neutral
  Citation) — a real standard would need a pluggable citation-style layer,
  analogous to CSL for Pandoc.
- Redlining/blackline as source-level data.
- Conditional/templated clause assembly.
- Multi-document consistency (shared defined-term registries across a deal
  bible of related agreements).
- E-signature / integrity-hash binding of an executed version.

These are named here so the spec is honest about its own scope rather than
silently pretending §2's list is fully solved.
