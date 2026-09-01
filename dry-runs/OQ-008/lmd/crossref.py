import re

from .errors import BuildError
from .numbering import NumberingResult

REF_RE = re.compile(r"\[\[ref:([\w-]+)\]\]")


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def validate_and_render_refs(body: str, numbering: NumberingResult) -> str:
    """Replace every ``[[ref:id]]`` with a link showing the *current*
    computed section number for that anchor.

    A reference to an anchor that doesn't exist is a build failure, not a
    dead link (see SPEC.md section 3.2) -- this is deliberately checked
    against a genuinely broken input in tests/test_crossref.py, not just
    asserted to work.
    """

    def _sub(m: re.Match) -> str:
        anchor_id = m.group(1)
        if anchor_id not in numbering.anchors:
            line = _line_of(body, m.start())
            known = ", ".join(sorted(numbering.anchors)) or "(none)"
            raise BuildError(
                f"cross-reference to unknown anchor '{anchor_id}'",
                line=line,
                context=f"{m.group(0)}  (known anchors: {known})",
            )
        heading = numbering.anchors[anchor_id]
        return f'<a class="lmd-ref" href="#{anchor_id}">Section {heading.number}</a>'

    return REF_RE.sub(_sub, body)
