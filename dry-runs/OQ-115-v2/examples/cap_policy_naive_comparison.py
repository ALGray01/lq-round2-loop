"""Compares the real router's stakes-aware cap policy against two naive
alternatives someone might plausibly build instead. Round 1's baseline
comparison (naive_baseline_comparison.py) attacked the router's "which
model" claim; this attacks its OTHER core claim -- token-cap conservation
that discriminates by stakes ("silently substitute at low/medium stakes;
never silently downgrade at high stakes -- flag an overage instead").

  a) dumb_cap_enforcer -- fail closed. If ANY tracked model is at/over its
     cap, refuse every request outright until an admin clears it. A
     plausible naive design: "don't let anything through once the budget
     system reports trouble."
  b) always_substitute -- fail open, uniformly. Whatever the stakes,
     silently swap in the next-ranked model with headroom. No stakes
     carve-out at all -- "keep working with whatever's available."

Both are implemented directly against the real router/models.json registry
and the real CapTracker (so cap math and ranking math are identical to the
real router's -- only the cap POLICY differs), then run through one
concrete scenario: push claude-opus to its cap, then route a high-stakes,
about-to-be-filed citation-checking request through all three.

Run: python examples/cap_policy_naive_comparison.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from router.cap_tracker import CapTracker  # noqa: E402
from router.models import load_registry  # noqa: E402
from router.policy import rank_candidates  # noqa: E402
from router.router import Router  # noqa: E402
from router.taxonomy import Stakes, TaskType  # noqa: E402


def dumb_cap_enforcer(models, task_type, stakes, cap_tracker, estimated_tokens=2000):
    """Fail closed: if ANY tracked model is over its cap, refuse everything."""
    exhausted = [mid for mid in cap_tracker.caps if cap_tracker.status(mid).exhausted]
    if exhausted:
        return {
            "chosen_model": None,
            "refused": True,
            "reason": f"request refused: model(s) at cap ({', '.join(exhausted)}); "
                      f"system halted until an admin clears the cap state.",
        }
    candidates = rank_candidates(models, task_type, stakes, cap_tracker, estimated_tokens)
    return {"chosen_model": candidates[0].model.id, "refused": False, "reason": "under cap, routed normally"}


def always_substitute(models, task_type, stakes, cap_tracker, estimated_tokens=2000):
    """Fail open, uniformly: always swap to next-with-headroom, regardless of stakes."""
    candidates = rank_candidates(models, task_type, stakes, cap_tracker, estimated_tokens)
    with_headroom = [c for c in candidates if c.has_headroom]
    if with_headroom:
        chosen = with_headroom[0]
        substituted = chosen.model.id != candidates[0].model.id
        return {
            "chosen_model": chosen.model.id,
            "refused": False,
            "silently_downgraded": substituted,
            "reason": (f"substituted {chosen.model.id} for capped-out {candidates[0].model.id} "
                       f"(no stakes carve-out)" if substituted else "top pick had headroom"),
        }
    chosen = candidates[0]
    return {"chosen_model": chosen.model.id, "refused": False, "silently_downgraded": False,
            "reason": "no model has headroom; proceeding with top-ranked anyway"}


def main():
    models = load_registry()

    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "cap_state.json"

        tracker = CapTracker(state_path=state_path)
        tracker.record_usage("claude-opus", 2_000_000)
        print("Setup: claude-opus pushed to its tracked cap.")
        print(json.dumps({"model": "claude-opus", **{k: getattr(tracker.status("claude-opus"), k)
                                                       for k in ("cap", "used", "remaining")}}, indent=2))
        print()

        text = "Verify this citation before we file the reply brief -- due to the court tomorrow morning"
        stakes = Stakes.HIGH
        task_type = TaskType.CITATION_CHECKING

        print(f'Scenario request: "{text}"  (stakes=high, task_type=citation_checking)')
        print()

        real_router = Router(cap_state_path=state_path)
        real_result = real_router.route(text=text, stakes="high", task_type="citation_checking")
        real_dict = real_result.to_dict()
        print("=== A. Real router (router/policy.py::select) ===")
        print(json.dumps({k: real_dict[k] for k in
                          ("chosen_model", "cap_exceeded", "human_review_required", "warnings")}, indent=2))
        print()

        dumb_result = dumb_cap_enforcer(models, task_type, stakes, tracker)
        print("=== B. Naive baseline: dumb_cap_enforcer (fail closed on ANY capped model) ===")
        print(json.dumps(dumb_result, indent=2))
        print()

        sub_result = always_substitute(models, task_type, stakes, tracker)
        print("=== C. Naive baseline: always_substitute (fail open, no stakes carve-out) ===")
        print(json.dumps(sub_result, indent=2))


if __name__ == "__main__":
    main()
