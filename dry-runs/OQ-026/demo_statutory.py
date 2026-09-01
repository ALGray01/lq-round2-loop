#!/usr/bin/env python3
"""
Second runnable demo, against knowledge_base/statutory_construction/kb.yaml.

Exists to demonstrate, not just claim, that schema/methodology_layer.schema.json
and methodology_layer/engine.py generalize to a bounded area of law that has
nothing to do with contracts: resolving ambiguity in federal statutory text.
Same InterpretiveAnnotation shape, same engine code, a completely different
knowledge base.

Run: python demo_statutory.py
"""

from __future__ import annotations

import json
from pathlib import Path

from methodology_layer.engine import FactPattern, annotate_clause
from methodology_layer.models import load_kb

KB_PATH = Path(__file__).parent / "knowledge_base" / "statutory_construction" / "kb.yaml"

SCENARIOS = [
    {
        "title": "Scenario A -- major questions doctrine gates ordinary interpretation",
        "note": (
            "An agency claims a novel statutory basis for a program of vast economic significance "
            "(West Virginia v. EPA's actual fact pattern: EPA claiming Clean Air Act authority to "
            "restructure the national power grid). The major-questions threshold rule (priority 5) "
            "must dispose of the case before the ordinary plain-meaning rule (priority 10) is reached."
        ),
        "jurisdiction": "US-federal",
        "fact_pattern": FactPattern(major_questions_raised=True, extrinsic_evidence_offered=True),
    },
    {
        "title": "Scenario B -- same jurisdiction, ordinary plain-meaning question",
        "note": (
            "No major-questions flag this time -- the engine must fall through to the second "
            "threshold rule in priority order rather than stopping at the first one it finds."
        ),
        "jurisdiction": "US-federal",
        "fact_pattern": FactPattern(major_questions_raised=False, extrinsic_evidence_offered=True),
    },
    {
        "title": "Scenario C -- agency interpretation offered, Chevron's overruling surfaces",
        "note": (
            "An agency's own interpretation of a statute it administers is offered as authority. "
            "Skidmore respect (not Chevron deference) is the live rule; the annotation must still "
            "surface that Chevron -- once the controlling rule -- was overruled by Loper Bright, "
            "since a reader unaware of that history could otherwise treat Chevron as good law."
        ),
        "jurisdiction": "US-federal",
        "fact_pattern": FactPattern(evidence_conflict_sources=["agency_interpretation"]),
    },
    {
        "title": "Scenario D -- rule of lenity, criminal statute, no other canon resolves it",
        "note": (
            "United States v. Bass's actual posture: a criminal statute's scope is genuinely "
            "ambiguous and no structural canon applies -- lenity is the last-resort tiebreaker."
        ),
        "jurisdiction": "US-federal",
        "fact_pattern": FactPattern(criminal_statute=True),
    },
    {
        "title": "Scenario E -- civil statute, same ambiguity shape, lenity must NOT apply",
        "note": (
            "Confirms lenity is genuinely gated on criminal_statute and not on 'no other rule fired' "
            "alone -- a civil statute with the identical unresolved-ambiguity shape gets no fallback "
            "canon at all in this KB, which is doctrinally correct: lenity is criminal-law-specific."
        ),
        "jurisdiction": "US-federal",
        "fact_pattern": FactPattern(criminal_statute=False),
    },
]


def run():
    kb = load_kb(KB_PATH, validate=True)
    for i, scenario in enumerate(SCENARIOS, 1):
        print("=" * 100)
        print(scenario["title"])
        print("-" * 100)
        print(f"Fact pattern: {scenario['note']}")
        print()
        annotation = annotate_clause(kb, f"statutory_scenario_{i}", scenario["jurisdiction"], scenario["fact_pattern"])
        print(json.dumps(annotation, indent=2))
        print()


if __name__ == "__main__":
    run()
