"""End-to-end demonstration of the router, run for real (not asserted).

Writes its own decision log to demo/demo_log.jsonl (fresh each run, using
an isolated lane-state file so it doesn't disturb state/lanes_state.json)
and prints a human-readable trace of each scenario to stdout. A copy of a
real run's log is committed at demo/sample_routing_log.jsonl as evidence
-- regenerate it any time with:

    python demo.py

Scenarios:
  1. Low-stakes citation check       -> fast tier, no verification
  2. Medium-stakes contract review   -> balanced tier, no verification
  3. HIGH-stakes litigation reasoning, court-bound -> frontier tier +
     mandatory verification pass (the brief's required end-to-end case)
  4. Headroom exhaustion, low stakes  -> demonstrates the tier-downgrade
     fallback (simulated by pre-draining the demo lane state)
  5. Headroom exhaustion, high stakes -> demonstrates the over-budget
     escalation fallback (tier is NOT downgraded even though every lane
     is out of headroom)
"""
from __future__ import annotations

import json
from pathlib import Path

from router.lanes import load_config, save_state
from router.router import route_request

DEMO_DIR = Path(__file__).parent / "demo"
STATE_PATH = DEMO_DIR / "demo_state.json"
LOG_PATH = DEMO_DIR / "demo_log.jsonl"
SAMPLE_LOG_PATH = DEMO_DIR / "sample_routing_log.jsonl"


def _print_decision(label: str, decision) -> None:
    c, t, l = decision.classification, decision.tier_decision, decision.lane_choice
    print(f"\n=== {label} ===")
    print(f"request        : {decision.request_text[:100]!r}")
    print(f"task_type      : {c.task_type} (confidence={c.task_type_confidence:.2f})")
    print(f"stakes         : {c.stakes} (source={c.stakes_source})")
    print(f"required tier  : {t.tier}   effective tier: {l.tier}   fallback_mode: {l.fallback_mode}")
    print(f"lane/model     : {l.lane} / {l.model}")
    print(f"verification   : {'required' if t.verification_required else 'not required'}")
    if decision.verification:
        print(f"  -> passed: {decision.verification['passed']}")
        if decision.verification["pattern_check"]["findings"]:
            for f in decision.verification["pattern_check"]["findings"]:
                print(f"     finding: {f}")
    print(f"draft response : {decision.draft_response[:160]}...")


def main() -> None:
    if LOG_PATH.exists():
        LOG_PATH.unlink()
    if STATE_PATH.exists():
        STATE_PATH.unlink()

    config = load_config()

    # --- Scenario 1: low-stakes, mechanical task ---
    d1 = route_request(
        "Please verify the citation: 410 U.S. 113 (1973), Bluebook format.",
        config=config, state_path=STATE_PATH, log_path=LOG_PATH,
    )
    _print_decision("1. Low-stakes citation check", d1)
    assert d1.tier_decision.tier == "fast"
    assert d1.verification is None
    assert d1.lane_choice.fallback_mode == "normal"

    # --- Scenario 2: medium-stakes review ---
    d2 = route_request(
        "We're about to sign this vendor MSA -- can you review it and flag risky clauses?",
        config=config, state_path=STATE_PATH, log_path=LOG_PATH,
    )
    _print_decision("2. Medium-stakes contract review", d2)
    assert d2.tier_decision.tier == "balanced"
    assert d2.verification is None
    assert d2.lane_choice.fallback_mode == "normal"

    # --- Scenario 3: HIGH-stakes, court-bound, escalation + verification ---
    d3 = route_request(
        "This is the final version of our argument on the motion to dismiss, "
        "to be filed with the court tomorrow morning -- opposing counsel will see this.",
        config=config, state_path=STATE_PATH, log_path=LOG_PATH,
    )
    _print_decision("3. HIGH-stakes litigation reasoning (court-bound)", d3)
    assert d3.classification.stakes == "high"
    assert d3.tier_decision.tier == "frontier"
    assert d3.tier_decision.verification_required is True
    assert d3.verification is not None
    assert d3.lane_choice.fallback_mode == "normal"

    # --- Scenario 4: low-stakes request, frontier AND balanced headroom
    #     pre-drained on every lane -> should downgrade to fast tier ---
    drained_state = {}
    for lane_name, lane_cfg in config.items():
        drained_state[lane_name] = {
            "frontier": {"used_tokens": lane_cfg["tiers"]["frontier"]["daily_cap_tokens"]},
            "balanced": {"used_tokens": lane_cfg["tiers"]["balanced"]["daily_cap_tokens"]},
        }
    save_state(drained_state, STATE_PATH)
    d4 = route_request(
        "What is the standard for piercing the corporate veil in Delaware?",
        config=config, state_path=STATE_PATH, log_path=LOG_PATH,
    )
    _print_decision("4. Low-stakes request, frontier+balanced exhausted -> downgrade", d4)
    assert d4.lane_choice.fallback_mode == "downgraded_no_headroom"
    assert d4.lane_choice.tier == "fast"

    # --- Scenario 5: HIGH-stakes request, every tier on every lane
    #     exhausted -> must NOT downgrade, goes over budget instead ---
    fully_drained_state = {}
    for lane_name, lane_cfg in config.items():
        fully_drained_state[lane_name] = {
            tier: {"used_tokens": tier_cfg["daily_cap_tokens"]}
            for tier, tier_cfg in lane_cfg["tiers"].items()
        }
    save_state(fully_drained_state, STATE_PATH)
    d5 = route_request(
        "Final version to be filed with the court: argument on our motion to dismiss.",
        config=config, state_path=STATE_PATH, log_path=LOG_PATH,
    )
    _print_decision("5. HIGH-stakes request, ALL lanes/tiers exhausted -> over-budget escalation", d5)
    assert d5.classification.stakes == "high"
    assert d5.lane_choice.fallback_mode == "over_budget_escalation"
    assert d5.lane_choice.tier == "frontier"  # NOT downgraded despite zero headroom

    DEMO_DIR.mkdir(exist_ok=True)
    SAMPLE_LOG_PATH.write_text(LOG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"\nAll 5 scenarios ran and asserted correctly.")
    print(f"Log written to {LOG_PATH} and copied to {SAMPLE_LOG_PATH} as committed evidence.")


if __name__ == "__main__":
    main()
