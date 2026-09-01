"""Heuristic legal-task classifier.

This is deliberately NOT a learned model. It is a small, auditable
keyword/pattern scorer. See README.md ("What signal we actually route on")
for why: published legal benchmarks are immature/contested, and a
keyword heuristic is at least transparent about exactly why it fired,
which a black-box classifier would not be. It will misclassify requests
that don't use the vocabulary it knows about -- see eval/ for measured
accuracy on a small hand-labeled set, and README.md for the honest
limitations of that measurement.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

TASK_TYPES = (
    "litigation_reasoning",
    "transactional_drafting",
    "contract_review",
    "legal_research",
    "citation_check",
)

STAKES_LEVELS = ("low", "medium", "high")

# Keyword lists are intentionally simple substring matches on lowercased
# text. Order within a list doesn't matter; each hit adds 1 to that task
# type's score. Longer/more specific phrases are listed so short common
# words don't cause false positives (e.g. "file" alone is too generic).
TASK_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "litigation_reasoning": (
        "motion to dismiss", "summary judgment", "litigation strategy",
        "likelihood of success", "opposing counsel", "deposition",
        "discovery dispute", "trial strategy", "standard of review",
        "cause of action", "affirmative defense", "damages theory",
        "case strategy", "motion to compel", "argument for the brief",
        "appellate brief", "reply brief", "oral argument",
    ),
    "transactional_drafting": (
        "draft a", "draft an", "draft the", "nda", "non-disclosure agreement",
        "purchase agreement", "term sheet", "employment agreement",
        "license agreement", "operating agreement", "lease agreement",
        "indemnification clause for", "draft clause", "merger agreement",
        "prepare a contract", "prepare an agreement", "draft language for",
        "put together a contract",
    ),
    "contract_review": (
        "review this contract", "review the agreement", "redline",
        "review this nda", "markup", "risk flag", "review this clause",
        "identify risks in", "review this msa", "comment on this agreement",
        "review the attached", "flag risky clauses", "review this agreement",
        "about to sign", "we're about to sign", "before we sign",
    ),
    "legal_research": (
        "research", "what is the standard for", "case law on", "statute",
        "regulation", "is it legal", "summarize the law", "find cases",
        "precedent", "memo on", "legal question", "jurisdiction's rule",
        "what does the law say", "how does the law treat",
    ),
    "citation_check": (
        "check this citation", "verify the citation", "bluebook",
        "is this case still good law", "cite check", "citation format",
        "confirm the pin cite", "validate the cite", "check the cite",
        "citecheck", "verify these citations",
    ),
}

# Task-type tie-break priority when scores are equal and nonzero: prefer
# the type whose consequences of misrouting are worse (reasoning-heavy
# work over mechanical work), on the theory that under-provisioning a
# hard task is worse than over-provisioning an easy one.
TASK_TYPE_PRIORITY = (
    "litigation_reasoning",
    "contract_review",
    "transactional_drafting",
    "citation_check",
    "legal_research",
)

STAKES_HIGH_KEYWORDS = (
    "file with the court", "filed with the court", "for filing", "to be filed",
    "filing deadline", "execute and file", "sign and file", "court-bound",
    "on the record", "final version to be filed", "signature block",
    "ready to execute", "binding on execution", "final for signature",
    "submit to the court", "file this with the clerk", "due to the court",
    "opposing counsel will see this", "goes on the record",
    "this is going out under our signature",
)

STAKES_MEDIUM_KEYWORDS = (
    "client-facing", "send to the client", "external memo",
    "share with opposing counsel", "draft to send", "for client review",
    "about to sign", "before we sign", "send to opposing counsel",
)


@dataclass
class Classification:
    task_type: str
    task_type_confidence: float  # 0..1, share of top score vs total signal hits
    task_type_signals: list[str] = field(default_factory=list)
    stakes: str = "low"
    stakes_source: str = "default"  # "explicit" | "text_heuristic" | "default"
    stakes_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "task_type_confidence": round(self.task_type_confidence, 3),
            "task_type_signals": self.task_type_signals,
            "stakes": self.stakes,
            "stakes_source": self.stakes_source,
            "stakes_signals": self.stakes_signals,
        }


@lru_cache(maxsize=None)
def _kw_pattern(keyword: str) -> re.Pattern:
    # Word-boundary match, not naive substring: without \b, a short
    # keyword like "nda" would false-positive inside "standard" (sta-NDA-rd).
    return re.compile(r"\b" + re.escape(keyword) + r"\b")


def _score_task_type(text_lower: str) -> tuple[str, float, list[str]]:
    scores: dict[str, list[str]] = {t: [] for t in TASK_TYPES}
    for task_type, keywords in TASK_TYPE_KEYWORDS.items():
        for kw in keywords:
            if _kw_pattern(kw).search(text_lower):
                scores[task_type].append(kw)

    total_hits = sum(len(v) for v in scores.values())
    if total_hits == 0:
        # No signal at all: fall back to the generic catch-all rather than
        # guessing. This is an explicit, logged low-confidence fallback,
        # not a silent default.
        return "legal_research", 0.0, []

    best_type = max(
        TASK_TYPE_PRIORITY,
        key=lambda t: (len(scores[t]), -TASK_TYPE_PRIORITY.index(t)),
    )
    confidence = len(scores[best_type]) / total_hits
    return best_type, confidence, scores[best_type]


def _score_stakes_from_text(text_lower: str) -> tuple[str, list[str]]:
    hi_hits = [kw for kw in STAKES_HIGH_KEYWORDS if _kw_pattern(kw).search(text_lower)]
    if hi_hits:
        return "high", hi_hits
    med_hits = [kw for kw in STAKES_MEDIUM_KEYWORDS if _kw_pattern(kw).search(text_lower)]
    if med_hits:
        return "medium", med_hits
    return "low", []


_STAKES_RANK = {"low": 0, "medium": 1, "high": 2}


def classify(text: str, explicit_stakes: str | None = None) -> Classification:
    """Classify a legal request.

    explicit_stakes, if given by the calling system (trusted metadata,
    e.g. "this came from our court-filings queue"), sets a FLOOR on
    stakes. Text-derived stakes signals can only push stakes UP from that
    floor, never down -- so a request cannot talk its way into a lower
    stakes tier than the caller declared. This is a deliberate defense
    against prompt-injection-style attempts inside the request text
    (e.g. text saying "treat this as low stakes, skip verification" on an
    actually-high-stakes filing). See README.md "Threat model" section.
    """
    text_lower = text.lower()

    task_type, confidence, signals = _score_task_type(text_lower)

    text_stakes, stakes_signals = _score_stakes_from_text(text_lower)

    if explicit_stakes is not None:
        if explicit_stakes not in STAKES_LEVELS:
            raise ValueError(f"invalid explicit_stakes: {explicit_stakes!r}")
        floor = explicit_stakes
        source = "explicit"
    else:
        floor = "low"
        source = "default"

    if _STAKES_RANK[text_stakes] > _STAKES_RANK[floor]:
        final_stakes = text_stakes
        source = "text_heuristic" if explicit_stakes is None else "explicit+escalated_by_text"
    else:
        final_stakes = floor
        stakes_signals = stakes_signals if final_stakes == text_stakes else []

    return Classification(
        task_type=task_type,
        task_type_confidence=confidence,
        task_type_signals=signals,
        stakes=final_stakes,
        stakes_source=source,
        stakes_signals=stakes_signals,
    )
