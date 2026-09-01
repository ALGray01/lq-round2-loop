"""Unit tests for the cross-reference extraction logic in
scripts/build_corpus.py, run against real sentences drawn from the actual
16 CFR Part 312 text (see data/raw/title16_part312_*.xml) plus a few
true-negative / edge cases the extractor should get right by *not*
matching or *not* resolving, so a passing suite can't just be a scorer
that never sees a case it should fail (FAILURE-CLASSES.md item 4).

Run: python -m pytest tests/test_build_corpus.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build_corpus import (  # noqa: E402
    expand_section_range,
    extract_cross_references,
    extract_definitions,
    is_coppa_self_reference,
    resolve_usc_against_companion,
)

KNOWN = {f"312.{n}" for n in range(1, 14)}  # 312.1 .. 312.13, matches the real corpus


def test_expand_simple_range():
    assert expand_section_range("312.2 through 312.8") == [
        "312.2", "312.3", "312.4", "312.5", "312.6", "312.7", "312.8",
    ]


def test_expand_range_plus_trailing_and():
    # real text: "§§ 312.2 through 312.8, and 312.10"
    assert expand_section_range("312.2 through 312.8, and 312.10") == [
        "312.2", "312.3", "312.4", "312.5", "312.6", "312.7", "312.8", "312.10",
    ]


def test_expand_single_number_no_range():
    assert expand_section_range("312.5") == ["312.5"]


def test_expand_and_separated_list_no_through():
    assert expand_section_range("312.5(b)(2) and (3)") == ["312.5"]


def test_internal_section_reference_resolves():
    text = "Provide notice under § 312.4(c)(1)."
    refs = extract_cross_references(text, "312", KNOWN)
    internal = [r for r in refs if r["type"] == "internal_section"]
    assert len(internal) == 1
    assert internal[0]["target_citation"] == "16 CFR 312.4"
    assert internal[0]["resolved"] is True


def test_internal_reference_to_missing_section_is_not_resolved():
    # true negative: this section number is NOT in the known set, so the
    # extractor must report resolved=False rather than optimistically
    # assuming every "§ 312.X"-shaped string is a hit.
    text = "See § 312.99 for details."
    refs = extract_cross_references(text, "312", KNOWN)
    internal = [r for r in refs if r["type"] == "internal_section"]
    assert len(internal) == 1
    assert internal[0]["resolved"] is False


def test_usc_reference_is_never_marked_resolved():
    text = "as defined in 15 U.S.C. 6501, et seq."
    refs = extract_cross_references(text, "312", KNOWN)
    usc = [r for r in refs if r["type"] == "usc"]
    assert len(usc) == 1
    assert usc[0]["target_citation"] == "15 U.S.C. 6501"
    assert usc[0]["resolved"] is False


def test_usc_worded_form():
    text = "as that term is defined in section 551(1) of title 5, United States Code."
    refs = extract_cross_references(text, "312", KNOWN)
    usc = [r for r in refs if r["type"] == "usc"]
    assert len(usc) == 1
    assert usc[0]["target_citation"] == "5 U.S.C. 551(1)"


def test_named_act_reference():
    text = "a violation of a regulation prescribed under section 6502(a) of this Act"
    refs = extract_cross_references(text, "312", KNOWN)
    named = [r for r in refs if r["type"] == "named_act_section"]
    assert len(named) == 1
    assert named[0]["resolved"] is False


def test_is_coppa_self_reference_recognizes_this_act_and_coppa_by_name():
    assert is_coppa_self_reference("this Act") is True
    assert is_coppa_self_reference("the Children's Online Privacy Protection Act of 1998") is True


def test_is_coppa_self_reference_rejects_other_named_acts():
    # true negative: a different named Act must not be mistaken for COPPA
    # self-reference just because it also matches "of ... Act".
    assert is_coppa_self_reference("the Federal Trade Commission Act") is False
    assert is_coppa_self_reference("the Fair Credit Reporting Act of 1970") is False


def test_named_act_reference_to_this_act_gets_a_usc_candidate_citation():
    # "section 6502(a) of this Act" is COPPA's own section 6502, which the
    # real U.S. Code also numbers 6502 - so this can be a candidate
    # companion-corpus citation (still type named_act_section, still
    # `resolved: False` at extraction time - actual resolution against the
    # companion corpus happens in resolve_usc_against_companion).
    text = "a violation of a regulation prescribed under section 6502(a) of this Act"
    refs = extract_cross_references(text, "312", KNOWN)
    named = [r for r in refs if r["type"] == "named_act_section"]
    assert len(named) == 1
    assert named[0]["target_citation"] == "15 U.S.C. 6502"


def test_named_act_reference_to_a_different_act_gets_no_usc_candidate():
    # true negative: the FTC Act's "section 18" must NOT get a candidate
    # U.S.C. citation - it isn't COPPA, and "18" isn't even in the
    # 3-5-digit shape a real U.S.C. section number in this range would be.
    text = "a rule defining an unfair or deceptive act or practice prescribed under section 18(a)(1)(B) of the Federal Trade Commission Act"
    refs = extract_cross_references(text, "312", KNOWN)
    named = [r for r in refs if r["type"] == "named_act_section"]
    assert len(named) == 1
    assert named[0]["target_citation"] is None


def test_named_act_reference_multiple_sections_each_get_own_entry():
    text = "sections 6503 and 6505 of the Children's Online Privacy Protection Act of 1998"
    refs = extract_cross_references(text, "312", KNOWN)
    named = [r for r in refs if r["type"] == "named_act_section"]
    citations = sorted(r["target_citation"] for r in named)
    assert citations == ["15 U.S.C. 6503", "15 U.S.C. 6505"]


def test_resolve_usc_against_companion_also_resolves_coppa_self_reference():
    sections = [
        {
            "cross_references": [
                {
                    "type": "named_act_section",
                    "raw_text": "section 6502(a) of this Act",
                    "target_citation": "15 U.S.C. 6502",
                    "resolved": False,
                },
                {
                    "type": "named_act_section",
                    "raw_text": "section 18(a)(1)(B) of the Federal Trade Commission Act",
                    "target_citation": None,
                    "resolved": False,
                },
            ]
        }
    ]
    usc_index = {("15", "6502"): "usc-title15-6501-6506"}
    resolve_usc_against_companion(sections, usc_index)
    coppa_ref, ftc_ref = sections[0]["cross_references"]
    assert coppa_ref["companion_resolved"] is True
    # true negative: a named_act_section with no target_citation (a
    # different Act entirely) must be left completely untouched, not
    # crash and not get spurious companion fields.
    assert "companion_resolved" not in ftc_ref


def test_self_reference():
    text = "This part implements the Children's Online Privacy Protection Act."
    refs = extract_cross_references(text, "312", KNOWN)
    self_refs = [r for r in refs if r["type"] == "self_reference"]
    assert len(self_refs) == 1


def test_plain_text_with_no_citations_yields_nothing():
    # true negative: text with zero citation-shaped substrings must not
    # produce any references at all.
    text = "Child means an individual under the age of 13."
    refs = extract_cross_references(text, "312", KNOWN)
    assert refs == []


def test_extract_definitions_finds_simple_and_multiword_terms():
    sections = [
        {
            "citation": "16 CFR 312.2",
            "paragraphs": [
                "Child means an individual under the age of 13.",
                "Parent includes a legal guardian.",
                "Mixed audience website or online service means a website or online service.",
            ],
        }
    ]
    defs = extract_definitions(sections)
    terms = {d["term"] for d in defs}
    assert terms == {"Child", "Parent", "Mixed audience website or online service"}


def test_extract_definitions_ignores_non_definition_paragraphs():
    # true negative: ordinary operative text (no "Term means/includes ..."
    # at the start) must not be mistaken for a definition just because the
    # word "means" appears somewhere in it.
    sections = [
        {
            "citation": "16 CFR 312.3",
            "paragraphs": [
                "It shall be unlawful for any operator to collect personal "
                "information from a child in a manner that means violating "
                "the regulations prescribed under this part.",
                "(a) Provide notice on the website of what it collects.",
            ],
        }
    ]
    assert extract_definitions(sections) == []


def test_resolve_usc_against_companion_marks_in_range_citation():
    sections = [
        {
            "cross_references": [
                {"type": "usc", "raw_text": "15 U.S.C. 6501", "target_citation": "15 U.S.C. 6501", "resolved": False},
            ]
        }
    ]
    usc_index = {("15", "6501"): "usc-title15-6501-6506"}
    resolve_usc_against_companion(sections, usc_index)
    ref = sections[0]["cross_references"][0]
    assert ref["companion_resolved"] is True
    assert ref["companion_corpus"] == "usc-title15-6501-6506"


def test_resolve_usc_against_companion_leaves_out_of_range_citation_unresolved():
    # true negative: a real U.S.C. citation that just isn't in the
    # companion corpus's coverage must not be marked resolved.
    sections = [
        {
            "cross_references": [
                {"type": "usc", "raw_text": "15 U.S.C. 45", "target_citation": "15 U.S.C. 45", "resolved": False},
            ]
        }
    ]
    usc_index = {("15", "6501"): "usc-title15-6501-6506"}
    resolve_usc_against_companion(sections, usc_index)
    ref = sections[0]["cross_references"][0]
    assert ref["companion_resolved"] is False
    assert ref["companion_corpus"] is None


def test_resolve_usc_against_companion_ignores_non_usc_refs():
    sections = [
        {"cross_references": [{"type": "internal_section", "target_citation": "16 CFR 312.4", "resolved": True}]}
    ]
    resolve_usc_against_companion(sections, {("15", "6501"): "usc-title15-6501-6506"})
    # must not add companion fields to a non-usc reference
    assert "companion_resolved" not in sections[0]["cross_references"][0]


def test_other_cfr_part_reference_is_not_internal():
    # a section-shaped citation whose part number differs from this
    # corpus's part must be classified as other_cfr_part, not
    # internal_section, and never marked resolved.
    text = "subject to the requirements of § 1.5 of this chapter"
    refs = extract_cross_references(text, "312", KNOWN)
    other = [r for r in refs if r["type"] == "other_cfr_part"]
    assert len(other) == 1
    assert other[0]["resolved"] is False
