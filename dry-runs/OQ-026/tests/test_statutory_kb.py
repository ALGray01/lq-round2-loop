"""
Second bounded area, same schema, same engine, no code path specific to
this KB other than the generic mechanisms in engine.py (see its module
docstring). Expected outcomes here are again real, independently-checkable
facts: Loper Bright actually overrules Chevron (2024, very well covered),
the major questions doctrine actually gates ordinary interpretation
(West Virginia v. EPA, 2022), and the rule of lenity actually applies only
as a last resort (United States v. Bass).
"""

from pathlib import Path

from methodology_layer.engine import FactPattern, annotate_clause
from methodology_layer.models import REPO_ROOT, load_kb

KB_PATH = REPO_ROOT / "knowledge_base" / "statutory_construction" / "kb.yaml"


def _kb():
    return load_kb(KB_PATH, validate=True)


def test_statutory_kb_validates_against_the_unchanged_schema():
    """The whole point of this second KB: it must validate against
    schema/methodology_layer.schema.json with zero schema changes."""
    kb = _kb()
    assert len(kb.authorities) == 8
    assert len(kb.doctrinal_rules) == 8


def test_major_questions_doctrine_gates_ordinary_plain_meaning():
    """West Virginia v. EPA: the major-questions clear-statement requirement
    is checked first (priority 5) and disposes of the case before ordinary
    plain-meaning analysis (priority 10) is ever reached."""
    kb = _kb()
    fp = FactPattern(major_questions_raised=True, extrinsic_evidence_offered=True)
    result = annotate_clause(kb, "clause_mq", "US-federal", fp)
    assert result["threshold_determination"]["test_applied"] == "Major questions doctrine (clear-statement gate)"
    assert "clear congressional authorization required and absent" in result["threshold_determination"]["outcome"]


def test_ordinary_plain_meaning_applies_when_major_questions_not_raised():
    """Same jurisdiction, same rule set, opposite fact -- confirms the
    engine actually falls through to the second threshold rule rather than
    always stopping at the first one it finds (this is exactly the
    generalization that required rewriting _apply_threshold to walk an
    ordered list instead of assuming one threshold rule per jurisdiction)."""
    kb = _kb()
    fp = FactPattern(major_questions_raised=False, extrinsic_evidence_offered=True)
    result = annotate_clause(kb, "clause_pm", "US-federal", fp)
    assert result["threshold_determination"]["test_applied"] == "Statutory plain-meaning rule"


def test_loper_bright_overruling_chevron_surfaces_when_skidmore_rule_cited():
    """Loper Bright Enterprises v. Raimondo (2024) overrules Chevron U.S.A.
    v. NRDC (1984). rule_skidmore_respect's authority_basis includes
    case_chevron specifically so this tension is citable; confirms the
    generic _conflicting_authority_for mechanism (built for the contract KB)
    picks up an entirely different KB's overrules relation with no
    KB-specific code."""
    kb = _kb()
    fp = FactPattern(evidence_conflict_sources=["agency_interpretation"])
    result = annotate_clause(kb, "clause_chevron", "US-federal", fp)
    assert "pr_loper_overrules_chevron" in result["conflicting_authority"]
    rule_ids = [r["rule_id"] for r in result["applicable_rules"]]
    assert "rule_skidmore_respect" in rule_ids


def test_rule_of_lenity_is_last_resort_like_contra_proferentem():
    """United States v. Bass: lenity applies only where ordinary tools of
    construction don't resolve the ambiguity -- same 'last resort, not
    first move' shape as contra proferentem in the contract KB, but gated
    on a different FactPattern flag (criminal_statute) via the same generic
    requires_flag mechanism, not a copy-pasted contract-specific check."""
    kb = _kb()

    fp_with_canon = FactPattern(structural_pattern="specific_list_then_general_catchall", criminal_statute=True)
    result = annotate_clause(kb, "clause_lenity_1", "US-federal", fp_with_canon)
    rule_ids = [r["rule_id"] for r in result["applicable_rules"]]
    assert "rule_ejusdem_generis_statutory" in rule_ids
    assert "rule_of_lenity" not in rule_ids

    fp_without_canon = FactPattern(criminal_statute=True)
    result2 = annotate_clause(kb, "clause_lenity_2", "US-federal", fp_without_canon)
    rule_ids2 = [r["rule_id"] for r in result2["applicable_rules"]]
    assert rule_ids2 == ["rule_of_lenity"]


def test_rule_of_lenity_does_not_fire_for_civil_statutes():
    """Confirms requires_flag genuinely gates the rule -- a fact pattern
    that would trigger contra proferentem's flag (unequal_bargaining_power)
    in the contract KB must NOT trigger lenity here, since lenity's flag is
    criminal_statute specifically, and this KB doesn't even define
    unequal_bargaining_power-triggered rules."""
    kb = _kb()
    fp = FactPattern(unequal_bargaining_power=True, criminal_statute=False)
    result = annotate_clause(kb, "clause_civil", "US-federal", fp)
    assert result["applicable_rules"] == []
