import pytest

from lmd.errors import BuildError
from lmd.render import build_html

VALID_DOC = """\
# Confidentiality {#confidentiality}

Some clause text.

# Remedies

See [[ref:confidentiality]] for the confidentiality obligations.
"""

BROKEN_DOC = """\
# Confidentiality {#confidentiality}

Some clause text.

# Remedies

See [[ref:this-anchor-does-not-exist]] for details.
"""


def test_valid_cross_reference_resolves_to_current_number():
    html_out = build_html(VALID_DOC)
    assert '<a class="lmd-ref" href="#confidentiality">Section 1</a>' in html_out


def test_broken_cross_reference_actually_fails_the_build():
    """This is the crafted-bad-input check FAILURE-CLASSES.md item 5 asks
    for: a cross-reference to an anchor that was never defined must raise,
    not render a dead link or the literal text -- verified by actually
    calling build_html() on a broken document, not by reading the code.
    """
    with pytest.raises(BuildError) as exc_info:
        build_html(BROKEN_DOC)
    assert "this-anchor-does-not-exist" in str(exc_info.value)


def test_duplicate_explicit_anchor_id_fails_the_build():
    doc = "# One {#dup}\n\n# Two {#dup}\n"
    with pytest.raises(BuildError, match="duplicate anchor id 'dup'"):
        build_html(doc)
