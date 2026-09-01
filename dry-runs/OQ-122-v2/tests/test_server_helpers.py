"""Unit tests for the small helper functions in server/statutes_mcp.py
that don't need the full MCP protocol round-trip to exercise (that's what
tests/test_mcp_client.py is for). Importing the module is safe - it only
starts the server under `if __name__ == "__main__"`.

Run: python -m pytest tests/test_server_helpers.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from statutes_mcp import normalize_citation, normalize_usc_citation, safe_repr  # noqa: E402


def test_normalize_citation_accepts_several_forms():
    assert normalize_citation("16 CFR 312.5") == "312.5"
    assert normalize_citation("312.5") == "312.5"
    assert normalize_citation("§ 312.5") == "312.5"
    assert normalize_citation("312.5(c)(1)") == "312.5"


def test_normalize_citation_rejects_oversized_input():
    assert normalize_citation("A" * 100000 + "312.5") is None


def test_normalize_citation_returns_none_for_no_match():
    assert normalize_citation("not a citation") is None


def test_safe_repr_bounds_output_size_for_escape_heavy_input():
    # A round-2 audit finding: truncating by *input* character count isn't
    # enough, because repr() escapes non-printable characters (a
    # zero-width space becomes the 6-character "​"), so escape-heavy
    # input can render far longer than the input slice suggests. The
    # rendered output itself must stay bounded.
    payload = "312.5" + ("​" * 1000)  # 1000 zero-width spaces
    result = safe_repr(payload)
    assert len(result) < 500, f"safe_repr output ballooned to {len(result)} chars"


def test_safe_repr_plain_ascii_under_limit_is_unchanged():
    assert safe_repr("312.5") == "'312.5'"


def test_safe_repr_marks_truncation_when_it_happens():
    result = safe_repr("A" * 100000)
    assert "truncated" in result
    assert len(result) < 500


def test_normalize_usc_citation_accepts_title_15_forms():
    assert normalize_usc_citation("15 U.S.C. 6501") == "6501"
    assert normalize_usc_citation("6501") == "6501"
    assert normalize_usc_citation("§ 6501") == "6501"


def test_normalize_usc_citation_rejects_a_different_stated_title():
    # A fresh-context audit found this exact bug: before the title was
    # validated, any of these returned "6501" (Title 15's real text)
    # despite explicitly naming a different title.
    assert normalize_usc_citation("20 U.S.C. 6501") is None
    assert normalize_usc_citation("42 U.S.C. 6501") is None
    assert normalize_usc_citation("5 U.S.C. 6501") is None


def test_normalize_usc_citation_rejects_malformed_reversed_order():
    assert normalize_usc_citation("6501 U.S.C. 20") is None


def test_normalize_usc_citation_rejects_worded_form_with_wrong_title():
    # A second fresh-context audit found the abbreviated-form fix above
    # didn't cover the WORDED citation form ("of title N, United States
    # Code") - these all previously bypassed title validation entirely
    # and returned Title 15's real text regardless of the stated title.
    assert normalize_usc_citation("section 6502 of title 20, United States Code") is None
    assert normalize_usc_citation("section 6502 of title 42, United States Code") is None
    assert normalize_usc_citation("20 United States Code 6502") is None
    assert normalize_usc_citation("Title 20, section 6502") is None


def test_normalize_usc_citation_accepts_worded_form_with_correct_title():
    assert normalize_usc_citation("section 6501 of title 15, United States Code") == "6501"


def test_normalize_usc_citation_rejects_oversized_input():
    assert normalize_usc_citation("A" * 100000 + "6501") is None
