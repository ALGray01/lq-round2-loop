"""The routing policy: task type x stakes -> tier + verification requirement.

This module is the actual "policy doc" -- it is code, not a diagram, so it
can be unit-tested and its decisions can be logged. See README.md for the
prose rationale; this is where that rationale is enforced.

TIERS
-----
fast     - cheap/fast model. Good for mechanical, pattern-following work
           where errors are cheap to catch and the task doesn't require
           deep multi-step reasoning.
balanced - mid-tier model. Default for most substantive legal work:
           drafting, review, research synthesis.
frontier - the most reliable tier available. Reserved for the hardest
           reasoning tasks and for anything high-stakes, regardless of
           how "hard" the task looks on its face.

TIER_ORDER defines a total order used to compute max(a, b).
"""
from __future__ import annotations

from dataclasses import dataclass

TIER_ORDER = ("fast", "balanced", "frontier")


def _tier_rank(tier: str) -> int:
    return TIER_ORDER.index(tier)


def _max_tier(a: str, b: str) -> str:
    return a if _tier_rank(a) >= _tier_rank(b) else b


# Baseline tier by task type, BEFORE stakes is applied. This is the part of
# the policy that is most defensibly informed-by-benchmarks-as-weak-prior:
# litigation reasoning is the task type most benchmarks (LegalBench,
# CaseHOLD-style tasks, contract-NLI) and practitioner reports agree
# degrades fastest on weaker models, so it gets the frontier floor even at
# low stakes. Citation checking is comparatively mechanical (pattern
# matching against a citation, not open-ended reasoning) so it can run on
# the fast tier by default.
TASK_TYPE_DEFAULT_TIER: dict[str, str] = {
    "citation_check": "fast",
    "legal_research": "balanced",
    "contract_review": "balanced",
    "transactional_drafting": "balanced",
    "litigation_reasoning": "frontier",
}

# Stakes sets a FLOOR on tier and whether a verification pass is mandatory.
# "low" imposes no floor (task-type default governs). "high" is the
# court-bound-deliverable extreme case named in the brief: frontier tier,
# mandatory verification pass, no exceptions.
STAKES_FLOOR_TIER: dict[str, str | None] = {
    "low": None,
    "medium": "balanced",
    "high": "frontier",
}

STAKES_REQUIRES_VERIFICATION: dict[str, bool] = {
    "low": False,
    "medium": False,
    "high": True,
}


@dataclass
class TierDecision:
    tier: str
    verification_required: bool
    rationale: list[str]

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "verification_required": self.verification_required,
            "rationale": self.rationale,
        }


def decide_tier(task_type: str, stakes: str) -> TierDecision:
    if task_type not in TASK_TYPE_DEFAULT_TIER:
        raise ValueError(f"unknown task_type: {task_type!r}")
    if stakes not in STAKES_FLOOR_TIER:
        raise ValueError(f"unknown stakes: {stakes!r}")

    default_tier = TASK_TYPE_DEFAULT_TIER[task_type]
    floor = STAKES_FLOOR_TIER[stakes]
    rationale = [f"task_type={task_type} default_tier={default_tier}"]

    if floor is None:
        effective = default_tier
    else:
        effective = _max_tier(default_tier, floor)
        if effective != default_tier:
            rationale.append(
                f"stakes={stakes} imposes tier floor={floor}, "
                f"raised from {default_tier} to {effective}"
            )
        else:
            rationale.append(
                f"stakes={stakes} floor={floor} did not exceed task default"
            )

    verification_required = STAKES_REQUIRES_VERIFICATION[stakes]
    rationale.append(
        f"verification_required={verification_required} "
        f"(mandatory whenever stakes=='high')"
    )

    return TierDecision(
        tier=effective,
        verification_required=verification_required,
        rationale=rationale,
    )
