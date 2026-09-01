"""
Engine tests. Every expected outcome here is a real, independently-checkable
doctrinal fact -- the holding of a specific reported case or the text of a
specific statute/restatement section -- decided by courts or the ALI, not by
this codebase. That is deliberate: FAILURE-CLASSES.md #2 and #3 warn against
ground truth written by the same process, in the same sitting, as the code
being tested. If these tests pass, it is because the engine reproduces
outcomes fixed by outside authority, not because the code and the tests
agree with each other in a closed loop. Where a fact pattern is fictional
(the clauses themselves are), the applicable *rule* it triggers is not.
"""

from pathlib import Path

from methodology_layer.engine import FactPattern, annotate_clause
from methodology_layer.models import REPO_ROOT, load_kb

KB_PATH = REPO_ROOT / "knowledge_base" / "contract_interpretation" / "kb.yaml"


def _kb():
    return load_kb(KB_PATH, validate=True)


def test_california_admits_extrinsic_evidence_even_when_facially_clear():
    """PG&E v. Thomas Drayage, 69 Cal.2d 33 (1968): extrinsic evidence must
    be provisionally admitted even where the contract looks unambiguous."""
    kb = _kb()
    fp = FactPattern(facially_ambiguous=False, extrinsic_evidence_offered=True)
    result = annotate_clause(kb, "clause_1", "US-CA", fp)
    assert result["threshold_determination"]["test_applied"] == "Contextualist / reasonably-susceptible rule (CA)"
    assert "provisionally admissible" in result["threshold_determination"]["outcome"]


def test_newport_beach_narrows_pge_for_undisclosed_subjective_intent():
    """Founding Members of the Newport Beach Country Club v. Newport Beach
    Country Club, Inc., 109 Cal. App. 4th 944 (2003): verified against the
    actual opinion text via web search (see README.md's Verification
    section) after an earlier draft of this KB mischaracterized the
    holding as a "sophisticated parties represented by counsel" carve-out,
    which the case does not contain. The real limitation is the objective
    theory of contracts -- undisclosed subjective intent never
    communicated to the other side is not the kind of extrinsic evidence
    PG&E's reasonably-susceptible test requires courts to consider. This
    test previously did not exist for this branch at all, which is exactly
    how the citation error went unnoticed for as long as it did."""
    kb = _kb()
    fp = FactPattern(extrinsic_evidence_offered=True, only_undisclosed_subjective_intent_offered=True)
    result = annotate_clause(kb, "clause_newport", "US-CA", fp)
    outcome = result["threshold_determination"]["outcome"]
    assert "undisclosed subjective intent" in outcome
    assert "not the kind of extrinsic evidence" in outcome
    assert "pr_newport_limits_pge" in result["conflicting_authority"]


def test_new_york_bars_extrinsic_evidence_when_facially_clear():
    """W.W.W. Assocs. v. Giancontieri, 77 N.Y.2d 157 (1990): the reverse
    outcome, same fact pattern, opposite jurisdiction -- this is the actual
    doctrinal split, not two branches of one rule."""
    kb = _kb()
    fp = FactPattern(facially_ambiguous=False, extrinsic_evidence_offered=True)
    result = annotate_clause(kb, "clause_1", "US-NY", fp)
    assert result["threshold_determination"]["test_applied"] == "Four corners / plain meaning rule (NY)"
    assert "inadmissible" in result["threshold_determination"]["outcome"]


def test_ninth_circuit_borrows_california_rule_but_flags_the_tension():
    """Trident Center, 847 F.2d 564 (9th Cir. 1988): applies PG&E because
    Erie requires it to apply CA substantive law, while on record disagreeing
    with the rule. The engine must reproduce both halves of that: the CA
    rule controls (not a made-up 9th-circuit-federal-common-law rule), and
    the criticism relation is surfaced, not hidden."""
    kb = _kb()
    fp = FactPattern(facially_ambiguous=False, extrinsic_evidence_offered=True)
    result = annotate_clause(kb, "clause_1", "US-federal-9th-cir", fp)
    assert result["threshold_determination"]["test_applied"] == "Contextualist / reasonably-susceptible rule (CA)"
    assert "pr_trident_criticizes_pge" in result["conflicting_authority"]


