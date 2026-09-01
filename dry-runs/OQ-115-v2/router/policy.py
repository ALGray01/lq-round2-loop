"""Scoring and selection policy: turns (task type, stakes, cap state) into
a ranked list of models and a single recommendation with caveats.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .cap_tracker import CapTracker
from .models import CAPABILITY_FIELDS, ModelProfile
from .taxonomy import REQUIRES_EXTERNAL_VERIFICATION, STAKES_POLICY, TASK_TYPE_WEIGHTS, Stakes, TaskType


@dataclass
class Candidate:
    model: ModelProfile
    capability_score: float  # weighted 1-5 scale
    cost_norm: float         # 0-5 scale, relative to registry
    score: float             # capability_score - cost_weight * cost_norm
    has_headroom: bool


@dataclass
class RoutingDecision:
    task_type: TaskType
    stakes: Stakes
    chosen_model_id: str
    capability_score: float
    cost_per_1m_blended_usd: float
    below_capability_floor: bool
    cap_exceeded: bool
    human_review_required: bool
    requires_external_verification: bool
    ranked_candidates: list[tuple[str, float]]
    rationale: str = ""
    warnings: list[str] = field(default_factory=list)


def _capability_score(model: ModelProfile, weights: dict[str, float]) -> float:
    return sum(weights[f] * model.capability(f) for f in CAPABILITY_FIELDS)


def _cost_norm(model: ModelProfile, all_models: list[ModelProfile]) -> float:
    costs = [m.cost_per_1m_blended_usd for m in all_models]
    lo, hi = min(costs), max(costs)
    if hi == lo:
        return 0.0
    return 5.0 * (model.cost_per_1m_blended_usd - lo) / (hi - lo)


def rank_candidates(
    models: list[ModelProfile],
    task_type: TaskType,
    stakes: Stakes,
    cap_tracker: CapTracker,
    estimated_tokens: int,
    min_context_tokens: int = 0,
) -> list[Candidate]:
    weights = TASK_TYPE_WEIGHTS[task_type]
    cost_weight = STAKES_POLICY[stakes]["cost_weight"]

    eligible = [m for m in models if m.context_window_tokens >= min_context_tokens]
    pool = eligible or models  # never return an empty pool; caller sees the caveat instead

    candidates = []
    for m in pool:
        cap_score = _capability_score(m, weights)
        cost_norm = _cost_norm(m, models)
        score = cap_score - cost_weight * cost_norm
        headroom = cap_tracker.has_headroom(m.id, estimated_tokens)
        candidates.append(Candidate(m, cap_score, cost_norm, score, headroom))

    # Rank by score desc; tie-break by lower cost, then higher speed.
    candidates.sort(key=lambda c: (-c.score, c.model.cost_per_1m_blended_usd, -c.model.speed))
    return candidates


def select(
    models: list[ModelProfile],
    task_type: TaskType,
    stakes: Stakes,
    cap_tracker: CapTracker,
    estimated_tokens: int = 2000,
    min_context_tokens: int = 0,
) -> RoutingDecision:
    candidates = rank_candidates(models, task_type, stakes, cap_tracker, estimated_tokens, min_context_tokens)
    ranked = [(c.model.id, round(c.score, 3)) for c in candidates]
    warnings: list[str] = []

    if stakes == Stakes.HIGH:
        # High stakes: never silently downgrade quality to save cap budget.
        # Take the top-ranked candidate outright; flag if it will blow the cap
        # so a human makes the overage call, rather than the router making it.
        chosen = candidates[0]
        if not chosen.has_headroom:
            warnings.append(
                f"{chosen.model.id} is over its tracked token cap for this period; "
                "proceeding anyway because stakes=high, but this will run over budget."
            )
    else:
        # Low/medium stakes: skip models without headroom, to conserve the
        # capped budget on frontier models for when stakes actually demand it.
        with_headroom = [c for c in candidates if c.has_headroom]
        if with_headroom:
            chosen = with_headroom[0]
            if chosen.model.id != candidates[0].model.id:
                warnings.append(
                    f"top-ranked {candidates[0].model.id} is at its token cap; "
                    f"substituted next-best {chosen.model.id} to conserve remaining budget."
                )
        else:
            chosen = candidates[0]
            warnings.append(
                "every candidate model is at its tracked token cap; proceeding with the "
                f"top-ranked {chosen.model.id} anyway (no cheaper option available)."
            )

    floor = STAKES_POLICY[stakes]["capability_floor"]
    below_floor = chosen.capability_score < floor
    if below_floor:
        warnings.append(
            f"{chosen.model.id}'s weighted capability score {chosen.capability_score:.2f} "
            f"is below the recommended floor {floor} for stakes={stakes.value}."
        )

    requires_verification = task_type in REQUIRES_EXTERNAL_VERIFICATION
    human_review = STAKES_POLICY[stakes]["human_review_required"] or requires_verification

    weights = TASK_TYPE_WEIGHTS[task_type]
    cost_weight = STAKES_POLICY[stakes]["cost_weight"]
    top_weighted_field = max(weights, key=weights.get)
    rationale = (
        f"{task_type.value} weights {top_weighted_field} most heavily ({weights[top_weighted_field]:.0%}); "
        f"stakes={stakes.value} sets cost_weight={cost_weight} and a capability floor of {floor}. "
        f"{chosen.model.id} ranked highest of {len(candidates)} candidates with weighted capability "
        f"{chosen.capability_score:.2f}/5 at ${chosen.model.cost_per_1m_blended_usd}/1M tokens."
    )

    return RoutingDecision(
        task_type=task_type,
        stakes=stakes,
        chosen_model_id=chosen.model.id,
        capability_score=round(chosen.capability_score, 3),
        cost_per_1m_blended_usd=chosen.model.cost_per_1m_blended_usd,
        below_capability_floor=below_floor,
        cap_exceeded=not chosen.has_headroom,
        human_review_required=human_review,
        requires_external_verification=requires_verification,
        rationale=rationale,
        ranked_candidates=ranked,
        warnings=warnings,
    )
