"""Baseline architecture: flat vector-store RAG over raw session transcripts.

This is the common default for "just give the agent memory": chunk every
past session transcript, embed it, retrieve top-k by similarity at query
time. No entity graph, no notion of a fact being superseded, no built-in
temporal axis beyond whatever timestamp happens to be in the metadata.

Two variants are exposed because a fair comparison needs a steelman, not a
strawman:
  - query(): applies a matter_id metadata filter when present, which is what
    most real naive-RAG setups actually do.
  - query() also naturally exposes what happens when a chunk's metadata
    lacks a matter tag (session 3 in the scenario) -- filtering breaks not
    because the filter logic is wrong, but because the tag was never there
    to filter on. That is the realistic failure mode, not a rigged one.
  - recency-sorted variant: to steelman the "no temporal reasoning" gap, a
    recency bias is offered as the most obvious naive fix. It is shown to
    fail the point-in-time task for the opposite reason (leaks the future
    into a past-dated question) rather than left untried.
"""
from __future__ import annotations

from legal_memory.scenario import Session
from legal_memory.textsim import Corpus


class VectorBaseline:
    def __init__(self, sessions: list[Session]):
        self.sessions = sessions
        self._corpus = Corpus([s.text for s in sessions])

    def query(self, query_text: str, *, matter_filter: str | None = None,
              top_k: int = 3) -> list[Session]:
        if matter_filter is not None:
            candidates = [i for i, s in enumerate(self.sessions) if s.matter_id == matter_filter]
        else:
            candidates = list(range(len(self.sessions)))
        ranked = self._corpus.rank(query_text, candidates)
        return [self.sessions[i] for i, score in ranked[:top_k] if score > 0]

    def query_recency_biased(self, query_text: str, *, matter_filter: str | None = None,
                              as_of_session: int | None = None, top_k: int = 3) -> list[Session]:
        """Steelman attempt at temporal reasoning: sort by similarity, break
        ties toward the most recent session. as_of_session is accepted only
        to show it does NOT constrain retrieval -- a flat store has no
        transaction-time filter, so "as of session N" cannot exclude session
        N+1's content the way it can for the graph store."""
        if matter_filter is not None:
            candidates = [i for i, s in enumerate(self.sessions) if s.matter_id == matter_filter]
        else:
            candidates = list(range(len(self.sessions)))
        ranked = self._corpus.rank(query_text, candidates)
        ranked.sort(key=lambda pair: (round(pair[1], 6), self.sessions[pair[0]].session_id), reverse=True)
        return [self.sessions[i] for i, score in ranked[:top_k] if score > 0]