def test_ucc_hierarchy_prefers_course_of_performance_over_usage_of_trade():
    """UCC 1-303(e): express terms > course of performance > course of
    dealing > usage of trade, when they conflict and cannot be reconciled."""
    kb = _kb()
    fp = FactPattern(
        contract_type="goods_sale",
        evidence_conflict_sources=["usage_of_trade", "course_of_performance"],
    )
    result = annotate_clause(kb, "clause_2", "US-CA", fp)
    rule_ids_in_order = [r["rule_id"] for r in result["applicable_rules"]]
    assert rule_ids_in_order.index("rule_course_of_performance") < rule_ids_in_order.index("rule_usage_of_trade")


def test_ejusdem_generis_triggers_on_specific_list_then_catchall():
    """Restatement (2d) Contracts §202 canon: 'cars, trucks, motorcycles, and
    other vehicles' -- the general catchall is read to include only things of
    the same kind as the enumerated items."""
    kb = _kb()
    fp = FactPattern(structural_pattern="specific_list_then_general_catchall")
    result = annotate_clause(kb, "clause_3", "US-NY", fp)
    rule_ids = [r["rule_id"] for r in result["applicable_rules"]]
    assert "rule_ejusdem_generis" in rule_ids


def test_contra_proferentem_is_last_resort_not_first_move():
    """Restatement (2d) Contracts §206: contra proferentem applies only when
    other interpretive rules do not resolve the ambiguity. If a canon already
    resolves the pattern, contra proferentem must not also fire."""
    kb = _kb()
    fp_with_canon = FactPattern(
        structural_pattern="specific_list_then_general_catchall",
        unequal_bargaining_power=True,
    )
    result = annotate_clause(kb, "clause_4", "US-NY", fp_with_canon)
    rule_ids = [r["rule_id"] for r in result["applicable_rules"]]
    assert "rule_ejusdem_generis" in rule_ids
    assert "rule_contra_proferentem" not in rule_ids

    fp_without_canon = FactPattern(unequal_bargaining_power=True)
    result2 = annotate_clause(kb, "clause_4", "US-NY", fp_without_canon)
    rule_ids2 = [r["rule_id"] for r in result2["applicable_rules"]]
    assert rule_ids2 == ["rule_contra_proferentem"]


def test_authority_weight_favors_binding_over_persuasive_same_court_level():
    """PG&E is binding in California and merely persuasive everywhere else
    (it has never been adopted as the rule in New York, which affirmatively
    rejects it in Giancontieri). Same case, same court level, different
    jurisdiction -> different weight. This is the computed-weight formula
    from weighting.py, not an asserted number."""
    from methodology_layer import weighting

    kb = _kb()
    pge = kb.authorities["case_pge"]
    weight_in_ca = weighting.compute_weight(pge, "US-CA")
    weight_in_ny = weighting.compute_weight(pge, "US-NY")
    assert weight_in_ca > weight_in_ny
    assert weighting.role_of(pge, "US-CA") == "binding"
    assert weighting.role_of(pge, "US-NY") == "persuasive"


def test_statute_not_enacted_in_jurisdiction_has_zero_weight():
    """A statute-type authority whose binding_in list does not include the
    queried jurisdiction is not 'weak' there, it is inapplicable -- weight
    must be exactly 0, not some small positive persuasive value, because an
    un-enacted statute is not a source of law in that jurisdiction at all."""
    from methodology_layer import weighting

    kb = _kb()
    ucc = kb.authorities["statute_ucc_1_303"]
    assert weighting.compute_weight(ucc, "US-TX") == 0.0
