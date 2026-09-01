# Legal-Markdown: A Specification for Machine-Readable Legal Documents

**Status:** Draft 0.1 — this document plus the reference implementation in
`../lmd/` together constitute the submission for OQ-008. The reference
implementation covers a deliberately narrow slice of this spec (see
"What the reference implementation covers" at the end); the rest of this
document describes the full standard as it should exist, including the
parts not yet built.

## 1. The problem

Legal documents share a document model that is genuinely different from
prose, and every existing "write it as plain text, render it to something
prettier" pipeline — CommonMark, Pandoc's Markdown, or hand-written
HTML+CSS — was designed against the prose model, not the legal one. The
gaps aren't cosmetic. They are the specific places where getting it wrong
produces a contract that misquotes itself, a brief that violates a court's
formatting rule, or an amendment that silently stops matching the section
it purports to amend.

Five properties define the legal document model:

1. **Numbering is semantic and multi-level, and it must survive editing.**
   A contract clause is not "the third bullet" — it is "Section 4.2(b)",
   and that identity has to survive a paragraph being inserted above it
   during redlining. The *number* a reader sees (4.2(b)) and the *identity*
   the document engine tracks (a stable anchor) are two different things,
   and only one of them is allowed to change when the document is edited.

2. **Cross-references are load-bearing, not decorative.** "As defined in
   Section 4.2(b)" is not prose flavor text — if Section 4.2(b) gets
   renumbered to 4.3(a) and the cross-reference isn't updated, the contract
   now contains a false statement of fact about its own structure. This is
   a correctness bug with legal consequences, not a formatting nit.

3. **Defined terms are a namespace, not decoration.** Capitalized quoted
   terms ("Confidential Information", "Effective Date") are declarations
   that create bindings used throughout the rest of the document (and often
   across a family of related documents — an NDA and the master agreement
   it's exhibited to). An undefined-but-capitalized term, or a term defined
   twice with different meanings, is a drafting error a standard should be
   able to catch mechanically.

4. **The page is a real unit, not a CSS afterthought.** Court rules
   frequently specify physical formatting as a matter of procedure — line
   numbering down the margin of every page (California pleading paper: 28
   numbered lines/page), specific margin widths, footnotes that must appear
   at the bottom of the physical page they're cited on (not collected at
   the end of a 40-page HTML scroll), running headers with the case
   caption and page number ("Page 4 of 22"). A contract's "signature page"
   is a real, physical, notarizable object, and "don't let the signature
   block split across two pages" is a hard requirement, not a suggestion.

5. **Redlining/versioning is a first-class document state, not a diff
   tool's side effect.** Legal documents spend most of their life as
   marked-up revisions of a prior version ("Section 3 is hereby amended to
   read in its entirety as follows: ..."). Track-changes markup —
   insertions, deletions, and the authorship/timestamp/comment attached to
   each — is something documents *carry*, not something a diffing tool
   reconstructs after the fact from two independent snapshots.

## 2. Why CommonMark, Pandoc, and HTML+CSS each fall short

None of these is "bad" — each is well-designed for what it targets (web
prose, academic/technical documents, and paginated visual layout,
respectively). The point is that none targets the legal document model
above, and bolting the gap closed with each one's extension mechanism
produces a different, incompatible hack every time — which is itself the
argument for a real, shared standard.

### CommonMark

- No footnotes in the spec at all (every implementation that has them —
  GFM, PHP Markdown Extra — invented its own incompatible syntax).
- No native multi-level ordered-list numbering scheme beyond flat
  `1. 2. 3.`; nothing that expresses "1.1(a)(i)" as a structural concept,
  and no anchor mechanism to reference a specific list item by stable ID.
- No cross-reference syntax of any kind — `[text](#anchor)` exists, but
  the anchor is a raw heading-derived slug, not a semantic ID that survives
  renumbering, and there is no validation that the anchor exists.
- No concept of a defined term, a page, a footnote-vs-endnote distinction,
  or redlining.
- Deliberately minimal by design (its stated goal is an unambiguous spec
  for the subset of Markdown already in wide use) — it is not a gap CommonMark
  failed to close, it's scope CommonMark explicitly excludes.

### Pandoc Markdown

The strongest of the three baselines — it already has footnotes
(`[^1]`), bracketed spans with attributes (`[text]{.class #id}`), and
(via `pandoc-crossref` or native numbered-section support) cross-references
for figures/tables/equations in the academic sense. This is real, useful
infrastructure, and the reference implementation below deliberately reuses
Pandoc's bracketed-span syntax rather than inventing a new delimiter, for
exactly the reason Pandoc invented it: it's already a widely-implemented
extension point, and fragmenting tooling by inventing a fifth incompatible
span syntax would be the same mistake CommonMark's extension-implementations
made with footnotes.

What Pandoc still lacks for the legal case, specifically:

- Cross-references are built for *figures/tables/equations/citations*, not
  for "Section 4.2(b) of this contract, where 4.2(b) is a legal numbering
  scheme, not a figure caption." `pandoc-crossref`'s section-numbering
  support produces decimal numbering (1, 1.1, 1.1.1) — it has no native
  concept of the `(a)(i)` alternating letter/roman legal sub-scheme, and no
  concept of a stable ID that's independent from the rendered number (in
  Pandoc, the anchor *is* the heading slug — renumbering and re-anchoring
  are the same operation, which is precisely the property §1 says must NOT
  be true).
