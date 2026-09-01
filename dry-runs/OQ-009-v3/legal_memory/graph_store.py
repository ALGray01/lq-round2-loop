"""Proposed design: a bi-temporal, matter-partitioned fact store.

Two structural properties, both load-bearing for the argument in README.md:

1. **Bi-temporal.** Every fact carries `valid_from_week` (when it became
   true in the world) and `learned_week` (transaction time: when the agent
   learned it, i.e. which session produced it). `query(as_of=W)` answers
   "what did we believe as of week W" by filtering on `learned_week <= W`,
   then within the surviving set, superseded facts are excluded if their
   successor was *also* learned by week W (see `_current_as_of`). This is
   the property a layered-compartment design (`compartment_store.py`) does
   not have: it only ever exposes the current layer.
2. **Matter-partitioned by construction.** `Fact.__post_init__` (see
   `scenario.py`) rejects a falsy `matter_id` at construction time, and
   `query()` below rejects a falsy `matter_id` argument too -- there is no
   code path that returns results without a matter to scope them to. A flat
   vector store's isolation, by contrast, is typically a metadata filter
   applied at query time, which fails silently if a chunk was never tagged
   or a caller forgets to pass the filter (see `vector_baseline.py` and
   eval tests T6/T7).

`enforce_time` and `enforce_matter` are test-only escape hatches (default
True) used exclusively by the eval harness's scorer sanity check (see
`eval_harness.py`) to prove the scorer actually catches it when either
structural guarantee is disabled -- not a supported production mode. Even
with `enforce_matter=False`, `Fact` construction and the `query()` argument
check still require a real `matter_id`; the flag only disables the internal
*filter*, so the sanity check exercises exactly one axis at a time.
"""
from __future__ import annotations

from .scenario import Fact, require_matter_id, validate_no_supersession_cycles
from .textsim import rank


class GraphMemoryStore:
    def __init__(self, facts: list[Fact], enforce_time: bool = True, enforce_matter: bool = True) -> None:
        validate_no_supersession_cycles(facts)
        self._facts = list(facts)
        self._by_id = {f.fact_id: f for f in self._facts}
        self.enforce_time = enforce_time
        self.enforce_matter = enforce_matter

    def _current_as_of(self, matter_facts: list[Fact], as_of: int | None) -> list[Fact]:
        """Facts known and not-yet-superseded as of a given transaction week.

        `as_of=None` means "now" (no upper bound on learned_week and every
        supersession that has happened is applied).
        """
        if self.enforce_time and as_of is not None:
            known = [f for f in matter_facts if f.learned_week <= as_of]
        else:
            known = list(matter_facts)

        # A fact's predecessor is excluded once the successor itself is
        # known (already guaranteed by the `known` filter above) -- this is
        # what makes `as_of` answer "what we believed then" rather than
        # "everything we ever learned, unfiltered."
        superseded_ids = {f.supersedes for f in known if f.supersedes}
        return [f for f in known if f.fact_id not in superseded_ids]

    def query(self, matter_id: str, query_text: str, as_of: int | None = None, top_k: int = 3) -> list[tuple[str, float]]:
        # Always required, regardless of enforce_matter: that flag only
        # disables the internal filter below, for the scorer sanity check
        # (FAILURE-CLASSES #4) -- it is not a way to bypass the argument
        # requirement itself. An earlier version of this check was gated on
        # `self.enforce_matter`, silently skipping the requirement whenever
        # the sanity-check flag was set; fixed so the two are independent.
        require_matter_id(matter_id, context="query()")

        if self.enforce_matter:
            matter_facts = [f for f in self._facts if f.matter_id == matter_id]
        else:
            matter_facts = list(self._facts)

        candidates = self._current_as_of(matter_facts, as_of)
        return rank(query_text, [(f.fact_id, f.text) for f in candidates], top_k=top_k)

    def get_text(self, fact_id: str) -> str:
        return self._by_id[fact_id].text
