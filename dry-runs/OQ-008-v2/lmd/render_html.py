"""Renders a built Document to a self-contained HTML file with print CSS
implementing the page/margin-number model from SPEC.md sections 2.3-2.4.

Honest scope note (see README.md Limitations for the full account): this
was tested against real headless-Chromium print-to-PDF output, not just
read as CSS and assumed correct. Two different results came out of that:
margin numbers (`.lmd-margin-number`) were found, via real PDF
text-position extraction, to render much closer to the paragraph than
intended -- a real bug in the original `left:-0.9in`+`width` positioning
technique interacting with `text-align:right` and this project's own
`@page` margin choice, not a renderer limitation. That's fixed here (the
`right: calc(100% + gap)` technique below) and re-verified the same way:
every margin number now sits at a consistent, predictable offset from its
paragraph. Separately, `@bottom-center`/`@top-center`/`position:
running()` (page numbers, running headers) do NOT render under Chromium at
all -- confirmed to be a real renderer limitation (Chromium doesn't
implement CSS Paged Media's margin-box generated-content model), not
something fixable from this file's CSS.
"""
from __future__ import annotations

from . import model as M

CSS = """
:root { --ink: #1a1a1a; --rule: #ccc; --accent: #7a1f1f; }
body {
  font-family: "Century Schoolbook", Georgia, "Times New Roman", serif;
  color: var(--ink);
  max-width: 8.5in;
  margin: 0 auto;
  padding: 1in 1in 1in 1.5in;
  line-height: 1.5;
  position: relative;
}
h1, h2, h3, h4 { font-weight: bold; }
h1 .lmd-label, h2 .lmd-label, h3 .lmd-label, h4 .lmd-label {
  color: var(--accent);
  margin-right: 0.4em;
}
h1 { font-size: 1.15em; text-transform: uppercase; margin-top: 1.6em; }
h2 { font-size: 1.05em; margin-top: 1.2em; }
h3 { font-size: 1em; margin-left: 1.5em; }
h4 { font-size: 1em; margin-left: 3em; }
.lmd-paragraph {
  position: relative;
  margin: 0.9em 0;
  padding-left: 0.2em;
}
.lmd-margin-number {
  /* right/calc(100% + gap), not left:-<offset>, because this box's
     containing block is .lmd-paragraph (position:relative), and
     text-align:right draws the glyph at the box's own RIGHT edge -- a
     left:-Xin + fixed-width version of this rule was found (via real
     Chromium print-to-PDF text-position extraction, not just visual
     inspection) to place the glyph only ~0.2-0.3in from the paragraph,
     not out in the gutter, because the box's right edge (where the glyph
     actually draws) landed near -Xin+width rather than near -Xin. Using
     `right` sidesteps that class of off-by-width error: the box's right
     edge is defined directly, independent of its width. */
  position: absolute;
  right: calc(100% + 0.2in);
  width: 0.9in;
  text-align: right;
  color: #888;
  font-size: 0.8em;
  font-family: "Courier New", monospace;
  user-select: none;
}
.lmd-term { color: var(--accent); }
.lmd-term-ref { color: var(--accent); text-decoration: none; border-bottom: 1px dotted var(--accent); }
.lmd-ref { color: #1a4a7a; text-decoration: none; border-bottom: 1px dotted #1a4a7a; }
.lmd-broken-ref, .lmd-broken { color: white; background: #b00; padding: 0 0.2em; font-family: monospace; }
.lmd-signature-block { margin-top: 3em; }
.lmd-signature-party { margin-top: 2em; }
.lmd-sig-line { border-top: 1px solid #333; width: 3.2in; margin-top: 2.2em; }
.lmd-sig-label { font-size: 0.85em; color: #555; margin-top: 0.2em; }
.lmd-footnotes { margin-top: 3em; border-top: 1px solid var(--rule); padding-top: 0.6em; font-size: 0.88em; }
.lmd-footnotes li { margin-bottom: 0.4em; }
.lmd-cover { text-align: center; margin-bottom: 2.5em; }
.lmd-cover h1 { font-size: 1.4em; }
.lmd-parties { font-size: 0.95em; color: #333; }

/* Print / paged-media target -- see module docstring for verification status.
   @page's own margin is deliberately small and uniform (not the old
   1.6in-left version): body's own 1.5in left padding is now the single
   source of gutter width. Stacking a large @page margin on top of that
   padding was the root cause of the margin-number positioning bug found
   by testing against real Chromium print-to-PDF output (see README.md
   Limitations) -- it pushed the whole content block, .lmd-margin-number
   included, so far right that the negative-offset margin-number technique
   ran out of room to reach a true gutter position. */
@page {
  size: letter;
  margin: 0.5in;
  @bottom-center { content: counter(page); }
  @top-center { content: var(--running-title); font-size: 9pt; color: #666; }
}
.lmd-running-title { position: running(running-title); }
"""


def _heading_tag(level: int) -> str:
    return f"h{level}"


def render_html(doc: M.Document) -> str:
    title = doc.front_matter.get("title", "Untitled Agreement")
    effective_date = doc.front_matter.get("effective_date", "")
    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en"><head><meta charset="utf-8">')
    parts.append(f"<title>{M.esc(title)}</title>")
    parts.append(f"<style>{CSS}</style></head><body>")
    parts.append(f'<div class="lmd-running-title">{M.esc(title)}</div>')
    parts.append('<div class="lmd-cover">')
    parts.append(f"<h1>{M.esc(title)}</h1>")
    if effective_date:
        parts.append(f'<p class="lmd-parties">Effective as of {M.esc(str(effective_date))}</p>')
    parties = doc.front_matter.get("parties", [])
    if parties:
        parts.append('<p class="lmd-parties">')
        parts.append("<br>".join(M.esc(p) for p in parties))
        parts.append("</p>")
    parts.append("</div>")

    for block in doc.render_blocks:
        if isinstance(block, M.RHeading):
            tag = _heading_tag(block.level)
            parts.append(
                f'<{tag} id="{M.esc(block.id)}"><span class="lmd-label">'
                f"{M.esc(block.local_label)}</span>{block.inline_html}</{tag}>"
            )
        elif isinstance(block, M.RParagraph):
            parts.append(
                '<p class="lmd-paragraph">'
                f'<span class="lmd-margin-number">{block.margin_number}</span>'
                f"{block.inline_html}</p>"
            )
        elif isinstance(block, M.RSignatureBlock):
            parts.append('<div class="lmd-signature-block">')
            for party in block.parties:
                parts.append('<div class="lmd-signature-party">')
                parts.append(f'<p class="lmd-sig-label">{M.esc(party)}</p>')
                parts.append('<div class="lmd-sig-line"></div>')
                parts.append('<p class="lmd-sig-label">By:</p>')
                parts.append('<p class="lmd-sig-label">Name:</p>')
                parts.append('<p class="lmd-sig-label">Title:</p>')
                parts.append('<p class="lmd-sig-label">Date:</p>')
                parts.append("</div>")
            parts.append("</div>")

    if doc.footnotes_in_order:
        parts.append('<ol class="lmd-footnotes">')
        for fn in doc.footnotes_in_order:
            parts.append(
                f'<li id="fn-{M.esc(fn.label)}">{fn.inline_html} '
                f'<a href="#fnref-{M.esc(fn.label)}">&#8617;</a></li>'
            )
        parts.append("</ol>")

    parts.append("</body></html>")
    return "\n".join(parts)
