"""Numbering correctness: computed independently by hand before checking
against the implementation (not derived by reading what the code emits).

Doc structure used below:
  # A          -> 1
  ## A.1       -> 1.1
  ### A.1.a    -> 1.1(a)
  #### A.1.a.i -> 1.1(a)(i)
  ## A.2       -> 1.2               (level-2 counter advances, deeper reset)
  # B          -> 2                 (level-1 counter advances, all reset)
  ## B.1       -> 2.1
"""
import pytest

from lmd.errors import BuildError
from lmd.numbering import compute_numbering, to_alpha_lower, to_roman_lower

SCHEME = ["decimal", "decimal", "alpha-lower", "roman-lower"]

DOC = """\
# A
## A.1
### A.1.a
#### A.1.a.i
## A.2
# B
## B.1
"""


def test_expected_numbers_in_document_order():
    result = compute_numbering(DOC, SCHEME)
    numbers = [h.number for h in result.headings]
    assert numbers == ["1", "1.1", "1.1(a)", "1.1(a)(i)", "1.2", "2", "2.1"]


def test_skipping_a_heading_level_is_a_build_error():
    """# A followed directly by ### A.1.a (no ## in between) is a document
    authoring mistake, not a case that should silently compute a bogus
    number like "1.0(a)". This was caught by hand-checking the algorithm
    before writing this test -- the first draft of compute_numbering()
    would have silently produced "1.0(a)" here.
    """
    doc = "# A\n### A.1.a\n"
    with pytest.raises(BuildError, match="skips from 1 to 3"):
        compute_numbering(doc, SCHEME)


def test_anchors_are_slugified_from_title_when_not_explicit():
    result = compute_numbering(DOC, SCHEME)
    assert "a" in result.anchors
    assert "b" in result.anchors
    assert result.anchors["a"].number == "1"


def test_explicit_anchor_id_is_used_verbatim():
    doc = "# Confidentiality {#confidentiality}\n"
    result = compute_numbering(doc, SCHEME)
    assert "confidentiality" in result.anchors
    assert result.anchors["confidentiality"].number == "1"


def test_alpha_lower_overflows_like_a_spreadsheet_column():
    assert to_alpha_lower(1) == "a"
    assert to_alpha_lower(26) == "z"
    assert to_alpha_lower(27) == "aa"


def test_roman_lower_small_values():
    assert to_roman_lower(1) == "i"
    assert to_roman_lower(4) == "iv"
    assert to_roman_lower(9) == "ix"
    assert to_roman_lower(14) == "xiv"
