"""Legal task taxonomy: task types and stakes levels.

These are the two axes the router conditions on. Task type determines
*which model capabilities matter*; stakes determines *how much quality
should be traded for cost/speed, and whether a human-review flag is owed*.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TaskType(str, Enum):
    LITIGATION_REASONING = "litigation_reasoning"
    TRANSACTIONAL_DRAFTING = "transactional_drafting"
    CONTRACT_REVIEW = "contract_review"
    LEGAL_RESEARCH = "legal_research"
    CITATION_CHECKING = "citation_checking"
    GENERAL = "general"


class Stakes(str, Enum):
    LOW = "low"       # internal memo, brainstorming, exploratory draft
    MEDIUM = "medium"  # client-facing but not yet filed/executed
    HIGH = "high"     # goes on the record: filed, signed, sent to opposing counsel


# Capability weight vectors: how much each task type cares about each
# model capability. Must sum to 1.0 per task type (enforced by a test).
TASK_TYPE_WEIGHTS: dict[TaskType, dict[str, float]] = {
    TaskType.LITIGATION_REASONING: {
        "reasoning": 0.60, "drafting": 0.15, "factual_accuracy": 0.25,
    },
    TaskType.TRANSACTIONAL_DRAFTING: {
        "reasoning": 0.25, "drafting": 0.55, "factual_accuracy": 0.20,
    },
    TaskType.CONTRACT_REVIEW: {
        "reasoning": 0.30, "drafting": 0.10, "factual_accuracy": 0.60,
    },
    TaskType.LEGAL_RESEARCH: {
        "reasoning": 0.35, "drafting": 0.10, "factual_accuracy": 0.55,
    },
    TaskType.CITATION_CHECKING: {
        "reasoning": 0.15, "drafting": 0.05, "factual_accuracy": 0.80,
    },
    TaskType.GENERAL: {
        "reasoning": 0.34, "drafting": 0.33, "factual_accuracy": 0.33,
    },
}

# Task types where an LLM's own output is never sufficient evidence on its
# own -- the router flags that a separate verification step (citation
# lookup, cite-checking tool, human Shepardizing) is owed regardless of
# which model answered. This is a legal-domain judgment call, not a
# generic router concern.
REQUIRES_EXTERNAL_VERIFICATION = {TaskType.CITATION_CHECKING}

# Stakes -> (cost_weight, capability_floor, human_review_required)
# cost_weight: how strongly cost pulls the score down (0 = ignore cost).
# capability_floor: minimum *weighted capability score* (0-5 scale) a
#   model should clear before being recommended without a caveat.
# human_review_required: whether the router always attaches a
#   human-sign-off recommendation to the decision.
STAKES_POLICY: dict[Stakes, dict] = {
    Stakes.LOW: {"cost_weight": 1.0, "capability_floor": 2.0, "human_review_required": False},
    Stakes.MEDIUM: {"cost_weight": 0.4, "capability_floor": 3.0, "human_review_required": False},
    Stakes.HIGH: {"cost_weight": 0.0, "capability_floor": 4.0, "human_review_required": True},
}


@dataclass(frozen=True)
class TaskTypeSpec:
    task_type: TaskType
    keywords: tuple[str, ...]


# Keyword signal lists for the heuristic classifier (see classifier.py).
# Order doesn't matter; classifier scores every task type independently.
TASK_TYPE_KEYWORDS: dict[TaskType, tuple[str, ...]] = {
    TaskType.LITIGATION_REASONING: (
        "motion", "brief", "argument", "opposing counsel", "discovery dispute",
        "summary judgment", "deposition", "trial strategy", "cross-examination",
        "hearing", "complaint", "answer to complaint", "appeal",
        "standard of review", "burden of proof", "cause of action",
        # "litigation" itself was removed (a second blind eval, see README,
        # caught it firing on "the litigation team" -- an admin/general
        # request, not a legal task) -- it's redundant with the more
        # specific terms above anyway.
    ),
    TaskType.TRANSACTIONAL_DRAFTING: (
        "draft a", "draft an", "term sheet", "employment agreement", "nda",
        "license agreement", "merger agreement", "asset purchase", "bylaws",
        "operating agreement", "lease agreement", "purchase agreement",
        "redline", "clause", "indemnification", "boilerplate", "closing docs",
    ),
    TaskType.CONTRACT_REVIEW: (
        "review this contract", "review the agreement", "flag risky clauses",
        "contract review", "redlines on", "due diligence", "review for risk",
        "compare against our playbook", "non-standard terms", "liability cap",
        "termination clause", "review and summarize this agreement",
        # Broadened after a held-out eval (see README) showed this category had
        # almost no vocabulary distinct from transactional_drafting's document
        # nouns (both mention "NDA", "lease agreement", etc.) -- these add the
        # *reviewing-something-that-already-exists* verbs/phrases that actually
        # distinguish "review this" from "draft this" in casual real phrasing.
        "look over", "go through", "before they sign", "before we sign",
        "the other side sent", "risk summary", "playbook", "diligence",
        "flag", "termination rights", "anything risky", "anything scary",
    ),
    TaskType.LEGAL_RESEARCH: (
        "research", "case law", "precedent", "what is the rule", "jurisdiction",
        "statute", "regulation", "is it legal to", "memo on", "survey the law",
        "how have courts treated", "circuit split", "legal question",
        "enforceable", "enforceability",
    ),
    TaskType.CITATION_CHECKING: (
        "check this citation", "verify the cite", "citation check", "shepardize",
        "confirm this case exists", "is this citation accurate", "cite-check",
        "verify quotations", "confirm pincite", "check bluebook format",
        "citation", "verify this citation", "confirm this citation", "pincite",
        "bluebook", "cite check",
        # "cite"/"quote" alone (word-boundary matched, so safe from false
        # substring hits) -- casual phrasing rarely spells out "citation".
        "cite", "quote",
    ),
}
