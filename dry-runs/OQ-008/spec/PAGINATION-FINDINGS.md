# Verified findings: what actually happens when you print this through a real browser

SPEC.md section 2 argues, from documentation/general knowledge, that HTML+CSS's
paginated-media story is weaker than it looks. This document replaces that
argument with two things actually observed by generating a real PDF from
`out/contract.html` (Chromium headless, via Playwright's `page.pdf()`,
`printBackground: true`) and inspecting it — not just asserted.

Reproduce with the project running (see README):

```
python -m http.server 8743 --directory out
# in another session: navigate a Chromium instance to
# http://localhost:8743/contract.html and call page.pdf(path=...)
python -c "from pypdf import PdfReader; r = PdfReader('out/contract.pdf'); [print(p.extract_text()[:200]) for p in r.pages]"
```

## Finding 1: running headers, page counters, and pagination itself all work

`@page { @top-center; @bottom-center }` in `lmd/templates/page.html` produced
a real 3-page PDF with "Mutual Non-Disclosure Agreement" as a running header
and "Page N of 3" as a running footer on every page, matching what CSS Paged
Media promises. Screenshot: `docs/screenshot-print-pdf.png`. This part of
the HTML+CSS baseline genuinely works and the reference implementation
relies on it rather than reinventing it.

## Finding 2: margin paragraph numbers vanish in print, though they render fine on screen

The margin clause-numbering (`.lmd-body > p::before`, CSS counters,
`position: absolute; left: -1.6in`) is visible in a normal scrolled browser
tab — see `docs/screenshot-screen.png`, numbers 1-12 down the left margin.
It is **not present at all** in the printed PDF (`docs/screenshot-print-pdf.png`,
same document, same CSS, only the media context differs) — the page starts
flush at "1 Definitions" with no margin column.

This wasn't asserted from documentation; it was found by generating both
renders of the identical file and comparing them. The likely mechanism:
Chromium's print pipeline clips absolutely-positioned content that extends
outside an ancestor's box once that ancestor is confined to the page's
content area, whereas continuous on-screen layout has no such clipping
because the viewport isn't paginated. Whatever the precise mechanism, the
practical result is what matters for the standard: **the same CSS a legal
document depends on for a real, load-bearing feature (margin numbering used
for pinpoint reference during negotiation) behaves differently in the two
output modes a lawyer actually uses (review on screen, sign a printed/PDF
copy)**. That inconsistency is a correctness risk a standard needs to design
around (e.g., by specifying margin numbering as a first-class, renderer-side
layout primitive rather than a CSS position hack), not a rendering nitpick.

## Finding 3: footnotes collect at the end of the document, not the bottom of the citing page

Extracting text per PDF page confirms footnote 1 is cited on page 1
("circumstances of disclosure.¹") but its text ("This definition is
intentionally broad...") appears only on page 3, under a "Notes" heading
after the signature block — not at the bottom of page 1. This is the
concrete version of the claim in SPEC.md section 2 about CSS Paged Media's
`float: footnote` having no mainstream browser implementation: it's not
merely that Chromium lacks the feature, it's that the practical fallback
(python-markdown's standard footnote rendering, collected at the document
end) is what every HTML-based tool actually ships, and it visibly fails the
"footnote at the bottom of the physical page it's cited on" requirement a
court filing or contract sometimes needs.

## What this changes about the spec

Both findings are cited directly in `SPEC.md` section 3.4 and in `README.md`
"Limitations" rather than being separate claims — they're the same
observation (HTML+CSS's paginated-media layer is real but incomplete and
inconsistent across render targets) demonstrated twice, from actual output,
in one reference implementation build.
