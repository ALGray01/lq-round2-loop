"""The LMD document model: numbering, defined-term/footnote/cross-ref
registries, inline resolution, and linting.

This is the "document model as data" piece SPEC.md section 7 argues a
legal-markdown standard needs and HTML+CSS structurally can't give you:
`Document.to_dict()` below is a fully resolved, JSON-serializable snapshot
of every clause number, defined term, footnote, and cross-reference in the
document -- inspectable and diffable without ever invoking a renderer.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from . import parser as P

NUMBERING_STYLES = {
    1: "decimal",
    2: "decimal-dotted",
    3: "alpha-paren",
    4: "roman-paren",
}

_ROMAN_TABLE = [
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
    (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
    (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
]


def to_roman(n: int) -> str:
    if n <= 0:
        raise ValueError("roman numerals only defined for positive integers")
    out = []
    for value, sym in _ROMAN_TABLE:
        count, n = divmod(n, value)
        out.append(sym * count)
    return "".join(out)


def to_alpha(n: int) -> str:
    """Bijective base-26: 1=a .. 26=z, 27=aa, 28=ab, ..."""
    if n <= 0:
        raise ValueError("alpha numbering only defined for positive integers")
    out = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out.append(chr(ord("a") + rem))
    return "".join(reversed(out))


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s or "section"


def esc(text: str) -> str:
    return html.escape(text, quote=True)


@dataclass
class LintIssue:
    severity: str  # "error" | "warning"
    message: str
    line_no: int

    def __str__(self):
        return f"{self.severity.upper()} line {self.line_no}: {self.message}"


@dataclass
class HeadingInfo:
    id: str
    level: int
    text: str
    local_label: str
    full_path: str
    line_no: int


@dataclass
class DefinedTermInfo:
    term: str
    definition: str
    anchor_id: str
    line_no: int
    used: bool = False


@dataclass
class FootnoteInfo:
    label: str
    text_raw: str
    line_no: int
    number: int | None = None
    referenced: bool = False


@dataclass
class RHeading:
    level: int
    local_label: str
    full_path: str
    id: str
    inline_html: str


@dataclass
class RParagraph:
    margin_number: int
    inline_html: str


@dataclass
class RSignatureBlock:
    parties: list[str]


@dataclass
class RFootnote:
    number: int
    label: str
    inline_html: str


@dataclass
class Document:
    front_matter: dict
    render_blocks: list
    headings: dict  # id -> HeadingInfo
    defined_terms: dict  # term -> DefinedTermInfo
    footnotes: dict  # label -> FootnoteInfo
    footnotes_in_order: list  # RFootnote, in citation order
    issues: list  # LintIssue

    def errors(self):
        return [i for i in self.issues if i.severity == "error"]

    def warnings(self):
        return [i for i in self.issues if i.severity == "warning"]

    def to_dict(self) -> dict:
        return {
            "front_matter": self.front_matter,
            "headings": {
                hid: {
                    "level": h.level,
                    "text": h.text,
                    "local_label": h.local_label,
                    "full_path": h.full_path,
                    "line_no": h.line_no,
                }
                for hid, h in self.headings.items()
            },
            "defined_terms": {
                t: {
                    "definition": d.definition,
                    "anchor_id": d.anchor_id,
                    "line_no": d.line_no,
                    "used": d.used,
                }
                for t, d in self.defined_terms.items()
            },
            "footnotes": {
                lbl: {
                    "number": f.number,
                    "line_no": f.line_no,
                    "referenced": f.referenced,
                }
                for lbl, f in self.footnotes.items()
            },
            "issues": [
                {"severity": i.severity, "message": i.message, "line_no": i.line_no}
                for i in self.issues
            ],
        }


class _Ctx:
    def __init__(self):
        self.defined_terms: dict[str, DefinedTermInfo] = {}
        self.headings: dict[str, HeadingInfo] = {}
        self.footnotes: dict[str, FootnoteInfo] = {}
        self.footnote_order: list[str] = []  # labels, in first-reference order
        self.issues: list[LintIssue] = []
        self.margin_counter = 0

    def err(self, msg, line_no):
        self.issues.append(LintIssue("error", msg, line_no))

    def warn(self, msg, line_no):
        self.issues.append(LintIssue("warning", msg, line_no))


def _heading_labels(counters: list[int], level: int) -> tuple[str, str]:
    """Returns (local_label, full_path_without_prefix)."""
    numeric = str(counters[0])
    if level >= 2:
        numeric += f".{counters[1]}"
    parens = ""
    if level >= 3:
        parens += f"({to_alpha(counters[2])})"
    if level >= 4:
        parens += f"({to_roman(counters[3])})"
    full = numeric + parens
    if level == 1:
        local = str(counters[0])
    elif level == 2:
        local = numeric
    elif level == 3:
        local = f"({to_alpha(counters[2])})"
    else:
        local = f"({to_roman(counters[3])})"
    return local, full


def _pass1_registries(blocks: list, ctx: _Ctx) -> None:
    """Assign heading numbers/ids and register defined-term/footnote-def
    declarations. Must complete before inline resolution (pass 2) because
    cross-references and term references can point forward in the doc.
    """
    counters = [0, 0, 0, 0]
    seen_ids: set[str] = set()
    define_re = re.compile(r"\[\[define:([^\|\]]+)\|([^\]]*)\]\]")

    for block in blocks:
        if isinstance(block, P.HeadingBlock):
            lvl = block.level
            counters[lvl - 1] += 1
            for deeper in range(lvl, 4):
                counters[deeper] = 0
            local_label, full = _heading_labels(counters, lvl)
            hid = block.explicit_id or slugify(block.text)
            if hid in seen_ids:
                ctx.err(f"duplicate heading id '{hid}'", block.line_no)
            seen_ids.add(hid)
            ctx.headings[hid] = HeadingInfo(
                id=hid,
                level=lvl,
                text=block.text,
                local_label=local_label,
                full_path=f"Section {full}",
                line_no=block.line_no,
            )
        elif isinstance(block, P.ParagraphBlock):
            for m in define_re.finditer(block.text):
                term = m.group(1).strip()
                definition = m.group(2).strip()
                if term in ctx.defined_terms:
                    ctx.err(
                        f"term '{term}' redefined (first defined at "
                        f"line {ctx.defined_terms[term].line_no})",
                        block.line_no,
                    )
                    continue
                anchor_id = f"def-{slugify(term)}"
                # anchor_id shares the same HTML id namespace as heading ids
                # (both land in id="..." attributes on the same page), so it
                # must go through the same seen_ids collision check -- found
                # by audit: an explicit heading {#def-agreement} colliding
                # with a term's auto-generated def-agreement anchor produced
                # two elements with the same id and a cross-reference that
                # silently resolved to the wrong one.
                if anchor_id in seen_ids:
                    ctx.err(
                        f"defined term '{term}' generates anchor id "
                        f"'{anchor_id}', which collides with an existing "
                        "heading id or another term's anchor",
                        block.line_no,
                    )
                    continue
                seen_ids.add(anchor_id)
                ctx.defined_terms[term] = DefinedTermInfo(
                    term=term,
                    definition=definition,
                    anchor_id=anchor_id,
                    line_no=block.line_no,
                )
        elif isinstance(block, P.FootnoteDefBlock):
            if block.label in ctx.footnotes:
                ctx.err(
                    f"footnote '[^{block.label}]' redefined (first defined at "
                    f"line {ctx.footnotes[block.label].line_no})",
                    block.line_no,
                )
                continue
            ctx.footnotes[block.label] = FootnoteInfo(
                label=block.label, text_raw=block.text, line_no=block.line_no
            )


_INLINE_TOKEN = re.compile(r"\[\[|\]\]|\[\^|\*\*|\*|`")


def render_inline(text: str, ctx: _Ctx, line_no: int) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("[[", i):
            end = text.find("]]", i + 2)
            if end == -1:
                out.append(esc(text[i:]))
                break
            content = text[i + 2 : end]
            out.append(_render_directive(content, ctx, line_no))
            i = end + 2
        elif text.startswith("[^", i):
            end = text.find("]", i + 2)
            if end == -1:
                out.append(esc(text[i:]))
                break
            label = text[i + 2 : end]
            out.append(_render_footnote_ref(label, ctx, line_no))
            i = end + 1
        elif text.startswith("**", i):
            end = text.find("**", i + 2)
            if end == -1:
                out.append(esc(text[i:]))
                break
            out.append(f"<strong>{esc(text[i + 2 : end])}</strong>")
            i = end + 2
        elif text[i] == "*":
            end = text.find("*", i + 1)
            if end == -1:
                out.append(esc(text[i:]))
                break
            out.append(f"<em>{esc(text[i + 1 : end])}</em>")
            i = end + 1
        elif text[i] == "`":
            end = text.find("`", i + 1)
            if end == -1:
                out.append(esc(text[i:]))
                break
            out.append(f"<code>{esc(text[i + 1 : end])}</code>")
            i = end + 1
        else:
            j = i
            while j < n and text[j] not in "[*`":
                j += 1
            out.append(esc(text[i:j]))
            i = j
    return "".join(out)


def _render_directive(content: str, ctx: _Ctx, line_no: int) -> str:
    if content.startswith("define:"):
        rest = content[len("define:") :]
        term = rest.split("|", 1)[0].strip()
        info = ctx.defined_terms.get(term)
        if info is None:
            ctx.err(f"internal: define directive for unregistered term '{term}'", line_no)
            return f'<span class="lmd-broken">[[define:{esc(term)}]]</span>'
        return f'<strong id="{info.anchor_id}" class="lmd-term">&quot;{esc(term)}&quot;</strong>'
    if content.startswith("ref:"):
        target = content[len("ref:") :].strip()
        heading = ctx.headings.get(target)
        if heading is None:
            ctx.err(f"cross-reference to undefined anchor id '{target}'", line_no)
            return f'<span class="lmd-broken-ref">[[ref:{esc(target)}?]]</span>'
        return f'<a class="lmd-ref" href="#{esc(heading.id)}">{esc(heading.full_path)}</a>'
    if content.strip() == "signature-block":
        return ""
    term = content.strip()
    info = ctx.defined_terms.get(term)
    if info is None:
        ctx.err(f"reference to undefined term '{term}'", line_no)
        return f'<span class="lmd-broken-ref">[[{esc(term)}?]]</span>'
    info.used = True
    return f'<a class="lmd-term-ref" href="#{info.anchor_id}">{esc(term)}</a>'


def _render_footnote_ref(label: str, ctx: _Ctx, line_no: int) -> str:
    info = ctx.footnotes.get(label)
    if info is None:
        ctx.err(f"footnote reference '[^{label}]' has no matching definition", line_no)
        return f'<sup class="lmd-broken-ref">[^{esc(label)}?]</sup>'
    if info.number is None:
        info.number = len(ctx.footnote_order) + 1
        ctx.footnote_order.append(label)
    info.referenced = True
    return (
        f'<sup id="fnref-{esc(label)}">'
        f'<a href="#fn-{esc(label)}">{info.number}</a></sup>'
    )


_SCALAR_FRONT_MATTER_KEYS = ("title", "effective_date")
_LIST_FRONT_MATTER_KEYS = ("parties",)


def _validate_front_matter(front_matter: dict) -> None:
    """Reject type-confused front matter instead of silently corrupting
    the document. Found by audit: `title:` followed by `- ` list items
    made `front_matter["title"]` a list, which crashed `html.escape` with
    an unhandled AttributeError; `parties: Acme Corp` (a scalar, not a
    `- ` list -- an easy mistake) made it a string, which both the
    signature block and cover page then iterated *character by character*
    with zero lint warning -- silent document corruption in a legal
    contract generator, worse than a loud crash.
    """
    for key in _SCALAR_FRONT_MATTER_KEYS:
        if key in front_matter and isinstance(front_matter[key], list):
            raise P.LmdSyntaxError(
                f"front matter '{key}' must be a single value, not a list "
                "(remove the '- ' list items under it)",
                1,
            )
    for key in _LIST_FRONT_MATTER_KEYS:
        if key in front_matter and not isinstance(front_matter[key], list):
            raise P.LmdSyntaxError(
                f"front matter '{key}' must be a list (use '{key}:' followed "
                f"by '  - item' lines, not '{key}: value' on one line)",
                1,
            )


def build_document(source: str) -> Document:
    lines = source.split("\n")
    front_matter, body_lines, offset = P.parse_front_matter(lines)
    _validate_front_matter(front_matter)
    body = "\n".join(body_lines)
    blocks = P.tokenize_blocks(body, offset)

    ctx = _Ctx()
    _pass1_registries(blocks, ctx)

    render_blocks: list = []
    for block in blocks:
        if isinstance(block, P.HeadingBlock):
            hid = block.explicit_id or slugify(block.text)
            heading = ctx.headings[hid]
            inline_html = render_inline(block.text, ctx, block.line_no)
            render_blocks.append(
                RHeading(
                    level=block.level,
                    local_label=heading.local_label,
                    full_path=heading.full_path,
                    id=heading.id,
                    inline_html=inline_html,
                )
            )
        elif isinstance(block, P.ParagraphBlock):
            ctx.margin_counter += 1
            inline_html = render_inline(block.text, ctx, block.line_no)
            render_blocks.append(
                RParagraph(margin_number=ctx.margin_counter, inline_html=inline_html)
            )
        elif isinstance(block, P.SignatureBlockDirective):
            parties = front_matter.get("parties", [])
            if not parties:
                ctx.err(
                    "[[signature-block]] used but front matter has no 'parties' list",
                    block.line_no,
                )
            render_blocks.append(RSignatureBlock(parties=list(parties)))
        elif isinstance(block, P.FootnoteDefBlock):
            pass  # rendered below, in citation order, not document order

    for term, info in ctx.defined_terms.items():
        if not info.used:
            ctx.warn(f"defined term '{term}' is never referenced", info.line_no)

    footnotes_in_order: list[RFootnote] = []
    for label in ctx.footnote_order:
        info = ctx.footnotes[label]
        inline_html = render_inline(info.text_raw, ctx, info.line_no)
        footnotes_in_order.append(
            RFootnote(number=info.number, label=label, inline_html=inline_html)
        )
    for label, info in ctx.footnotes.items():
        if not info.referenced:
            ctx.warn(f"footnote '[^{label}]' is defined but never referenced", info.line_no)

    ctx.issues.sort(key=lambda i: i.line_no)

    return Document(
        front_matter=front_matter,
        render_blocks=render_blocks,
        headings=ctx.headings,
        defined_terms=ctx.defined_terms,
        footnotes=ctx.footnotes,
        footnotes_in_order=footnotes_in_order,
        issues=ctx.issues,
    )
