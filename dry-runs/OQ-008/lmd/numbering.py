import html
import re
from dataclasses import dataclass, field

from .errors import BuildError

HEADING_RE = re.compile(
    r"^(?P<hashes>#{1,4})\s+(?P<title>.+?)\s*(?:\{#(?P<id>[\w-]+)\})?\s*$"
)


def to_alpha_lower(n: int) -> str:
    """1 -> a, 2 -> b, ... 26 -> z, 27 -> aa (spreadsheet-style overflow)."""
    if n < 1:
        raise ValueError("alpha numbering requires n >= 1")
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(ord("a") + rem) + result
    return result


_ROMAN_TABLE = [
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
    (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
    (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
]


def to_roman_lower(n: int) -> str:
    if n < 1:
        raise ValueError("roman numbering requires n >= 1")
    result = ""
    for value, symbol in _ROMAN_TABLE:
        while n >= value:
            result += symbol
            n -= value
    return result


def format_label(kind: str, n: int) -> str:
    if kind == "decimal":
        return str(n)
    if kind == "alpha-lower":
        return to_alpha_lower(n)
    if kind == "alpha-upper":
        return to_alpha_lower(n).upper()
    if kind == "roman-lower":
        return to_roman_lower(n)
    if kind == "roman-upper":
        return to_roman_lower(n).upper()
    raise ValueError(f"unknown numbering kind: {kind!r}")


def slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug or "section"


@dataclass
class Heading:
    line: int
    level: int
    title: str
    explicit_id: str | None
    anchor_id: str = ""
    number: str = ""


@dataclass
class NumberingResult:
    headings: list[Heading] = field(default_factory=list)
    anchors: dict[str, Heading] = field(default_factory=dict)


def compute_numbering(body: str, scheme: list[str], line_offset: int = 0) -> NumberingResult:
    """Pass 1: find every ATX heading (levels 1-4) and assign it a number
    and a stable anchor ID.

    The anchor ID is either the author-supplied ``{#id}`` or a slug of the
    title. Crucially, once assigned, the anchor never changes when a
    sibling section is added/removed/reordered — only the *number* does.
    Explicit IDs are exactly how an author pins that stability down when a
    slug alone wouldn't survive a heading being reworded.
    """
    counters = [0, 0, 0, 0]
    result = NumberingResult()
    seen_ids: set[str] = set()
    previous_level = 0

    for i, raw_line in enumerate(body.splitlines()):
        m = HEADING_RE.match(raw_line)
        if not m:
            continue
        level = len(m.group("hashes"))
        title = m.group("title").strip()
        explicit_id = m.group("id")
        file_line = line_offset + i + 1

        if level > previous_level + 1:
            raise BuildError(
                f"heading level skips from {previous_level} to {level}: "
                f"a level-{previous_level + 1} heading is required before "
                f"'{'#' * level} {title}' can appear",
                line=file_line,
                context=raw_line.strip(),
            )
        previous_level = level

        counters[level - 1] += 1
        for j in range(level, 4):
            counters[j] = 0

        parts = []
        for lvl in range(1, level + 1):
            label = format_label(scheme[lvl - 1], counters[lvl - 1])
            if lvl == 1:
                parts.append(label)
            elif lvl == 2:
                parts.append("." + label)
            else:
                parts.append(f"({label})")
        number = "".join(parts)

        anchor_id = explicit_id or slugify(title)
        if anchor_id in seen_ids:
            raise BuildError(
                f"duplicate anchor id '{anchor_id}'", line=file_line, context=raw_line.strip()
            )
        seen_ids.add(anchor_id)

        heading = Heading(
            line=file_line,
            level=level,
            title=title,
            explicit_id=explicit_id,
            anchor_id=anchor_id,
            number=number,
        )
        result.headings.append(heading)
        result.anchors[anchor_id] = heading

    return result


def render_headings(body: str, numbering: NumberingResult) -> str:
    """Pass 2: replace each heading line with a raw HTML heading tag
    carrying its computed number and stable anchor id, so it survives
    the Markdown pass untouched.
    """
    heading_iter = iter(numbering.headings)
    out_lines = []
    for raw_line in body.splitlines():
        m = HEADING_RE.match(raw_line)
        if not m:
            out_lines.append(raw_line)
            continue
        h = next(heading_iter)
        out_lines.append(
            f'<h{h.level} id="{h.anchor_id}" class="lmd-heading lmd-level-{h.level}">'
            f'<span class="lmd-number">{h.number}</span> '
            f'<span class="lmd-title">{html.escape(h.title)}</span></h{h.level}>'
        )
    return "\n".join(out_lines)
