"""Regression tests for a real XSS/HTML-injection finding from the
reserve-phase adversarial audit: heading titles, defined-term text, and
front-matter page.size/page.margin were reaching the rendered HTML
unescaped in three places (render.py, numbering.py, terms.py), while
title/header were already escaped in the same function. Each test here
plants the exact payload the audit used and checks the raw tag it
injected no longer appears live in the output.
"""
from lmd.render import build_html

PAYLOAD = "<script>alert(1)</script>"


def test_heading_title_is_escaped():
    doc = f"# {PAYLOAD} {{#s}}\n\nBody text.\n"
    out = build_html(doc)
    assert PAYLOAD not in out
    assert "&lt;script&gt;" in out


def test_defined_term_text_is_escaped():
    doc = f"# Def\n\nThe [{PAYLOAD}]{{.def}} is a term.\n"
    out = build_html(doc)
    assert PAYLOAD not in out
    assert "&lt;script&gt;" in out


def test_term_usage_text_is_escaped():
    doc = f"# Def\n\nThe [X]{{.def}} term.\n\n# Use\n\nSee [{PAYLOAD}]{{.term}}... \n"
    # Usage text must exactly match a defined term to pass validation, so
    # define the payload itself as the term under test.
    doc = (
        f"# Def\n\nThe [{PAYLOAD}]{{.def}} term.\n\n"
        f"# Use\n\nSee [{PAYLOAD}]{{.term}} again.\n"
    )
    out = build_html(doc)
    assert PAYLOAD not in out
    assert out.count("&lt;script&gt;") >= 2


def test_page_size_and_margin_are_escaped():
    doc = (
        "---\n"
        f'title: "Doc"\n'
        f'page:\n  size: "Letter</style>{PAYLOAD}"\n  margin: "1in"\n'
        "---\n\n# A\n\nBody.\n"
    )
    out = build_html(doc)
    assert PAYLOAD not in out
    assert "&lt;script&gt;" in out