- No defined-term namespace, no first-use/subsequent-use distinction, no
  detection of an undefined term in use.
- No page-oriented output at all on its own — page layout is delegated
  entirely to whatever backend Pandoc targets (LaTeX, HTML+CSS, DOCX), so
  "does it support pleading-paper line numbering" reduces to "does LaTeX or
  Word support it," which is a different question with a different answer
  per backend, i.e. not a property of the format.
- No redlining primitive. Pandoc's own AST has no insertion/deletion node
  type; `git diff` on two `.md` files is a text diff of unrelated snapshots,
  not an author-attributed markup the document itself carries.

### HTML + CSS

The only one of the three with a real answer to "the page is a physical
unit" — CSS Paged Media (`@page`, margin boxes, `counter()`,
`break-before/after/inside`) genuinely models running headers, page
counters, and page-break avoidance. This is real infrastructure the other
two don't have at all, and it's why the reference implementation's own
output is HTML+CSS rather than something further removed from a browser.

Where it still falls short:

- **No document model, only a presentation model.** HTML has no semantic
  distinction between "this `<div>` is a legal Section" and "this `<div>`
  is a sidebar" — you can express *anything* in `<div class="...">`, which
  means an authoring standard built directly on raw HTML has no shared
  vocabulary at all; every author reinvents the semantics via class names,
  and no two documents' "Section" divs are guaranteed to mean the same
  thing or be checkable by shared tooling.
- **No cross-reference validation.** `<a href="#sec-4-2-b">` either
  resolves at render time or silently produces a dead link; nothing in
  HTML/CSS checks at authoring time that the target exists, let alone that
  it still refers to the clause the author meant after a renumbering.
- **CSS Paged Media's footnote support (`float: footnote`, part of the
  GCPM spec) has essentially no mainstream browser implementation** — Chrome,
  Firefox, and Safari do not implement it as of this writing. In practice,
  "print this HTML+CSS document and get real page-bottom footnotes" only
  works via a small number of dedicated non-browser renderers (e.g. Prince,
  Antenna House), which is exactly the fragmentation problem again: CSS
  *specifies* the feature, but "HTML+CSS" as a deployable standard doesn't
  actually deliver it. The reference implementation below hits this
  limitation directly, by generating a real PDF from its own output and
  finding the footnote text collected at the document's end rather than the
  bottom of the page it's cited on, rather than asserting it from
  documentation alone (`spec/PAGINATION-FINDINGS.md`, finding 3). The same
  check surfaced an unplanned second finding (finding 2): CSS-counter margin
  numbering renders correctly in a normal browser tab but is silently
  clipped out of the printed/PDF output of the identical file — its own
  argument for why margin numbering needs to be a renderer-level layout
  primitive, not a CSS positioning hack.
- **No authoring ergonomics.** Nobody drafts a contract by typing
  `<p class="clause">`; CSS's strength is precisely that it's a rendering
  target, not something meant for a lawyer to author directly. A legal
  standard needs a plain-text authoring syntax that *compiles to*
  HTML+CSS (among other targets) — which is the same relationship
  Markdown has to HTML, just aimed at a different document model.

### The shared conclusion

CommonMark is the wrong layer (too minimal, deliberately). Pandoc is the
closest existing thing and the right extension mechanism to build on
(bracketed spans, existing footnote syntax), but its cross-reference and
numbering model is aimed at academic documents, not legal ones, and it has
no defined-term or redlining concept at all. HTML+CSS is the right
*rendering target* for the page/footer/counter half of the problem, but is
not — and was never meant to be — an authoring standard or a
cross-reference-validating document model. An open legal-markdown standard
is therefore not "yet another Markdown flavor"; it's a semantic layer of
legal-specific structure (stable IDs, cross-reference validation, defined
terms, redlines) that *compiles to* Pandoc-family syntax where existing
extension points are reusable, and to HTML+CSS (or a dedicated paginating
renderer) for physical layout.

## 3. What the standard needs to specify

### 3.1 Numbering

- A declared **numbering scheme** per document (front matter), as an
  ordered list of level formats: e.g. `["decimal", "decimal", "alpha-lower",
  "roman-lower"]` → `1.`, `1.1`, `1.1(a)`, `1.1(a)(i)`. Schemes must be
  swappable per document (a UK-style contract's convention differs from a
  US one) without changing the source document's structure.
- Numbering is **derived from document structure at render time**, never
  hand-typed by the author. An author writes nested headings/sections; the
  renderer computes and inserts the numbers.
