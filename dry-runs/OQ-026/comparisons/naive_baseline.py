#!/usr/bin/env python3
"""
Baseline comparison artifact, kept deliberately (not scratch).

Built by an independent auditor subagent during this session's reserve-phase
review, to test the implicit claim that the shipped structured methodology
layer (schema/methodology_layer.schema.json + methodology_layer/engine.py +
weighting.py) is worth its complexity for the bounded contract-interpretation
demo. This is the naive/boring alternative: a single if/elif chain with
hardcoded jurisdiction checks and a literal (authority, jurisdiction) ->
weight lookup table sized to exactly what the 5 demo.py scenarios need. No
JSON Schema, no KnowledgeBase abstraction, no computed-weight formula.

Verified result (see README.md's Baseline comparison section): on the 5
demo.py scenarios exactly as posed, this reproduces the shipped engine's
output field-for-field -- the structure buys nothing there. Asked a question
outside that anticipated set (see __main__ below), it has no answer, where
the shipped engine's computed weight formula does. Run directly
(`python comparisons/naive_baseline.py`) to see both halves for yourself.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FactPattern:
    contract_type: str = "services"
    facially_ambiguous: bool = False
    extrinsic_evidence_offered: bool = False
    structural_pattern: str | None = None
    evidence_conflict_sources: list[str] = field(default_factory=list)
    unequal_bargaining_power: bool = False
    sophisticated_parties_represented_by_counsel: bool = False


# ---------------------------------------------------------------------------
# Hardcoded "weights" -- literal numbers, one per (authority, jurisdiction)
# combo that the demo scenarios actually need. This is the naive analogue of
# weighting.compute_weight(): instead of a formula, just the numbers that
# make the known scenarios come out right.
# ---------------------------------------------------------------------------
HARDCODED_WEIGHTS = {
    ("case_pge", "US-CA"): (120.0, "binding"),
    ("case_pge", "US-NY"): (60.0, "persuasive"),
    ("case_pge", "US-federal-9th-cir"): (60.0, "persuasive"),
    ("case_giancontieri", "US-NY"): (120.0, "binding"),
    ("statute_ucc_1_303", "US-CA"): (90.0, "binding"),
    ("case_frigaliment", "US-CA"): (30.0, "persuasive"),
    ("restatement_202", "US-NY"): (40.0, "persuasive"),
    ("restatement_206", "US-NY"): (40.0, "persuasive"),
}


def weight_of(authority_id: str, jurisdiction: str):
    # Naive version: if the combo wasn't anticipated, we simply don't know.
    return HARDCODED_WEIGHTS.get((authority_id, jurisdiction), (None, None))


def annotate_clause(clause_id: str, jurisdiction: str, fp: FactPattern) -> dict:
    conflicting: list[str] = []
    applicable_rules: list[dict] = []
    citations: list[dict] = []

    # --- threshold: CA vs NY vs 9th Circuit (Erie-borrows CA), hardcoded ---
    if jurisdiction == "US-CA" or jurisdiction == "US-federal-9th-cir":
        if fp.extrinsic_evidence_offered or fp.facially_ambiguous:
            outcome = (
                "provisionally admissible: extrinsic evidence must be considered to test whether the "
                "language is reasonably susceptible to the meaning urged, regardless of facial clarity"
            )
        else:
            outcome = "not reached: no extrinsic evidence offered and no facial ambiguity alleged"
        test_applied = "Contextualist / reasonably-susceptible rule (CA)"
        authority = "case_pge"
        if jurisdiction == "US-federal-9th-cir":
            conflicting.append("pr_trident_criticizes_pge")
            outcome += " [borrowed from US-CA law under Erie]"
    elif jurisdiction == "US-NY":
        if fp.facially_ambiguous:
            outcome = "ambiguity appears on the face of the document; extrinsic evidence is admissible to resolve it"
        elif fp.extrinsic_evidence_offered:
            outcome = (
                "inadmissible: contract is unambiguous on its face, and the four-corners rule "
                "bars extrinsic evidence regardless of what is offered"
            )
        else:
            outcome = "not reached: no extrinsic evidence offered and no facial ambiguity alleged"
        test_applied = "Four corners / plain meaning rule (NY)"
        authority = "case_giancontieri"
    else:
        # naive fallback: this jurisdiction was simply never anticipated
        test_applied = None
        outcome = "no codified threshold rule for this jurisdiction (not hardcoded)"
        authority = None

    threshold = {"test_applied": test_applied, "outcome": outcome, "authority": authority}
    w, role = weight_of(authority, jurisdiction) if authority else (None, None)
    if authority and w is not None:
        citations.append({"authority_id": authority, "weight": w, "role": role})

    # --- UCC hierarchy: hardcoded priority via if/elif on source names ---
    if fp.contract_type == "goods_sale" and fp.evidence_conflict_sources:
        order = ["express_terms", "course_of_performance", "course_of_dealing", "usage_of_trade"]
        rule_names = {
            "express_terms": ("rule_express_terms", 1),
            "course_of_performance": ("rule_course_of_performance", 2),
            "course_of_dealing": ("rule_course_of_dealing", 3),
            "usage_of_trade": ("rule_usage_of_trade", 4),
        }
        for source in order:
            if source in fp.evidence_conflict_sources:
                rid, pr = rule_names[source]
                applicable_rules.append({"rule_id": rid, "priority": pr, "weight": 90.0})
        w, role = weight_of("statute_ucc_1_303", jurisdiction)
        if w is not None:
            citations.append({"authority_id": "statute_ucc_1_303", "weight": w, "role": role})
        w, role = weight_of("case_frigaliment", jurisdiction)
        if w is not None:
            citations.append({"authority_id": "case_frigaliment", "weight": w, "role": role})

    # --- canons: hardcoded if/elif on structural_pattern string ---
    canon_fired = False
    if fp.structural_pattern == "specific_list_then_general_catchall":
        applicable_rules.append({"rule_id": "rule_ejusdem_generis", "priority": 30, "weight": 40.0})
        canon_fired = True
        w, role = weight_of("restatement_202", jurisdiction)
        if w is not None:
            citations.append({"authority_id": "restatement_202", "weight": w, "role": role})
    elif fp.structural_pattern == "ambiguous_word_among_associated_words":
        applicable_rules.append({"rule_id": "rule_noscitur_a_sociis", "priority": 31, "weight": 40.0})
        canon_fired = True
    elif fp.structural_pattern == "enumerated_list_no_catchall":
        applicable_rules.append({"rule_id": "rule_expressio_unius", "priority": 32, "weight": 40.0})
        canon_fired = True

    # --- fallback: contra proferentem, only if nothing else fired ---
    ucc_fired = fp.contract_type == "goods_sale" and bool(fp.evidence_conflict_sources)
    if fp.unequal_bargaining_power and not canon_fired and not ucc_fired:
        applicable_rules.append({"rule_id": "rule_contra_proferentem", "priority": 90, "weight": 40.0})
        w, role = weight_of("restatement_206", jurisdiction)
        if w is not None:
            citations.append({"authority_id": "restatement_206", "weight": w, "role": role})

    applicable_rules.sort(key=lambda r: r["priority"])
    citations.sort(key=lambda c: -c["weight"])

    if applicable_rules:
        lead = applicable_rules[0]
        posture = f"Threshold: {threshold['outcome']}. Controlling interpretive rule: {lead['rule_id']} (priority {lead['priority']} of {len(applicable_rules)} triggered)."
    else:
        posture = f"Threshold: {threshold['outcome']}. No downstream interpretive rule triggered by this fact pattern."

    return {
        "clause_id": clause_id,
        "jurisdiction": jurisdiction,
        "threshold_determination": threshold,
        "applicable_rules": applicable_rules,
        "conflicting_authority": conflicting,
        "recommended_interpretive_posture": posture,
        "citations": citations,
    }


if __name__ == "__main__":
    import json

    scenarios = [
        ("scenario_1", "US-CA", FactPattern(facially_ambiguous=False, extrinsic_evidence_offered=True)),
        ("scenario_1", "US-NY", FactPattern(facially_ambiguous=False, extrinsic_evidence_offered=True)),
        ("scenario_2", "US-federal-9th-cir", FactPattern(facially_ambiguous=False, extrinsic_evidence_offered=True)),
        ("scenario_3", "US-CA", FactPattern(contract_type="goods_sale", evidence_conflict_sources=["usage_of_trade", "course_of_performance"])),
        ("scenario_4", "US-NY", FactPattern(structural_pattern="specific_list_then_general_catchall")),
        ("scenario_5", "US-NY", FactPattern(unequal_bargaining_power=True)),
    ]
    for cid, jur, fp in scenarios:
        print("=" * 60, cid, jur)
        print(json.dumps(annotate_clause(cid, jur, fp), indent=2))

    print("\n" + "=" * 60)
    print("EDGE CASE the shipped engine's test suite checks but this naive")
    print("version was never told about: statute weight in an un-enacted")
    print("jurisdiction (US-TX), and PG&E's weight/role outside CA/NY/9th-Cir.")
    print(weight_of("statute_ucc_1_303", "US-TX"))
    print(weight_of("case_pge", "US-federal-2nd-cir"))
