"""Proposed architecture: a bi-temporal, matter-partitioned fact store.

Two independent time axes per fact (Graphiti's core idea, applied to a legal
context):
  - valid_from / valid_until : when the fact was/is true in the real world
    (a statute's effective dates, a precedent's good-law window).
  - recorded_at / invalidated_at : when the agent's *belief* about that fact
    was learned / superseded (transaction time) -- lets the agent answer
    "what did we know as of session N" even after later sessions correct it.

matter_id is a required, non-nullable field on every Fact (see
scenario.Fact.__post_init__). That is the whole isolation argument: a fact
that cannot be filed without a matter cannot leak across the ethical wall
by omission the way an untagged row in a flat store can.

Ranking uses the exact same TF-IDF cosine similarity as the flat baseline
(legal_memory.textsim) -- the only difference under test is which candidate
facts are even eligible to be ranked, not a smarter ranker.
"""
from __future__ import annotations

from legal_memory.scenario import Fact
from legal_memory.textsim import Corpus


class GraphMemoryStore:
    def __init__(self, facts: list[Fact], *, enforce_time: bool = True, enforce_matter: bool = True):
        """enforce_time and enforce_matter both default True; the eval
        harness flips each off independently on a copy of the store to
        sanity-check that the scorer can actually detect a broken proposed
        system on *both* structural axes, not just rubber-stamp it
        (FAILURE-CLASSES #4). In production Fact() also requires matter_id
        at construction (scenario.py), so enforce_matter=False here is
        strictly a test-only escape hatch to prove the scorer notices if the
        partition filter were ever removed -- query_ignoring_matter_wall()
        below is the equivalent demonstration at the query-method level."""
        self.facts = facts
        self.enforce_time = enforce_time
        self.enforce_matter = enforce_matter
        self._corpus = Corpus([f.text for f in facts])

    def _eligible(self, matter_id: str, as_of_transaction_session: int | None,
                  as_of_valid_time: int | None) -> list[int]:
        indices = []
        for i, f in enumerate(self.facts):
            if self.enforce_matter and f.matter_id != matter_id:
                continue
            if self.enforce_time:
                as_of_txn = as_of_transaction_session
                if as_of_txn is not None:
                    if f.recorded_at > as_of_txn:
                        continue
                    if f.invalidated_at is not None and f.invalidated_at <= as_of_txn:
                        continue
                else:
                    # "now": most current belief only
                    if f.invalidated_at is not None:
                        continue
                if as_of_valid_time is not None:
                    if f.valid_from is not None and f.valid_from > as_of_valid_time:
                        continue
                    if f.valid_until is not None and f.valid_until <= as_of_valid_time:
                        continue
            else:
                # broken variant: ignore all temporal bounds, everything is eligible
                pass
            indices.append(i)
        return indices

    def query(self, matter_id: str, query_text: str, *,
              as_of_transaction_session: int | None = None,
              as_of_valid_time: int | None = None,
              top_k: int = 3) -> list[Fact]:
        if not matter_id:
            # Argument is positionally required (TypeError if omitted), but a
            # caller could still pass a falsy value (None, ""); reject that
            # too so "cannot query without a matter" is enforced on the value,
            # not just on the argument's presence.
            raise ValueError("query() requires a non-empty matter_id")
        candidates = self._eligible(matter_id, as_of_transaction_session, as_of_valid_time)
        ranked = self._corpus.rank(query_text, candidates)
        return [self.facts[i] for i, score in ranked[:top_k] if score > 0]

    def query_ignoring_matter_wall(self, query_text: str, *, top_k: int = 3) -> list[Fact]:
        """Only exists to demonstrate what the baseline is exposed to by default:
        a search with no matter partition at all. The proposed design has no
        code path that reaches this without a caller explicitly bypassing
        matter_id -- there is no equivalent "forget to filter" bug possible,
        because query() requires a matter_id argument to run at all."""
        candidates = list(range(len(self.facts)))
        ranked = self._corpus.rank(query_text, candidates)
        return [self.facts[i] for i, score in ranked[:top_k] if score > 0]
