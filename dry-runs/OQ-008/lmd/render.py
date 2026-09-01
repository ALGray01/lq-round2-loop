import html
from pathlib import Path

import markdown as md

from .crossref import validate_and_render_refs
from .frontmatter import split_front_matter
from .numbering import compute_numbering, render_headings
from .terms import collect_definitions, render_terms, validate_usages

TEMPLATE_PATH = Path(__file__).parent / "templates" / "page.html"


def build_html(source_text: str) -> str:
    """Compile legal-markdown source into a self-contained, print-ready
    HTML document. Raises lmd.errors.BuildError on any validation failure
    (broken cross-reference, undefined term, duplicate anchor/definition).
    """
    meta, body, body_start_line = split_front_matter(source_text)
    scheme = meta["numbering_scheme"]

    # Pass 1: validate everything before rendering anything. A document
    # that's broken in three places should report the first real problem,
    # not whichever one happens to be reached first at render time.
    numbering = compute_numbering(body, scheme, line_offset=body_start_line - 1)
    definitions = collect_definitions(body)
    validate_usages(body, definitions)

    # Pass 2: render, in dependency order (headings, then terms, then
    # cross-references, which need the heading numbers already computed).
    body = render_headings(body, numbering)
    body = render_terms(body)
    body = validate_and_render_refs(body, numbering)

    body_html = md.markdown(body, extensions=["footnotes", "extra", "md_in_html"])

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{{TITLE}}", html.escape(str(meta.get("title", ""))))
        .replace("{{PAGE_SIZE}}", html.escape(str(meta.get("page", {}).get("size", "Letter"))))
        .replace("{{PAGE_MARGIN}}", html.escape(str(meta.get("page", {}).get("margin", "1in"))))
        .replace("{{HEADER}}", html.escape(str(meta.get("page", {}).get("header", meta.get("title", "")))))
        .replace("{{BODY}}", body_html)
    )


def build_file(src_path: str) -> str:
    text = Path(src_path).read_text(encoding="utf-8")
    return build_html(text)
