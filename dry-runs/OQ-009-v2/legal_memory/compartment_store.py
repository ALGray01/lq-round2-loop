"""Third system under test: a layered-compartment store, standing in for the
Honcho/Cognee style of memory the question named as an alternative.

The defining property of that family is a per-user/per-session compartment
that keeps a rolling "current understanding" -- isolation between
compartments is native (this is exactly what those systems are built
for), but there is no bi-temporal edge model: once a belief is updated,
the prior belief is gone, not superseded-with-a-timestamp. So this store
reuses GraphMemoryStore's matter partition (isolation is not the axis this
system is meant to test) but structurally has no `as_of_transaction_session`
parameter at all -- there is no code path that could honor "what did we
believe as of session N," because a layered-compartment design keeps only
the current layer, not a history of past layers.

This is not a strawman: it correctly gets every "what's true now" question
right (it does what it's built for), and correctly keeps matters apart. It
specifically cannot answer "what did we believe before we learned better,"
which is the whole reason this project's Recommendation reaches for a
bi-temporal graph instead.
"""
from __future__ import annotations

from legal_memory.scenario import Fact
from legal_memory.textsim import Corpus


class CompartmentMemoryStore:
    def __init__(self, facts: list[Fact]):
        self.facts = facts
        self._corpus = Corpus([f.text for f in facts])

    def query(self, matter_id: str, query_text: str, *, top_k: int = 3) -> list[Fact]:
        """Deliberately has no as_of_transaction_session / as_of_valid_time
        parameters: the current layer is all this architecture keeps."""
        if not matter_id:
            raise ValueError("query() requires a non-empty matter_id")
        candidates = [i for i, f in enumerate(self.facts)
                      if f.matter_id == matter_id and f.invalidated_at is None]
        ranked = self._corpus.rank(query_text, candidates)
        return [self.facts[i] for i, score in ranked[:top_k] if score > 0]
