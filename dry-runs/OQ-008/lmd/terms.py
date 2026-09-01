import html
import re

from .errors import BuildError
from .numbering import slugify

DEF_RE = re.compile(r"\[([^\[\]]+)\]\{\.def\}")
TERM_RE = re.compile(r"\[([^\[\]]+)\]\{\.term\}")


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def collect_definitions(body: str) -> dict[str, int]:
    """Pass 1: find every ``[Term]{.def}`` definition site.

    Returns term -> line number. Raises BuildError on a term defined more
    than once (a real drafting error a mechanical check should catch).
    """
    seen: dict[str, int] = {}
    for m in DEF_RE.finditer(body):
        term = m.group(1).strip()
        line = _line_of(body, m.start())
        if term in seen:
            raise BuildError(
                f"defined term \"{term}\" is defined more than once "
                f"(first defined at line {seen[term]})",
                line=line,
            )
        seen[term] = line
    return seen


def validate_usages(body: str, definitions: dict[str, int]) -> None:
    """Pass 1 (continued): every ``[Term]{.term}`` usage must have a
    matching ``.def`` somewhere in the document. Order doesn't matter
    (v0.1 doesn't enforce definition-before-first-use).
    """
    for m in TERM_RE.finditer(body):
        term = m.group(1).strip()
        if term not in definitions:
            line = _line_of(body, m.start())
            raise BuildError(
                f'"{term}" is used as a defined term but never defined '
                f"with [{term}]{{.def}} anywhere in the document",
                line=line,
                context=m.group(0),
            )


def render_terms(body: str) -> str:
    """Pass 2: substitute definition/usage spans with anchored HTML.

    Assumes collect_definitions/validate_usages already ran and raised on
    any problem, so no further validation happens here.
    """

    def _def_sub(m: re.Match) -> str:
        term = m.group(1).strip()
        slug = slugify(term)
        safe_term = html.escape(term)
        return f'<span class="lmd-term-def" id="term-{slug}">&#8220;{safe_term}&#8221;</span>'

    def _term_sub(m: re.Match) -> str:
        term = m.group(1).strip()
        slug = slugify(term)
        safe_term = html.escape(term)
        return f'<a class="lmd-term-ref" href="#term-{slug}">{safe_term}</a>'

    body = DEF_RE.sub(_def_sub, body)
    body = TERM_RE.sub(_term_sub, body)
    return body
