"""Heuristic task-type classifier.

This is a deliberately simple, deterministic, keyword-overlap classifier --
not an LLM call. See README "Limitations" for why: it keeps the router
runnable offline with no API keys and fully unit-testable, at the cost of
missing task descriptions that don't share vocabulary with the keyword
lists. `Classifier` is a small protocol so a real implementation (e.g. a
cheap-model classification call) can be swapped in without touching the
policy or routing code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from .taxonomy import TASK_TYPE_KEYWORDS, TaskType


@dataclass(frozen=True)
class Classification:
    task_type: TaskType
    confidence: float  # 0.0-1.0, fraction of matched keyword weight
    matched_keywords: tuple[str, ...]


class Classifier(Protocol):
    def classify(self, text: str) -> Classification: ...


class KeywordClassifier:
    """Scores each task type by how many of its keyword phrases appear in
    the text as whole-word/whole-phrase matches (case-insensitive, word-
    boundary regex -- NOT naive substring matching), and returns the best
    match. Falls back to TaskType.GENERAL when nothing matches.

    Word-boundary matching matters: a naive `"nda" in text` substring check
    matches "nda" inside "defe-NDA-nt", silently misclassifying any text
    about a defendant as an NDA-drafting request. A held-out eval (see
    README) caught this in practice; \\b...\\b regex matching fixes the
    whole class of short-keyword-inside-a-longer-word bug, not just this
    one instance.
    """

    def __init__(self, keyword_map: dict[TaskType, tuple[str, ...]] | None = None):
        self.keyword_map = keyword_map or TASK_TYPE_KEYWORDS
        # Trailing `s?` tolerates simple plurals ("citations", "lease
        # agreements") without needing every keyword duplicated -- it only
        # extends the end of the phrase, so the leading \b that fixes the
        # substring-collision bug is unaffected.
        self._patterns: dict[TaskType, tuple[tuple[str, re.Pattern], ...]] = {
            task_type: tuple((kw, re.compile(r"\b" + re.escape(kw) + r"s?\b", re.IGNORECASE))
                              for kw in keywords)
            for task_type, keywords in self.keyword_map.items()
        }

    def classify(self, text: str) -> Classification:
        best_type = TaskType.GENERAL
        best_matches: tuple[str, ...] = ()
        best_fraction = 0.0

        # Ranking key is (match count, fraction-of-list-matched), in that
        # order. Fraction alone would let a category with a shorter keyword
        # list win on a single weak match against a category with a longer
        # (better-covered) list and the same single match -- e.g. one
        # generic "brief" hit (1/17) used to beat citation_checking's own
        # "cite" hit (1/18) purely because that list happens to be longer.
        # Match count is the more honest primary signal: it doesn't get
        # worse just because a category's vocabulary was later broadened.
        best_count = 0
        for task_type, keyword_patterns in self._patterns.items():
            matched = tuple(kw for kw, pattern in keyword_patterns if pattern.search(text))
            if not matched:
                continue
            fraction = len(matched) / len(keyword_patterns)
            if (len(matched), fraction) > (best_count, best_fraction):
                best_count = len(matched)
                best_fraction = fraction
                best_type = task_type
                best_matches = matched

        if best_type == TaskType.GENERAL:
            return Classification(TaskType.GENERAL, 0.0, ())

        # Confidence still reports the fraction-of-list-matched (a
        # reasonable "how much of this category's signal showed up" UX
        # metric), blended down for a lone single-keyword match so it
        # doesn't look artificially confident.
        confidence = min(1.0, best_fraction * (1.0 if len(best_matches) > 1 else 0.6))
        return Classification(best_type, round(confidence, 3), best_matches)
