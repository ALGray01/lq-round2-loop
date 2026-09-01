"""
Authority-weighting formula.

Deliberately NOT a per-authority hardcoded number in the knowledge base --
that would make "weight" whatever the KB author wanted it to be, which is
exactly the kind of dressed-up-as-reasoning shortcut this project's own
FAILURE-CLASSES.md warns about. Instead weight is *computed* at query time
from three declared facts about the authority (type, court level, whether it
binds in the jurisdiction being queried), via a formula fixed once here and
applied uniformly. Disagree with the formula's shape and you can change it
in one place; you can't quietly special-case one authority to win a demo.
"""

from __future__ import annotations

# Base weight by authority type, for non-case authorities. Ordered to
# reflect the conventional common-law hierarchy of sources: positive law
# (constitution/statute/regulation) outweighs secondary/persuasive
# commentary (restatement/treatise), regardless of jurisdiction.
BASE_BY_TYPE = {
    "constitution": 100,
    "statute": 90,
    "regulation": 80,
    "restatement": 40,
    "treatise": 20,
}

# Base weight by court level, for case authorities. This is the "how high
# up the judicial hierarchy did this come from" axis.
COURT_LEVEL_SCORE = {
    "scotus": 70,
    "state_supreme": 60,
    "federal_circuit": 55,
    "state_appellate": 45,
    "federal_district": 30,
    "state_trial": 20,
    "n/a": 0,
}

# A case that binds the queried jurisdiction counts double a case that is
# merely persuasive there. This is the axis that lets a lower-ranked but
# binding case beat a higher-ranked but merely-persuasive one -- e.g. a
# state appellate case binding in its own district can outweigh an
# out-of-jurisdiction state supreme court case cited only for its
# persuasive value.
BINDING_MULTIPLIER = 2.0
PERSUASIVE_MULTIPLIER = 1.0


def is_binding(authority: dict, jurisdiction: str) -> bool:
    return jurisdiction in (authority.get("binding_in") or [])


def compute_weight(authority: dict, jurisdiction: str) -> float:
    """Return the authority's weight when cited to a court sitting in `jurisdiction`.

    Positive law (statute/regulation/constitution) that was never enacted in
    the queried jurisdiction is not "weak" there, it is inapplicable: weight
    0. Restatements and treatises are secondary authority everywhere by
    construction (binding_in is always empty for them in this KB) so their
    weight does not vary with jurisdiction. Cases get the binding/persuasive
    multiplier because the same opinion really does carry different force
    depending on who is looking at it.
    """
    atype = authority["type"]

    if atype == "case":
        base = COURT_LEVEL_SCORE[authority.get("court_level", "n/a")]
        multiplier = BINDING_MULTIPLIER if is_binding(authority, jurisdiction) else PERSUASIVE_MULTIPLIER
        return base * multiplier

    base = BASE_BY_TYPE[atype]
    if atype in ("constitution", "statute", "regulation"):
        binding_in = authority.get("binding_in") or []
        if binding_in and jurisdiction not in binding_in:
            return 0.0
        return float(base)

    # restatement / treatise: persuasive-only everywhere, by definition.
    return float(base)


def role_of(authority: dict, jurisdiction: str) -> str:
    if authority["type"] == "case":
        return "binding" if is_binding(authority, jurisdiction) else "persuasive"
    if authority["type"] in ("constitution", "statute", "regulation"):
        binding_in = authority.get("binding_in") or []
        return "binding" if (not binding_in or jurisdiction in binding_in) else "persuasive"
    return "persuasive"
