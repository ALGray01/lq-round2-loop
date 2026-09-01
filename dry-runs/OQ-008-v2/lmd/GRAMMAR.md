# LMD v0.1 concrete syntax

Covers SPEC.md rows 1, 2, 3, 4, 5, 6, 10 (the reference-implementation
slice). Everything not listed here (lists, tables, code blocks, images,
nested inline emphasis edge cases) falls back to being treated as plain
paragraph text — this is a subset of CommonMark plus legal extensions, not
a full CommonMark implementation. See README.md's Limitations.

## Front matter

Optional, must be the first thing in the file:

```
---
title: Master Services Agreement
parties:
  - Acme Corp, a Delaware corporation ("Provider")
  - Globex Inc, a New York corporation ("Client")
effective_date: 2026-01-15
---
```

A restricted YAML subset: `key: value` scalars, and `key:` followed by
`  - item` list lines. No nested maps, no quoting rules beyond literal
text. `title`, `parties`, and `effective_date` are the only keys the
reference implementation gives meaning to (`parties` feeds the
`[[signature-block]]` directive); unrecognized keys are preserved in the
model but otherwise ignored.

## Headings -> hierarchical numbering

```
# Definitions
## Confidential Information {#sec-confidential-info}
### Exclusions
#### Written notice
```

- `#` through `####` are the only 4 levels (Section / Subsection / alpha /
  roman) — a 5th `#####` level is a parse error, not silently accepted,
  because SPEC.md §2.1 only justifies 4 levels for the contract-drafting
  workflow this reference implementation targets.
- Numbering style per level (decimal `1`, decimal-dotted `1.1`,
  alpha-paren `(a)`, roman-paren `(i)`) is fixed for v0.1, not
  configurable from front matter, to keep the reference implementation to
  one concrete workflow as the brief asks — SPEC.md's model marks
  per-level style as data (`model.NUMBERING_STYLES`), so making it
  configurable is a small, explicitly-deferred follow-up, not a redesign.
- An explicit anchor `{#id}` at the end of a heading line sets its
  cross-reference id. Without one, an id is slugified from the heading
  text (lowercase, non-alnum -> `-`). Duplicate ids (explicit or
  slugified) are a lint error. An explicit id must match
  `[A-Za-z][A-Za-z0-9-]*` and is rejected with a syntax error otherwise --
  this is not stylistic pedantry, it's a security boundary: the id is
  placed directly into an HTML `id="..."` attribute and into `href="#..."`
  on generated cross-reference links, so an id containing `"`, `<`, or
  `>` would let a `.lmd` source file inject arbitrary HTML/JS into its own
  rendered output (this was found by an adversarial audit against an
  earlier version of this implementation that validated auto-generated
  slugs but not explicit ids -- see README.md's Reflection).
- A heading's rendered number is the dotted/parenthesized path of its
  ancestors' numbers at each level, e.g. a level-3 heading under section 4,
  subsection 2 renders as `(b)` and its full path (used by cross-refs) is
  `Section 4.2(b)`.

## Paragraphs and margin numbers

Any non-blank, non-directive text block that is not a heading is a
paragraph. Every paragraph gets a sequential margin number (`M1`, `M2`,
...) independent of the heading numbering, rendered in the left margin of
the HTML/print output — SPEC.md §2.3's line/margin-numbering requirement,
demonstrated as a document-continuous counter (true per-page line
numbering needs a paged-media renderer; see README.md Limitations).

Inline formatting inside paragraphs: `**bold**`, `*italic*`, `` `code` ``.

## Defined terms

```
[[define:Agreement|this Master Services Agreement, including all Exhibits and Schedules]]
```

Registers `Agreement` in the term registry with the given definition text,
renders inline as **"Agreement"** at the point of definition, and creates
an anchor other content can link to. A term may only be defined once;
redefinition is a lint error.

```
[[Agreement]]
```

References a previously defined term; renders as plain linked text
(`Agreement`, hyperlinked to its definition in HTML output). Referencing an
undefined term is a lint error (SPEC.md §2.5). A term defined but never
referenced is a lint warning, not an error (some definitions exist for
completeness/future amendments and that's legitimate).

## Cross-references

```
[[ref:sec-confidential-info]]
```

Resolves at build time to the target heading's current rendered path
(e.g. `Section 2.3`). Referencing an id with no matching heading anchor is
a lint error.

## Footnotes

```
The Provider represents it holds all licenses required by law.[^license-rep]

[^license-rep]: See 17 U.S.C. § 101 for the applicable definition of "license" in this context.
```

Standard CommonMark-extension footnote syntax (`[^label]` inline,
`[^label]: text` as its own block, order-independent in the source). A
footnote label must match `[A-Za-z][A-Za-z0-9-]*` (same restriction and
same reason as heading ids above), enforced at the definition site.
Numbering is document-continuous (SPEC.md §2.6 notes real legal drafting
sometimes wants per-page or per-section restart; continuous is the only
scope the reference implementation covers — restart rules need real
pagination, which is out of scope per §4/§8 of SPEC.md). A footnote
reference with no matching definition, or a definition with no reference,
is a lint error/warning respectively (same asymmetry as defined terms:
unused definitions are a warning, dangling references are an error).

## Signature block

```
[[signature-block]]
```

Standalone directive. Renders one signature block per entry in front
matter's `parties:` list, in order. Requires `parties` to be present and
non-empty in front matter; a `[[signature-block]]` directive with no
`parties` defined is a lint error.

## Escaping

None implemented in v0.1 — a literal `[[` or `[^` in body text will be
misparsed as a directive/footnote open. Documented as a known limitation,
not silently handled.

## Directives inside bold/italic/code (known limitation, found by audit)

Do not write `[[define:...]]`, `[[ref:...]]`, `[[Term]]`, or `[^label]`
*inside* `**bold**`, `*italic*`, or `` `code` `` spans. `render_inline`'s
bold/italic/code branches do not recursively parse their contents -- they
escape the raw substring as literal text. But pass 1's registry scan
(`_pass1_registries`) regex-scans raw block text directly, so a
`[[define:Term|...]]` written inside `**...**` *does* get registered (the
term becomes referenceable) even though its own `<strong id="def-...">`
anchor never actually renders anywhere on the page -- a later
`[[Term]]` reference then links to an anchor that doesn't exist, with no
lint warning (the term shows as "used", suppressing the unused-term
check). Write definitions and cross-references as plain (non-bold,
non-italic) text.
