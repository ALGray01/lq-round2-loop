"""Top-level Router: text (+ optional overrides) in, RoutingDecision out."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

from .cap_tracker import CapTracker
from .classifier import Classification, Classifier, KeywordClassifier
from .models import ModelProfile, load_registry
from .policy import RoutingDecision, select
from .taxonomy import Stakes, TaskType


@dataclass
class RouteResult:
    classification: Classification
    decision: RoutingDecision

    def to_dict(self) -> dict:
        d = {
            "task_type": self.decision.task_type.value,
            "task_type_confidence": self.classification.confidence,
            "matched_keywords": list(self.classification.matched_keywords),
            "stakes": self.decision.stakes.value,
            "chosen_model": self.decision.chosen_model_id,
            "capability_score": self.decision.capability_score,
            "cost_per_1m_blended_usd": self.decision.cost_per_1m_blended_usd,
            "below_capability_floor": self.decision.below_capability_floor,
            "cap_exceeded": self.decision.cap_exceeded,
            "human_review_required": self.decision.human_review_required,
            "requires_external_verification": self.decision.requires_external_verification,
            "ranked_candidates": self.decision.ranked_candidates,
            "rationale": self.decision.rationale,
            "warnings": self.decision.warnings,
        }
        return d


class Router:
    def __init__(
        self,
        registry_path: Path | None = None,
        cap_state_path: Path | None = None,
        classifier: Classifier | None = None,
    ):
        self.models: list[ModelProfile] = load_registry(registry_path)
        self.cap_tracker = CapTracker(state_path=cap_state_path)
        self.classifier: Classifier = classifier or KeywordClassifier()

    def route(
        self,
        text: str,
        stakes: str | Stakes,
        task_type: str | TaskType | None = None,
        estimated_tokens: int = 2000,
        min_context_tokens: int = 0,
    ) -> RouteResult:
        stakes_enum = Stakes(stakes) if isinstance(stakes, str) else stakes

        if task_type is not None:
            tt = TaskType(task_type) if isinstance(task_type, str) else task_type
            classification = Classification(tt, 1.0, ("explicit override",))
        else:
            classification = self.classifier.classify(text)

        decision = select(
            self.models,
            classification.task_type,
            stakes_enum,
            self.cap_tracker,
            estimated_tokens=estimated_tokens,
            min_context_tokens=min_context_tokens,
        )
        return RouteResult(classification=classification, decision=decision)

    def record_usage(self, model_id: str, tokens: int):
        return self.cap_tracker.record_usage(model_id, tokens)
