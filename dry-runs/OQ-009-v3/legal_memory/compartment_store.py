"""Stand-in for Honcho/Cognee-style layered-compartment memory.

The defining property of this family, per their own design descriptions, is
that memory is organized into compartments/layers optimized for modeling a
*user* over time (working vs. long-term, current understanding) -- not a
bi-temporal record of superseded facts. This class models exactly that
defining property: it is matter-partitioned (same non-nullable `matter_id`
requirement as `GraphMemoryStore`, since isolation is not the axis this
family is being tested on), but its `query()` has **no `as_of` parameter at
all** -- there is no prior layer to query against once the current layer is
updated. A superseded fact is simply gone once a newer one replaces it.

This is a fair stand-in for the architectural pattern, not a benchmark of
the actual Honcho or Cognee libraries -- neither was installed or run here.
See README Limitations for exactly what that gap means.
"""
from __future__ import annotations

from .scenario import Fact, require_matter_id, validate_no_supersession_cycles
from .textsim import rank


class CompartmentMemoryStore:
    def __init__(self, facts: list[Fact]) -> None:
        validate_no_supersession_cycles(facts)
        self._facts = list(facts)

    def _current_layer(self, matter_id: str) -> list[Fact]:
        matter_facts = [f for f in self._facts if f.matter_id == matter_id]
        superseded_ids = {f.supersedes for f in matter_facts if f.supersedes}
        return [f for f in matter_facts if f.fact_id not in superseded_ids]

    def query(self, matter_id: str, query_text: str, top_k: int = 3) -> list[tuple[str, float]]:
        # Deliberately no `as_of` parameter -- this store has no notion of
        # "what we believed at some earlier point," only "what's current."
        require_matter_id(matter_id, context="query()")
        current = self._current_layer(matter_id)
        return rank(query_text, [(f.fact_id, f.text) for f in current], top_k=top_k)

    def get_text(self, fact_id: str) -> str:
        for f in self._facts:
            if f.fact_id == fact_id:
                return f.text
        raise KeyError(fact_id)
