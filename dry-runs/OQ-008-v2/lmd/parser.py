"""Front-matter + block-level tokenizing for LMD source text.

Deliberately not a full CommonMark parser (see GRAMMAR.md) -- this covers
exactly the block types the contract-drafting workflow needs: front
matter, headings 1-4 levels deep, paragraphs, and footnote definitions.
Inline-level parsing (bold/italic/directives/footnote refs) happens later,
in model.py, once we know the full document (defined-term / cross-ref
resolution needs two passes).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_VALID_ID = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")


class LmdSyntaxError(Exception):
    def __init__(self, message: str, line_no: int):
        super().__init__(f"line {line_no}: {message}")
        self.message = message
        self.line_no = line_no


@dataclass
class HeadingBlock:
    level: int
    text: str
    explicit_id: str | None
    line_no: int


@dataclass
class ParagraphBlock:
    text: str
    line_no: int


@dataclass
class FootnoteDefBlock:
    label: str
    text: str
    line_no: int


@dataclass
class SignatureBlockDirective:
    line_no: int


Block = HeadingBlock | ParagraphBlock | FootnoteDefBlock | SignatureBlockDirective


def parse_front_matter(lines: list[str]) -> tuple[dict, list[str], int]:
    """Returns (front_matter_dict, remaining_lines, line_offset).

    Supports `key: value` scalars and `key:` + `  - item` lists. No nested
    maps. Not a general YAML parser -- see GRAMMAR.md.
    """
    if not lines or lines[0].strip() != "---":
        return {}, lines, 0

    fm: dict = {}
    i = 1
    current_list_key: str | None = None
    while i < len(lines):
        raw = lines[i]
        if raw.strip() == "---":
            return fm, lines[i + 1 :], i + 1
        if raw.strip() == "":
            i += 1
            continue
        if raw.startswith("  - ") or raw.startswith("- "):
            item = raw.strip()[2:].strip()
            if current_list_key is None:
                raise LmdSyntaxError(
                    "list item with no preceding 'key:' line in front matter", i + 1
                )
            fm.setdefault(current_list_key, []).append(item)
            i += 1
            continue
        if ":" not in raw:
            raise LmdSyntaxError(f"malformed front-matter line: {raw!r}", i + 1)
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            current_list_key = key
            fm[key] = []
        else:
            current_list_key = None
            fm[key] = value
        i += 1

    raise LmdSyntaxError("front matter opened with '---' but never closed", 1)


_HEADING_PREFIXES = {1: "# ", 2: "## ", 3: "### ", 4: "#### "}


def _parse_heading(line: str, line_no: int) -> HeadingBlock:
    stripped = line.rstrip("\n")
    hashes = 0
    while hashes < len(stripped) and stripped[hashes] == "#":
        hashes += 1
    if hashes < 1 or hashes > 4 or hashes >= len(stripped) or stripped[hashes] != " ":
        raise LmdSyntaxError(
            f"heading must use 1-4 '#' followed by a space (got {hashes!r} hashes)",
            line_no,
        )
    text = stripped[hashes + 1 :].strip()
    explicit_id = None
    if text.endswith("}") and "{#" in text:
        open_at = text.rfind("{#")
        candidate = text[open_at + 2 : -1].strip()
        # The {#...} suffix is always stripped from the displayed heading
        # text once detected, whether or not candidate is valid -- found by
        # audit: a whitespace-only id like "{#   }" used to fall through
        # this whole block and leave the literal "{#   }" sitting in the
        # visible heading text instead of being treated as a malformed id.
        text = text[:open_at].strip()
        if not candidate:
            raise LmdSyntaxError("heading has an empty explicit id '{#}'", line_no)
        if not _VALID_ID.match(candidate):
            raise LmdSyntaxError(
                f"invalid heading id {candidate!r}: ids must match "
                "[A-Za-z][A-Za-z0-9-]* (this restriction exists because the id "
                "is placed directly into an HTML id/href attribute -- see "
                "SPEC.md/GRAMMAR.md)",
                line_no,
            )
        explicit_id = candidate
    if not text:
        raise LmdSyntaxError("heading has no text", line_no)
    return HeadingBlock(level=hashes, text=text, explicit_id=explicit_id, line_no=line_no)


def tokenize_blocks(body: str, line_offset: int) -> list[Block]:
    """Split body text into blank-line-separated top-level blocks."""
    lines = body.split("\n")
    blocks: list[Block] = []
    buf: list[str] = []
    buf_start_line = 0

    def flush():
        if not buf:
            return
        text = "\n".join(buf).strip()
        if text:
            start_no = buf_start_line + line_offset + 1
            if text.startswith("[^") and "]:" in text.split("\n", 1)[0]:
                first_line = text.split("\n", 1)[0]
                label_end = first_line.find("]:")
                label = first_line[2:label_end]
                # Same restricted charset as heading ids, and for the same
                # reason: labels are placed verbatim into HTML id="fn-..."/
                # href="#fn-..." attributes (model.py's _render_footnote_ref).
                # Both consumption sites already esc() the label so this
                # isn't currently exploitable, but validating at the source
                # closes off the same bug shape as the heading-id XSS found
                # by audit, rather than relying solely on every future
                # consumption site remembering to escape.
                if not _VALID_ID.match(label):
                    raise LmdSyntaxError(
                        f"invalid footnote label {label!r}: labels must match "
                        "[A-Za-z][A-Za-z0-9-]*",
                        start_no,
                    )
                rest_first = first_line[label_end + 2 :].strip()
                rest = "\n".join([rest_first] + text.split("\n")[1:]).strip()
                blocks.append(FootnoteDefBlock(label=label, text=rest, line_no=start_no))
            elif text.strip() == "[[signature-block]]":
                blocks.append(SignatureBlockDirective(line_no=start_no))
            else:
                blocks.append(ParagraphBlock(text=text, line_no=start_no))
        buf.clear()

    for idx, raw in enumerate(lines):
        line_no = idx + line_offset + 1
        stripped = raw.rstrip("\n")
        if stripped.strip() == "":
            flush()
            continue
        if stripped.lstrip().startswith("#"):
            flush()
            blocks.append(_parse_heading(stripped, line_no))
            continue
        if not buf:
            buf_start_line = idx
        buf.append(stripped)
    flush()
    return blocks