- Every numbered node gets a **stable anchor ID**, assigned once (either
  explicitly by the author, e.g. `{#confidentiality}`, or auto-generated
  from the first heading text) and never recomputed from the numbering.
  Reordering, inserting, or deleting sibling sections changes the rendered
  numbers of everything after the edit, but never changes any anchor ID.
  This is the single property that makes stable cross-references possible
  at all, and it is the property none of the three baselines has (Pandoc
  and raw HTML both derive the anchor from the heading slug/position, which
  changes when the heading's position or text changes).
- **Margin/paragraph numbering** (every clause paragraph numbered 1, 2, 3…
  in the left margin, independent of section numbering — the convention
  used so negotiating parties can say "strike paragraph 14" during
  redlining) is a distinct, second numbering axis from section numbering
  and must be specifiable independently.
- **Pleading-format line numbering** (every physical line on the page
  numbered 1–28, per California and several other jurisdictions' local
  rules) is a third, page-relative axis: it numbers *rendered lines on a
  physical page*, which by definition cannot be known until layout/pagination
  happens, and therefore must be a renderer-side concern driven by a
  document-level flag, not something the author can number by hand.

### 3.2 Cross-references

- A cross-reference syntax that resolves against anchor IDs (not raw
  headings), e.g. `[[ref:confidentiality]]`, rendered as the *current*
  computed number ("Section 4.2(b)") at build time.
- **Build-time validation is mandatory, not optional:** a reference to a
  nonexistent anchor MUST fail the build with a clear diagnostic (file +
  line), the same way a broken symbol reference fails a compiler. Silently
  emitting a dead link (HTML's behavior) or the literal text (a naive
  templating approach) are both failures of the standard, not acceptable
  degraded modes.
- Cross-document references (Exhibit A of this Agreement referring to a
  clause of the Master Agreement it's exhibited to) need the same anchor +
  validation model extended across files, which implies the standard needs
  a project/manifest concept (which files make up "the deal"), not just a
  single-file spec.

### 3.3 Defined terms

- A definition-site syntax and a use-site syntax, distinguishable from each
  other (first use vs. reference use), e.g. Pandoc-style spans:
  `[Effective Date]{.def}` at the definition, `[Effective Date]{.term}` at
  each subsequent use.
- **Build-time validation:** a `.term` use with no matching `.def`
  anywhere in the document (or in an incorporated exhibit/master
  agreement) must fail the build. A `.def` defined twice with different
  text is a build warning at minimum.
- Auto-generated **defined-terms index/glossary** as a build output (a
  table of term → definition-location, standard in long-form commercial
  contracts).

### 3.4 Page and physical layout

- Front-matter-declared **page geometry**: size, margins, running header
  content (case caption, party names), page-number format
  ("Page N of M").
- **Footnote vs. endnote** as an explicit document-level choice, where
  "footnote" specifically means bottom-of-the-physical-page-of-citation.
  Because this requires knowing pagination, it can only be fully honored
  by a renderer that does real pagination (a browser rendering continuous
  HTML does not paginate at all, and current browsers' `float: footnote`
  support does not exist in practice — see §2). The standard should specify
  the *semantic* distinction and let conformant renderers vary in how well
  they achieve true pagination, the way CSS itself specifies more paged-media
  behavior than browsers implement.
- **Page-break control primitives** at the semantic level: "keep this
  signature block on one page," "always start this Exhibit on a new page,"
  expressed as document intent, not manually inserted blank space.

### 3.5 Redlining

- Insertion/deletion spans as first-class inline markup, each carrying
  author + timestamp (+ optional comment), e.g.
  `{++inserted text++}{--deleted text--}` (borrowing the already-existing
  critic markup convention), so that a document *is* a redline, rather
  than being reconstructed by diffing two independently-authored snapshots.
- A render mode that shows the clean (accepted) version, and one that shows
  the marked-up (all changes visible) version, from the same source file.
- "Amends and restates" semantics: a clause that says "Section 3 is hereby
  deleted and replaced with the following" needs to be a structural
  operation the standard understands (this section supersedes that
  anchor ID going forward), not prose the renderer treats as inert text.

### 3.6 Conditional/template content

- Bracketed optional clauses and fill-in variables for contract templates
  (`{{Party A Name}}`, `[IF governing_law == "Delaware"]...[END IF]`), since
  most real contracts are drafted from a template with deal-specific
  variables and optional clauses, not written from scratch per deal.

## 4. What the reference implementation covers

Given the scope of §3, the reference implementation in `../lmd/` targets
**one concrete workflow**, as the question asks: **contract drafting with
margin numbering, footnotes, and cross-references** — specifically §3.1
(section numbering with stable anchor IDs + margin paragraph numbering),
§3.2 (validated cross-references), §3.3 (defined terms with validation),
and the footnote half of §3.4 (with its real limitation demonstrated, not
asserted — see the README and `spec/PAGINATION-FINDINGS.md`, which also
reports an unplanned second finding: margin numbering itself renders
correctly on screen but is silently clipped in print output).

**Explicitly not implemented** (documented as future work, not silently
dropped): pleading-format per-line numbering, cross-document/multi-file
references, redlining/track-changes, and conditional/template content
(§3.5, §3.6, and the multi-file part of §3.2). These are scoped out for
this submission's time budget, not because they're less important — see
the README's "Limitations" section for the honest accounting.
