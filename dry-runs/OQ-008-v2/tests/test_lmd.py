"""Tests for the lmd reference implementation.

Deliberately includes negative cases (test_broken_fixture_*) that assert
the linter actually fails on bad input -- per FAILURE-CLASSES.md item 4, a
scorer/checker that's only ever been run against input it should pass
can't be trusted; these confirm it also correctly rejects input it should
reject.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lmd import model as M
from lmd import parser as P

REPO_ROOT = Path(__file__).resolve().parent.parent
GOOD_FIXTURE = REPO_ROOT / "examples" / "services-agreement.lmd"
BROKEN_FIXTURE = REPO_ROOT / "examples" / "broken.lmd"


def build(path: Path) -> M.Document:
    return M.build_document(path.read_text(encoding="utf-8"))


# ---- numbering ----

def test_heading_numbering_all_four_levels():
    doc = build(GOOD_FIXTURE)
    h = doc.headings
    assert h["definitions"].full_path == "Section 1"
    assert h["sec-confidential-info"].full_path == "Section 2"
    assert h["obligations"].full_path == "Section 2.1"
    assert h["sec-exclusions"].full_path == "Section 2.2"
    assert h["publicly-available-information"].full_path == "Section 2.2(a)"
    assert h["independently-developed-information"].full_path == "Section 2.2(b)"
    assert h["burden-of-proof"].full_path == "Section 2.2(b)(i)"


def test_numbering_resets_on_shallower_sibling():
    doc = build(GOOD_FIXTURE)
    # Section 3 follows Section 2.2(b)(i); its subsections restart at .1
    assert doc.headings["term-and-termination"].full_path == "Section 3"
    assert doc.headings["term"].full_path == "Section 3.1"
    assert doc.headings["sec-termination-convenience"].full_path == "Section 3.2"


def test_alpha_and_roman_numeral_helpers():
    assert M.to_alpha(1) == "a"
    assert M.to_alpha(26) == "z"
    assert M.to_alpha(27) == "aa"
    assert M.to_roman(1) == "i"
    assert M.to_roman(4) == "iv"
    assert M.to_roman(9) == "ix"
    assert M.to_roman(14) == "xiv"


# ---- cross-references ----

def test_cross_reference_resolves_to_current_label():
    doc = build(GOOD_FIXTURE)
    para = next(
        b for b in doc.render_blocks
        if isinstance(b, M.RParagraph) and "Section 4" in b.inline_html
    )
    assert 'href="#sec-amendment"' in para.inline_html
    assert "Section 4" in para.inline_html


def test_broken_cross_reference_is_a_lint_error():
    doc = build(BROKEN_FIXTURE)
    messages = [i.message for i in doc.errors()]
    assert any("undefined anchor id 'sec-nowhere'" in m for m in messages)


# ---- defined terms ----

def test_defined_term_marked_used_when_referenced():
    doc = build(GOOD_FIXTURE)
    assert doc.defined_terms["Agreement"].used is True


def test_defined_term_unused_is_a_warning_not_error():
    doc = build(GOOD_FIXTURE)
    warnings = [i.message for i in doc.warnings()]
    assert any("'Services' is never referenced" in m for m in warnings)
    assert not any("Services" in i.message for i in doc.errors())


def test_undefined_term_reference_is_a_lint_error():
    doc = build(BROKEN_FIXTURE)
    messages = [i.message for i in doc.errors()]
    assert any("undefined term 'Services'" in m for m in messages)


def test_term_redefinition_is_a_lint_error():
    doc = build(BROKEN_FIXTURE)
    messages = [i.message for i in doc.errors()]
    assert any("'Agreement' redefined" in m for m in messages)


# ---- footnotes ----

def test_footnotes_numbered_in_citation_order():
    doc = build(GOOD_FIXTURE)
    assert [fn.number for fn in doc.footnotes_in_order] == [1, 2]
    assert doc.footnotes_in_order[0].label == "care-standard"
    assert doc.footnotes_in_order[1].label == "burden"


def test_dangling_footnote_reference_is_a_lint_error():
    doc = build(BROKEN_FIXTURE)
    messages = [i.message for i in doc.errors()]
    assert any("'[^ghost]' has no matching definition" in m for m in messages)


def test_unreferenced_footnote_is_a_warning():
    doc = build(BROKEN_FIXTURE)
    messages = [i.message for i in doc.warnings()]
    assert any("'[^unused]' is defined but never referenced" in m for m in messages)


# ---- other lint checks ----

def test_duplicate_heading_id_is_a_lint_error():
    doc = build(BROKEN_FIXTURE)
    messages = [i.message for i in doc.errors()]
    assert any("duplicate heading id 'obligations'" in m for m in messages)


def test_signature_block_without_parties_is_a_lint_error():
    doc = build(BROKEN_FIXTURE)
    messages = [i.message for i in doc.errors()]
    assert any("no 'parties' list" in m for m in messages)


def test_good_fixture_has_zero_lint_errors():
    doc = build(GOOD_FIXTURE)
    assert doc.errors() == [], [str(i) for i in doc.errors()]


def test_broken_fixture_has_exactly_the_six_planted_errors():
    doc = build(BROKEN_FIXTURE)
    assert len(doc.errors()) == 6, [str(i) for i in doc.errors()]


# ---- margin numbers ----

def test_margin_numbers_are_sequential_and_skip_headings():
    doc = build(GOOD_FIXTURE)
    paragraphs = [b for b in doc.render_blocks if isinstance(b, M.RParagraph)]
    assert [p.margin_number for p in paragraphs] == list(range(1, len(paragraphs) + 1))


# ---- html output safety (escaping) ----

def test_html_output_escapes_hostile_heading_and_body_text(tmp_path):
    from lmd import render_html as R

    src = (
        "# <script>alert(1)</script> {#evil}\n\n"
        'Body with a raw <img src=x onerror="alert(2)"> tag and a & ampersand.\n'
    )
    doc = M.build_document(src)
    html_out = R.render_html(doc)
    assert "<script>alert(1)</script>" not in html_out
    assert "<img src=x onerror=" not in html_out
    assert "&lt;script&gt;" in html_out
    assert "&amp; ampersand" in html_out


def test_html_output_escapes_hostile_defined_term_and_definition():
    from lmd import render_html as R

    src = (
        '[[define:<b>Evil</b>|"><script>alert(3)</script>]] means nothing.\n\n'
        "Later reference to [[<b>Evil</b>]].\n"
    )
    doc = M.build_document(src)
    html_out = R.render_html(doc)
    assert "<script>alert(3)</script>" not in html_out
    assert "<b>Evil</b>" not in html_out


# ---- front matter parser edge cases ----

def test_front_matter_without_closing_delimiter_raises():
    with pytest.raises(P.LmdSyntaxError):
        M.build_document("---\ntitle: no closing delimiter\n")


def test_heading_level_beyond_four_is_a_syntax_error():
    with pytest.raises(P.LmdSyntaxError):
        M.build_document("##### too deep\n\nbody text\n")


def test_no_front_matter_is_fine():
    doc = M.build_document("# Just a heading\n\nJust a paragraph.\n")
    assert doc.front_matter == {}
    assert doc.headings["just-a-heading"].full_path == "Section 1"


# ---- explicit heading-id injection (regression: found by attacker-persona
# audit -- explicit {#id} was placed into the id/href HTML attributes with
# no validation and no escaping, allowing attribute-breakout XSS via
# id="x\"><script>...</script><h1 x=\""). Fixed by (1) validating explicit
# ids against a safe charset at parse time, rejecting anything else with a
# clean syntax error, and (2) escaping the id at both HTML consumption
# sites anyway, as defense in depth in case a future code path constructs
# a Document without going through the parser's validation. ----

def test_explicit_heading_id_with_attribute_breakout_chars_is_rejected():
    src = '# Title {#x"><script>alert(document.domain)</script><h1 x="}\n\nBody.\n'
    with pytest.raises(P.LmdSyntaxError, match="invalid heading id"):
        M.build_document(src)


def test_explicit_heading_id_used_in_cross_ref_href_with_breakout_chars_is_rejected():
    src = (
        '# Definitions {#defs" onclick="alert(1)}\n\n'
        'See [[ref:defs" onclick="alert(1)]] for details.\n'
    )
    with pytest.raises(P.LmdSyntaxError, match="invalid heading id"):
        M.build_document(src)


def test_valid_explicit_heading_ids_with_hyphens_and_digits_still_work():
    src = "# Section {#sec-4-2b}\n\nBody referencing [[ref:sec-4-2b]].\n"
    doc = M.build_document(src)
    assert doc.headings["sec-4-2b"].full_path == "Section 1"
    assert doc.errors() == []


def test_defined_term_anchor_colliding_with_heading_id_is_a_lint_error():
    """Regression: found by round-2 audit. An explicit heading id equal to
    another term's auto-generated def-<slug> anchor produced two elements
    with the same HTML id and a cross-reference that silently resolved to
    the wrong one (whichever the browser's getElementById picks first).
    """
    src = (
        "# Definitions {#def-agreement}\n\n"
        "[[define:Agreement|the contract between the parties]] means "
        "the contract between the parties.\n"
    )
    doc = M.build_document(src)
    messages = [i.message for i in doc.errors()]
    assert any("collides with an existing heading id" in m for m in messages)


def test_footnote_label_with_invalid_characters_is_rejected():
    """Regression: round-2 audit noted footnote labels had no parser-level
    charset validation (unlike heading ids), relying solely on esc() at
    every consumption site -- the exact shape of bug that caused the
    heading-id XSS. Validating at the source closes that off proactively.
    """
    src = 'Body text with a footnote.[^bad"label]\n\n[^bad"label]: text\n'
    with pytest.raises(P.LmdSyntaxError, match="invalid footnote label"):
        M.build_document(src)


def test_heading_with_empty_explicit_id_is_a_syntax_error():
    """Regression: round-2 audit found a whitespace-only {#   } id used to
    silently leave the literal braces in the visible heading text instead
    of being rejected.
    """
    with pytest.raises(P.LmdSyntaxError, match="empty explicit id"):
        M.build_document("# Section One {#   }\n\nBody.\n")


def test_model_json_output_is_embedding_safe_against_script_breakout():
    """Regression: round-2 audit found `lmd model`'s JSON dump embedded
    front-matter values verbatim, so a title containing
    "</script><script>alert(1)</script>" would break out if a downstream
    consumer did the common `var m = {json};` embed inside a <script> tag.
    """
    from lmd.cli import _html_safe_json

    src = (
        "---\n"
        "title: Evil </script><script>alert(1)</script>\n"
        "---\n\n"
        "# Heading\n\nBody.\n"
    )
    doc = M.build_document(src)
    text = _html_safe_json(doc.to_dict())
    assert "</script>" not in text
    assert "\\u003c/script\\u003e" in text
    # still valid JSON, not just mangled text
    import json

    parsed = json.loads(text)
    assert "</script>" in parsed["front_matter"]["title"]


def test_render_html_escapes_heading_id_as_defense_in_depth():
    """Construct a Document bypassing the parser's own validation (as if a
    future code path fed render_html a Document built some other way) and
    confirm the renderer itself still refuses to emit an unescaped id --
    i.e. the fix isn't solely reliant on the parser catching everything.
    """
    from lmd import render_html as R

    doc = M.Document(
        front_matter={},
        render_blocks=[
            M.RHeading(
                level=1,
                local_label="1",
                full_path='Section 1" onclick="alert(1)',
                id='x" onclick="alert(1)',
                inline_html="Title",
            )
        ],
        headings={},
        defined_terms={},
        footnotes={},
        footnotes_in_order=[],
        issues=[],
    )
    html_out = R.render_html(doc)
    assert 'onclick="alert(1)"' not in html_out
    assert "&quot;" in html_out


# ---- round-3 audit regressions ----

def test_title_as_a_list_is_rejected_not_crashed():
    """Regression: found by round-3 attacker audit. `title:` followed by
    `- ` list items made front_matter['title'] a list; render_html called
    M.esc(title) directly with no str() coercion, causing an unhandled
    AttributeError deep inside html.escape instead of a clean error.
    """
    src = "---\ntitle:\n  - Not\n  - A Scalar\n---\n\n# Heading\n\nBody.\n"
    with pytest.raises(P.LmdSyntaxError, match="must be a single value"):
        M.build_document(src)


def test_parties_as_a_scalar_string_is_rejected_not_silently_corrupted():
    """Regression: found by round-3 attacker audit. `parties: Acme Corp`
    (a natural mistake -- scalar instead of a '- ' list) made
    front_matter['parties'] a string, which the signature block and cover
    page then iterated character-by-character with zero lint warning --
    silent document corruption in a legal contract generator.
    """
    src = "---\ntitle: X\nparties: Acme Corp\n---\n\n# Heading\n\n[[signature-block]]\n"
    with pytest.raises(P.LmdSyntaxError, match="must be a list"):
        M.build_document(src)


def test_valid_list_parties_and_scalar_title_still_work():
    src = (
        "---\ntitle: X\nparties:\n  - Acme Corp\n  - Globex Inc\n---\n\n"
        "# Heading\n\n[[signature-block]]\n"
    )
    doc = M.build_document(src)
    assert doc.errors() == []
    assert doc.front_matter["parties"] == ["Acme Corp", "Globex Inc"]


def test_margin_number_css_uses_right_offset_not_the_reverted_left_width_bug():
    """Regression: found by round-3 verification-skeptic audit. The
    margin-number positioning fix (right: calc(100% + gap), replacing a
    buggy left:-0.9in + width:0.7in rule that put the glyph only ~0.2in
    from the paragraph instead of out in the gutter) had zero automated
    coverage -- all 30 prior tests passed whether or not the fix was in
    place. This asserts the fix's actual CSS text is present and the
    specific buggy pattern is gone, so a revert would be caught here
    without needing a full PDF-render-and-measure cycle in CI.
    """
    from lmd.render_html import CSS

    assert "right: calc(100% + 0.2in)" in CSS
    assert "left: -0.9in" not in CSS
