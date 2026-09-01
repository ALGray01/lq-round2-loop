"""Unit tests for scripts/build_usc_corpus.py's section-splitting logic.

Written after actually building the real corpus and finding a genuine bug
by inspecting its output (not by reading the regex and assuming it was
correct): the last requested section's captured text was silently
swallowing the *next* U.S. Code chapter's heading and table of contents,
because nothing stopped extraction at a chapter boundary when there was
no further "§ NNNN." match to stop at. These tests pin that fix down with
synthetic text shaped like the real PDF extraction output, so a future
change can't reintroduce it silently.

Run: python -m pytest tests/test_build_usc_corpus.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest

from build_usc_corpus import apply_manual_heading_corrections, split_sections  # noqa: E402

# Shaped like the real combined multi-page text: section headings start a
# line, sections run on into each other, and (for the last one) a new
# chapter's heading/TOC runs on with no "§" heading separating it.
SAMPLE_TEXT = """§ 6501. Definitions
In this chapter:
(1) Child
The term 'child' means an individual under the age of 13.
§ 6502. Regulation of unfair and deceptive acts
(a) Acts prohibited
It is unlawful for an operator...
(Pub. L. 105-277, div. C, title XIII, Sec. 1303, Oct. 21, 1998, 112 Stat. 2681-730.)
§ 6503. Safe harbors
(a) Guidelines
An operator may satisfy the requirements...
CHAPTER 91A—PROMOTING A SAFE
INTERNET FOR CHILDREN
Sec.
6551. Internet safety.
"""


def test_splits_into_correct_number_of_sections():
    sections = split_sections(SAMPLE_TEXT)
    assert {s["identifier"] for s in sections} == {"6501", "6502", "6503"}


def test_last_section_stops_at_chapter_boundary():
    sections = split_sections(SAMPLE_TEXT)
    sec_6503 = next(s for s in sections if s["identifier"] == "6503")
    assert "CHAPTER 91A" not in sec_6503["text"]
    assert "6551" not in sec_6503["text"]
    assert "An operator may satisfy" in sec_6503["text"]


def test_middle_section_does_not_bleed_into_next():
    sections = split_sections(SAMPLE_TEXT)
    sec_6501 = next(s for s in sections if s["identifier"] == "6501")
    assert "§ 6502" not in sec_6501["text"]
    assert "unlawful for an operator" not in sec_6501["text"]


def test_headings_captured_correctly():
    sections = split_sections(SAMPLE_TEXT)
    by_id = {s["identifier"]: s for s in sections}
    assert by_id["6501"]["heading"] == "Definitions"
    assert by_id["6502"]["heading"] == "Regulation of unfair and deceptive acts"
    assert by_id["6503"]["heading"] == "Safe harbors"


def test_no_chapter_boundary_present_is_handled_cleanly():
    # true negative: text with no trailing chapter heading at all must
    # still work (the boundary check is optional, not required).
    text = "§ 6501. Definitions\nSome text here.\n§ 6502. Something else\nMore text.\n"
    sections = split_sections(text)
    assert len(sections) == 2
    assert sections[0]["text"].strip() == "Some text here."


def test_manual_heading_correction_moves_continuation_from_text_to_heading():
    # Regression test for a real bug a fresh-context audit found: § 6502's
    # printed heading spans multiple lines before "(a) Acts prohibited"
    # starts the actual body, but SECTION_HEADING_RE only captures the
    # first line. HEADING_CONTINUATIONS/apply_manual_heading_corrections
    # moves the rest from the front of `text` into `heading`.
    sections = [
        {
            "identifier": "6502",
            "heading": "Regulation of unfair and deceptive acts",
            "text": (
                "and practices in connection with collection \n"
                "and use of personal information from and \n"
                "about children on the Internet \n"
                "(a) Acts prohibited \nIt is unlawful..."
            ),
        }
    ]
    apply_manual_heading_corrections(sections)
    assert sections[0]["heading"] == (
        "Regulation of unfair and deceptive acts and practices in connection "
        "with collection and use of personal information from and about "
        "children on the Internet"
    )
    assert sections[0]["text"].startswith("(a) Acts prohibited")


def test_manual_heading_correction_raises_if_expected_text_missing():
    # If the source text ever changes (re-fetch pulls different wording),
    # this must fail loudly rather than silently apply a stale correction
    # to the wrong content.
    sections = [{"identifier": "6502", "heading": "Regulation...", "text": "totally different text"}]
    with pytest.raises(RuntimeError):
        apply_manual_heading_corrections(sections)


def test_manual_heading_correction_is_a_noop_for_sections_without_one():
    sections = [{"identifier": "6501", "heading": "Definitions", "text": "In this chapter: ..."}]
    apply_manual_heading_corrections(sections)
    assert sections[0]["heading"] == "Definitions"
    assert sections[0]["text"] == "In this chapter: ..."
