"""Command-line entrypoint for the router.

Usage:
    python -m router.cli "your request text here"
    python -m router.cli "your request text here" --stakes high
    python -m router.cli --file request.txt --stakes high
"""
from __future__ import annotations

import argparse
import json
import sys

from router.router import route_request


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Legal-task-aware model router")
    parser.add_argument("text", nargs="?", help="request text")
    parser.add_argument("--file", help="read request text from a file instead")
    parser.add_argument(
        "--stakes",
        choices=["low", "medium", "high"],
        default=None,
        help="explicit caller-provided stakes (trusted; sets a floor text can only raise)",
    )
    parser.add_argument("--json", action="store_true", help="print full decision as JSON")
    args = parser.parse_args(argv)

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        parser.error("provide request text as an argument or via --file")
        return 2

    decision = route_request(text, explicit_stakes=args.stakes)

    if args.json:
        print(json.dumps(decision.to_log_entry(), indent=2))
        return 0

    c = decision.classification
    t = decision.tier_decision
    l = decision.lane_choice
    print(f"task_type      : {c.task_type} (confidence={c.task_type_confidence:.2f}, signals={c.task_type_signals})")
    print(f"stakes         : {c.stakes} (source={c.stakes_source}, signals={c.stakes_signals})")
    print(f"required tier  : {t.tier}")
    if l.tier != t.tier:
        print(f"effective tier : {l.tier}  <-- differs from required tier, see fallback_mode below")
    print(f"verification   : {'required' if t.verification_required else 'not required'}")
    print(f"lane           : {l.lane} -> model={l.model} (fallback_mode={l.fallback_mode})")
    print(f"headroom       : {l.headroom_before} -> ~{l.headroom_after_estimate} tokens")
    print("rationale:")
    for r in t.rationale + l.rationale:
        print(f"  - {r}")
    print()
    print("draft response:")
    print(decision.draft_response)
    if decision.verification:
        print()
        print(f"verification passed: {decision.verification['passed']}")
        if decision.verification["pattern_check"]["findings"]:
            print("pattern-check findings:")
            for finding in decision.verification["pattern_check"]["findings"]:
                print(f"  - {finding}")
        print("model critic response:")
        print(decision.verification["model_critic_response"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
