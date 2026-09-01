#!/usr/bin/env python3
"""
Runnable demo: for a handful of realistic contract clauses, show

  1. what a raw entity-extraction pass (Isaacus/Kanon-style NER) gives an
     LLM today, and
  2. what the methodology layer gives it instead/in addition: doctrinal
     hierarchy, authority weighting, precedent tension, all resolved for a
     specific jurisdiction and fact pattern.

Run: python demo.py
"""

from __future__ import annotations

import json
from pathlib import Path

from methodology_layer.engine import FactPattern, annotate_clause
from methodology_layer.entity_extraction_stub import extract_entities
from methodology_layer.models import load_kb

KB_PATH = Path(__file__).parent / "knowledge_base" / "contract_interpretation" / "kb.yaml"


SCENARIOS = [
    {
        "title": "Scenario 1 -- same clause, two jurisdictions (the CA/NY interpretive split)",
        "clause_text": (
            "This Agreement may not be extended beyond its Initial Term of 3 years "
            "except by written instrument signed by both the Buyer and the Seller."
        ),
        "jurisdictions": ["US-CA", "US-NY"],
        "fact_pattern": FactPattern(facially_ambiguous=False, extrinsic_evidence_offered=True),
        "note": (
            "One party offers evidence of an oral side-agreement extending the term. The clause "
            "text is identical; only the jurisdiction changes. Raw entity extraction cannot see "
            "that this changes the legal answer -- the methodology layer's job is exactly to see it."
        ),
    },
    {
        "title": "Scenario 2 -- a federal court borrowing state law (Erie / Trident Center)",
        "clause_text": (
            "Buyer shall have no right to accelerate or prepay any portion of the outstanding balance "
            "prior to the Maturity Date."
        ),
        "jurisdictions": ["US-federal-9th-cir"],
        "fact_pattern": FactPattern(facially_ambiguous=False, extrinsic_evidence_offered=True),
        "note": (
            "This is Trident Center's actual fact pattern (a categorical no-prepayment clause). A "
            "9th Circuit panel applying California law is bound by PG&E even though it called the "
            "result absurd. The annotation must surface that tension, not launder it away."
        ),
    },
    {
        "title": "Scenario 3 -- UCC hierarchy: conflicting course of performance vs. usage of trade",
        "clause_text": (
            "Seller shall deliver Grade A produce, with quality determined per prevailing industry "
            "standard, and Buyer has accepted three prior shipments without objection."
        ),
        "jurisdictions": ["US-CA"],
        "fact_pattern": FactPattern(
            contract_type="goods_sale",
            evidence_conflict_sources=["usage_of_trade", "course_of_performance"],
        ),
        "note": (
            "Two sources of extrinsic meaning point in different directions. UCC 1-303(e) fixes "
            "the priority order by statute; this is not a judgment call the engine is making."
        ),
    },
    {
        "title": "Scenario 4 -- structural canon: specific list + general catchall",
        "clause_text": (
            "Lessee shall not park cars, trucks, motorcycles, or other vehicles on the lawn."
        ),
        "jurisdictions": ["US-NY"],
        "fact_pattern": FactPattern(structural_pattern="specific_list_then_general_catchall"),
        "note": (
            "Does 'other vehicles' include a bicycle or a ride-on lawnmower? Ejusdem generis reads "
            "the catchall in light of the specific items that precede it."
        ),
    },
    {
        "title": "Scenario 5 -- last resort: contra proferentem with no other canon available",
        "clause_text": (
            "Coverage excludes damage arising from 'normal wear and tear', a term this policy does "
            "not define."
        ),
        "jurisdictions": ["US-NY"],
        "fact_pattern": FactPattern(unequal_bargaining_power=True),
        "note": (
            "An adhesive insurance policy, no structural canon applies, and no other rule resolves "
            "the ambiguity -- contra proferentem is the fallback of last resort, not first move."
        ),
    },
    {
        "title": "Scenario 6 -- Newport Beach Country Club narrows PG&E (objective theory of contracts)",
        "clause_text": (
            "Right of First Offer under this Agreement extends to any member organization of the Club "
            "existing as of the date hereof."
        ),
        "jurisdictions": ["US-CA"],
        "fact_pattern": FactPattern(extrinsic_evidence_offered=True, only_undisclosed_subjective_intent_offered=True),
        "note": (
            "PG&E's reasonably-susceptible test still applies in California, but Newport Beach Country "
            "Club narrows it: undisclosed subjective intent -- internal communications never conveyed to "
            "the other side -- is not the kind of extrinsic evidence the test requires courts to admit. "
            "(This scenario replaced an earlier, inaccurate one after web-search verification found the "
            "case's actual holding didn't match this KB's first draft -- see README.md's Verification "
            "section.)"
        ),
    },
]


def run():
    kb = load_kb(KB_PATH, validate=True)

    for i, scenario in enumerate(SCENARIOS, 1):
        print("=" * 100)
        print(scenario["title"])
        print("-" * 100)
        print(f'Clause text: "{scenario["clause_text"]}"')
        print(f"Fact pattern: {scenario['note']}")
        print()

        print("[1] Raw entity extraction (Isaacus/Kanon-style NER) -- what an LLM sees today:")
        entities = extract_entities(scenario["clause_text"])
        print(json.dumps(entities, indent=2) if entities else "  (no entities matched -- this stub is intentionally minimal)")
        print()

        for jurisdiction in scenario["jurisdictions"]:
            print(f"[2] Methodology-layer InterpretiveAnnotation -- jurisdiction={jurisdiction}:")
            annotation = annotate_clause(kb, f"scenario_{i}", jurisdiction, scenario["fact_pattern"])
            print(json.dumps(annotation, indent=2))
            print()
        print()


if __name__ == "__main__":
    run()
