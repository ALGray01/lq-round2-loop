"""Command-line entry point.

Examples:
  python -m router route --text "Draft an NDA for a new vendor" --stakes medium
  python -m router route --text "..." --stakes high --task-type citation_checking
  python -m router record-usage --model claude-sonnet --tokens 15000
  python -m router stats
"""

from __future__ import annotations

import argparse
import json
import sys

from .models import RegistryError
from .router import Router
from .taxonomy import TaskType


def _non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {value}")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="router")
    sub = p.add_subparsers(dest="command", required=True)

    route_p = sub.add_parser("route", help="Route one request to a model")
    route_p.add_argument("--text", required=True, help="The task description / prompt")
    route_p.add_argument("--stakes", required=True, choices=["low", "medium", "high"])
    route_p.add_argument("--task-type", default=None, choices=[t.value for t in TaskType],
                          help="Override the classifier")
    route_p.add_argument("--estimated-tokens", type=_non_negative_int, default=2000)
    route_p.add_argument("--min-context-tokens", type=_non_negative_int, default=0)

    usage_p = sub.add_parser("record-usage", help="Record actual tokens consumed by a model")
    usage_p.add_argument("--model", required=True)
    usage_p.add_argument("--tokens", type=_non_negative_int, required=True)

    sub.add_parser("stats", help="Show current cap usage for all tracked models")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        router = Router()
    except RegistryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.command == "route":
        result = router.route(
            text=args.text,
            stakes=args.stakes,
            task_type=args.task_type,
            estimated_tokens=args.estimated_tokens,
            min_context_tokens=args.min_context_tokens,
        )
        print(json.dumps(result.to_dict(), indent=2))
        return 0

    if args.command == "record-usage":
        status = router.record_usage(args.model, args.tokens)
        print(json.dumps({"model": status.model_id, "used": status.used, "cap": status.cap,
                           "remaining": status.remaining}, indent=2))
        return 0

    if args.command == "stats":
        tracker = router.cap_tracker
        # Union of caps and usage keys, not just caps: a typo'd/unregistered
        # --model in record-usage still persists its usage and must stay
        # visible here (with unbounded cap, since it isn't a tracked model),
        # rather than silently disappearing from view.
        all_ids = sorted(set(tracker.caps) | set(tracker.usage))
        out = {mid: {"used": tracker.status(mid).used, "cap": tracker.status(mid).cap,
                      "remaining": tracker.status(mid).remaining}
               for mid in all_ids}
        print(json.dumps(out, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
