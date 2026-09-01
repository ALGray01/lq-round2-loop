"""Subscription-lane bookkeeping: which lane has token headroom.

A "lane" is one subscription product (e.g. a firm's Claude/ChatGPT/Gemini
seat). Each lane exposes fast/balanced/frontier tiers via its own model
family. Headroom is tracked PER (lane, tier), not per lane as a whole,
because that's how real subscription products actually meter usage: the
scarce/expensive frontier model has a much tighter cap than the cheap
fast model on the same seat. Modeling a single shared per-lane budget
would make "downgrade to a cheaper tier when out of headroom" meaningless,
since the tier you downgrade to would share the same exhausted budget.

The router prefers, among lanes that satisfy the required tier, the one
with the most headroom left at that tier -- so usage spreads across
whatever subscriptions still have room instead of hammering one lane down
to zero while others sit idle.

State (tokens used so far, per lane per tier) is persisted to a JSON file
so headroom tracking survives across CLI invocations within a "day".
There is no actual day-rollover scheduler in this build -- see README
limitations.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "lanes.json"
DEFAULT_STATE_PATH = Path(__file__).parent.parent / "state" / "lanes_state.json"


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_state(path: Path = DEFAULT_STATE_PATH) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict, path: Path = DEFAULT_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def headroom(lane_name: str, tier: str, config: dict, state: dict) -> int:
    cap = config[lane_name]["tiers"][tier]["daily_cap_tokens"]
    used = state.get(lane_name, {}).get(tier, {}).get("used_tokens", 0)
    return cap - used


@dataclass
class LaneChoice:
    lane: str
    tier: str  # the tier ACTUALLY used -- may differ from the tier requested by policy
    model: str
    headroom_before: int
    headroom_after_estimate: int
    fallback_mode: str  # "normal" | "over_budget_escalation" | "downgraded_no_headroom"
    rationale: list[str]

    def to_dict(self) -> dict:
        return {
            "lane": self.lane,
            "tier": self.tier,
            "model": self.model,
            "headroom_before": self.headroom_before,
            "headroom_after_estimate": self.headroom_after_estimate,
            "fallback_mode": self.fallback_mode,
            "rationale": self.rationale,
        }


def _candidates_at_tier(tier: str, estimated_tokens: int, config: dict, state: dict):
    return [
        (name, headroom(name, tier, config, state))
        for name in config.keys()
        if estimated_tokens <= headroom(name, tier, config, state)
    ]


def pick_lane(
    required_tier: str,
    stakes: str,
    estimated_tokens: int,
    config: dict | None = None,
    state: dict | None = None,
) -> LaneChoice:
    """Pick a lane (and its model for required_tier) with headroom.

    Fallback rule when NO lane has headroom at required_tier:
      - stakes == "high": correctness beats cost control for a
        court-bound deliverable. Stay at required_tier, pick the lane
        with the most (least-negative) headroom, and log that we went
        over budget rather than silently under-provisioning the task.
      - stakes != "high": cost control matters more when stakes are low.
        Step down to the next lower tier that DOES have headroom
        somewhere, and log the downgrade explicitly (including the
        effective tier actually used) so it's auditable rather than
        silent. If even the cheapest tier is exhausted everywhere, fall
        through to the same over-budget behavior as stakes=="high", but
        under a DIFFERENT fallback_mode label
        ("over_budget_no_cheaper_tier_available") so the audit log
        doesn't conflate "policy chose not to downgrade" with "tried to
        downgrade and there was nowhere left to go".
    """
    from router.policy import TIER_ORDER  # local import, avoid cycle at module load

    config = config if config is not None else load_config()
    state = state if state is not None else load_state()

    candidates = _candidates_at_tier(required_tier, estimated_tokens, config, state)
    if candidates:
        best_name, best_headroom = max(candidates, key=lambda t: t[1])
        model = config[best_name]["tiers"][required_tier]["model"]
        return LaneChoice(
            lane=best_name,
            tier=required_tier,
            model=model,
            headroom_before=best_headroom,
            headroom_after_estimate=best_headroom - estimated_tokens,
            fallback_mode="normal",
            rationale=[
                f"lane={best_name} tier={required_tier} has headroom {best_headroom} "
                f"tokens >= estimated cost {estimated_tokens}; chosen as max-headroom "
                f"lane among {len(candidates)} eligible lane(s)"
            ],
        )

    # No lane has headroom at required_tier.
    all_headrooms = [
        (name, headroom(name, required_tier, config, state)) for name in config.keys()
    ]
    best_name, best_headroom = max(all_headrooms, key=lambda t: t[1])

    if stakes == "high":
        model = config[best_name]["tiers"][required_tier]["model"]
        return LaneChoice(
            lane=best_name,
            tier=required_tier,
            model=model,
            headroom_before=best_headroom,
            headroom_after_estimate=best_headroom - estimated_tokens,
            fallback_mode="over_budget_escalation",
            rationale=[
                f"no lane had headroom at required_tier={required_tier}; "
                f"stakes=='high' so tier is NOT downgraded",
                f"proceeding over budget on lane={best_name} "
                f"(headroom {best_headroom} < needed {estimated_tokens})",
            ],
        )

    # Step down tiers until we find one with headroom somewhere.
    tiers_to_try = TIER_ORDER[: TIER_ORDER.index(required_tier)][::-1]
    for lower_tier in tiers_to_try:
        lower_candidates = _candidates_at_tier(lower_tier, estimated_tokens, config, state)
        if lower_candidates:
            best_name2, best_headroom2 = max(lower_candidates, key=lambda t: t[1])
            model = config[best_name2]["tiers"][lower_tier]["model"]
            return LaneChoice(
                lane=best_name2,
                tier=lower_tier,
                model=model,
                headroom_before=best_headroom2,
                headroom_after_estimate=best_headroom2 - estimated_tokens,
                fallback_mode="downgraded_no_headroom",
                rationale=[
                    f"no lane had headroom at required_tier={required_tier} "
                    f"and stakes={stakes!r} != 'high', so downgraded to tier={lower_tier}",
                    f"chosen lane={best_name2} with headroom {best_headroom2}",
                ],
            )

    # Every lane is out of headroom at every tier, including the cheapest
    # one: there is nothing left to downgrade INTO. Proceed over budget on
    # the least-negative lane at the originally required tier rather than
    # refusing to serve the request. This is deliberately a DIFFERENT
    # fallback_mode from the stakes=='high' case above: that one reflects
    # a policy choice (never downgrade a high-stakes request); this one
    # reflects that downgrading was attempted and simply had nowhere to
    # go. Conflating the two under one label would misrepresent *why* the
    # request went over budget in the audit log.
    model = config[best_name]["tiers"][required_tier]["model"]
    return LaneChoice(
        lane=best_name,
        tier=required_tier,
        model=model,
        headroom_before=best_headroom,
        headroom_after_estimate=best_headroom - estimated_tokens,
        fallback_mode="over_budget_no_cheaper_tier_available",
        rationale=[
            f"no lane had headroom at required_tier={required_tier}, and no "
            f"cheaper tier had headroom either (stakes={stakes!r}); "
            "every lane is out of headroom at every tier",
            f"proceeding over budget on lane={best_name} rather than "
            "refusing to serve the request",
        ],
    )


def consume(lane_name: str, tier: str, tokens: int, state: dict) -> dict:
    lane_entry = state.setdefault(lane_name, {})
    tier_entry = lane_entry.setdefault(tier, {"used_tokens": 0})
    tier_entry["used_tokens"] = tier_entry.get("used_tokens", 0) + tokens
    return state
