"""Scoring logic, kept separate from run_headtohead.py so it has its own
unit tests (see tests/test_scorer.py) -- including a deliberately-wrong
answer that must score as incorrect (FAILURE-CLASSES.md item 4: a scorer
that has never been shown a true negative can silently overstate results).
"""
from dataclasses import dataclass

from memory_lab.architectures import AnswerResult
from scenario.queries import Query


@dataclass
class ScoreResult:
    query_id: str
    correct: bool
    leaked: bool
    reason: str


def score(query: Query, result: AnswerResult) -> ScoreResult:
    leaked = query.forbidden_matter is not None and query.forbidden_matter in result.matter_ids_touched

    if leaked:
        return ScoreResult(query.id, correct=False, leaked=True,
                            reason=f"touched forbidden matter {query.forbidden_matter}")

    if query.expected_fact_id is not None:
        ok = result.fact_id == query.expected_fact_id
        reason = "matched expected fact" if ok else f"expected {query.expected_fact_id}, got {result.fact_id}"
        return ScoreResult(query.id, correct=ok, leaked=False, reason=reason)

    # expected_fact_id is None: either a true-negative (nothing should be
    # found) or an episodic-recall query (a keyword should show up in the
    # snippet, but no fact_id).
    if result.fact_id is not None:
        return ScoreResult(query.id, correct=False, leaked=False,
                            reason=f"expected no fact, got {result.fact_id}")

    if query.expected_keyword is not None:
        ok = query.expected_keyword.lower() in result.snippet.lower()
        reason = "recalled expected episodic content" if ok else f"snippet missing '{query.expected_keyword}': {result.snippet!r}"
        return ScoreResult(query.id, correct=ok, leaked=False, reason=reason)

    # No expected_keyword: this is a true-negative query (nothing at all
    # should be surfaced), not just "no fact_id". A system can have
    # fact_id=None and still have wrongly recalled an *irrelevant* episodic
    # turn as if it were responsive (found by testing this directly -- see
    # README "Generalization check, round 2"); requiring an empty snippet
    # catches that instead of treating "no fact_id" as automatically correct.
    ok = result.snippet == ""
    reason = "correctly found nothing" if ok else f"expected nothing, but recalled irrelevant snippet: {result.snippet!r}"
    return ScoreResult(query.id, correct=ok, leaked=False, reason=reason)
