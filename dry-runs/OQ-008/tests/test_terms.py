import pytest

from lmd.errors import BuildError
from lmd.render import build_html

VALID_DOC = """\
# Definitions

This Agreement is between Acme (the [Company]{.def}) and Beta (the
[Recipient]{.def}).

# Obligations

The [Company]{.term} shall pay the [Recipient]{.term} on time.
"""

UNDEFINED_TERM_DOC = """\
# Obligations

The [Company]{.term} shall pay on time.
"""

DUPLICATE_DEF_DOC = """\
# Definitions

The [Company]{.def} is Acme.

# More Definitions

The [Company]{.def} is actually Beta.
"""


def test_defined_term_usage_links_back_to_its_definition():
    html_out = build_html(VALID_DOC)
    assert 'id="term-company"' in html_out
    assert '<a class="lmd-term-ref" href="#term-company">Company</a>' in html_out


def test_using_an_undefined_term_actually_fails_the_build():
    """Crafted bad input, run for real: a [.term] usage with no matching
    [.def] anywhere in the document must raise, not silently render the
    term as plain text.
    """
    with pytest.raises(BuildError, match="never defined"):
        build_html(UNDEFINED_TERM_DOC)


def test_defining_the_same_term_twice_fails_the_build():
    with pytest.raises(BuildError, match="defined more than once"):
        build_html(DUPLICATE_DEF_DOC)
