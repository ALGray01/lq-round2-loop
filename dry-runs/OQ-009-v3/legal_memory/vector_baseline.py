"""Stand-in for naive flat RAG: TF-IDF/cosine over raw session transcripts.

This indexes `scenario.build_sessions()` directly -- raw transcript text,
one chunk per session -- not hand-authored facts. Isolation between matters
is a query-time metadata filter (`matter_id` tag on each session), which is
the realistic implementation for a flat store: there is no schema-level
guarantee that every chunk got tagged, and no guarantee a caller always
remembers to pass the filter. Both failure modes are exercised directly by
the eval (T6: an untagged session drifts out of scope regardless of which
matter should have owned it; T7: omitting the filter entirely leaks across
matters).

There is no temporal axis at all: `query()` ranks by text similarity only.
`query_recency_biased()` adds one obvious naive fix (prefer later sessions)
to check whether recency alone can substitute for genuine point-in-time
reasoning -- it can't, because "most recent" and "true as of a specific
earlier week" are different questions. `query_date_heuristic()` adds a
second, different naive fix (extract an explicit "as of week N" phrase
from the query and pre-filter the candidate pool by it) -- found by a
third-round audit subagent to actually flip T4 to a pass, but only when
the query names the same week-numbering scheme the corpus happens to use
internally; see README's "Does the obvious naive fix save the baseline?"
section for the honest result either way.
"""
from __future__ import annotations

import re

from .scenario import Session
from .textsim import build_idf, cosine, tfidf_vector

_WEEK_RE = re.compile(r"as of week (\d+)", re.IGNORECASE)


class VectorBaseline:
    def __init__(self, sessions: list[Session]) -> None:
        self._sessions = list(sessions)

    def _candidates(self, matter_id: str | None) -> list[Session]:
        if matter_id is None:
            return list(self._sessions)  # no filter applied -- the T7 bug case
        return [s for s in self._sessions if s.matter_id == matter_id]

    def query(self, query_text: str, matter_id: str | None, top_k: int = 3) -> list[tuple[str, float]]:
        if top_k < 0:
            raise ValueError("top_k must be non-negative")
        candidates = self._candidates(matter_id)
        if not candidates:
            return []
        corpus = [s.transcript for s in candidates] + [query_text]
        idf = build_idf(corpus)
        query_vec = tfidf_vector(query_text, idf)
        scored = [
            (s.session_id, cosine(query_vec, tfidf_vector(s.transcript, idf)))
            for s in candidates
        ]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored[:top_k]

    def query_recency_biased(self, query_text: str, matter_id: str | None, top_k: int = 3,
                              recency_weight: float = 0.15) -> list[tuple[str, float]]:
        """The obvious naive fix for "no temporal reasoning": bias toward
        later sessions. Included so the eval tests the fix, not just the
        unfixed baseline -- a fair comparison has to try the easy patch.
        """
        if top_k < 0:
            raise ValueError("top_k must be non-negative")
        candidates = self._candidates(matter_id)
        if not candidates:
            return []
        max_week = max(s.week for s in candidates) or 1
        corpus = [s.transcript for s in candidates] + [query_text]
        idf = build_idf(corpus)
        query_vec = tfidf_vector(query_text, idf)
        scored = []
        for s in candidates:
            sim = cosine(query_vec, tfidf_vector(s.transcript, idf))
            recency = s.week / max_week
            scored.append((s.session_id, sim + recency_weight * recency))
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored[:top_k]

    def query_date_heuristic(self, query_text: str, matter_id: str | None,
                              top_k: int = 3) -> list[tuple[str, float]]:
        """A second, different naive fix: regex out an explicit "as of week
        N" phrase and restrict the candidate pool to sessions at or before
        week N before ranking -- distinct from `query_recency_biased()`,
        which only ever biases toward *later* sessions. Naive on purpose:
        no embeddings, no LLM, just a regex over the query string plus the
        session's own `week` field (which a flat store could plausibly
        carry as ordinary metadata, same as `matter_id`). If no such phrase
        is found, or the phrase would empty the candidate pool entirely,
        falls back to the unrestricted pool rather than returning nothing.
        """
        if top_k < 0:
            raise ValueError("top_k must be non-negative")
        candidates = self._candidates(matter_id)
        if not candidates:
            return []
        match = _WEEK_RE.search(query_text)
        if match:
            as_of_week = int(match.group(1))
            restricted = [s for s in candidates if s.week <= as_of_week]
            if restricted:
                candidates = restricted
        corpus = [s.transcript for s in candidates] + [query_text]
        idf = build_idf(corpus)
        query_vec = tfidf_vector(query_text, idf)
        scored = [
            (s.session_id, cosine(query_vec, tfidf_vector(s.transcript, idf)))
            for s in candidates
        ]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored[:top_k]

    def get_text(self, session_id: str) -> str:
        for s in self._sessions:
            if s.session_id == session_id:
                return s.transcript
        raise KeyError(session_id)
