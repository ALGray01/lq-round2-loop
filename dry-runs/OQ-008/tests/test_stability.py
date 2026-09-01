"""Tests the central claim of SPEC.md section 1 / section 3.1: the anchor
ID identifying a clause and the number a reader sees are two different
things, and reordering sibling sections must change the number without
touching the anchor -- and a cross-reference into the moved section must
follow it to its new number automatically, with no manual renumbering.
"""
import re

from lmd.render import build_html


def _number_for(html_out: str, anchor: str) -> str:
    m = re.search(
        rf'id="{anchor}"[^>]*>\s*<span class="lmd-number">([^<]+)</span>', html_out
    )
    assert m, f"no heading with id={anchor!r} found in output"
    return m.group(1)

ORIGINAL_ORDER = """\
# Confidentiality {#confidentiality}

Confidentiality obligations go here.

# Indemnification {#indemnification}

See [[ref:confidentiality]] for the related confidentiality duties.

# Governing Law {#governing-law}

Delaware law applies.
"""

REORDERED = """\
# Governing Law {#governing-law}

Delaware law applies.

# Confidentiality {#confidentiality}

Confidentiality obligations go here.

# Indemnification {#indemnification}

See [[ref:confidentiality]] for the related confidentiality duties.
"""


def test_reordering_sections_changes_numbers_but_not_anchors():
    original = build_html(ORIGINAL_ORDER)
    reordered = build_html(REORDERED)

    # Same three anchor ids exist in both builds -- reordering never
    # invents or drops an anchor.
    for anchor in ("confidentiality", "indemnification", "governing-law"):
        assert f'id="{anchor}"' in original
        assert f'id="{anchor}"' in reordered

    # In the original order Confidentiality is Section 1; after moving
    # Governing Law to the front, Confidentiality becomes Section 2.
    assert _number_for(original, "confidentiality") == "1"
    assert _number_for(reordered, "confidentiality") == "2"

    # The cross-reference to #confidentiality inside Indemnification
    # automatically tracks the move: "Section 1" in the original,
    # "Section 2" after reordering -- without editing the reference itself.
    assert '<a class="lmd-ref" href="#confidentiality">Section 1</a>' in original
    assert '<a class="lmd-ref" href="#confidentiality">Section 2</a>' in reordered
