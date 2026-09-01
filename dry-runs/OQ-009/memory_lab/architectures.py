"""Three memory architectures with a common `answer` interface, so the
head-to-head eval can drive them identically.

AnswerResult.fact_id is the single fact the system is relying on for a
factual query (None for pure-episodic recall queries). matter_ids_touched
records every matter compartment the system actually read from while
answering -- that's how the eval catches cross-matter leakage.
"""
from dataclasses import dataclass, field
from typing import Optional

from memory_lab.facts import FactStore
from memory_lab.episodic import EpisodicLog
from memory_lab.retrieval import TfidfIndex, confident_top


@dataclass
class AnswerResult:
    fact_id: Optional[str]
    snippet: str
    matter_ids_touched: list[str] = field(default_factory=list)


class HybridMemory:
    """Proposed design: compartments (outer boundary) + temporal fact graph
    (inside each compartment) + episodic TF-IDF recall (inside each
    compartment) as a fallback for non-factual queries.

    Structural compartmentalization: this class never builds an index that
    spans matter_ids. A query always names its matter_id and only that
    matter's facts/turns are ever touched.
    """

    def __init__(self, fact_store: FactStore, episodic_log: EpisodicLog):
        self.facts = fact_store
        self.episodic = episodic_log

    def answer(self, query: str, matter_id: str, as_of: str) -> AnswerResult:
        current = self.facts.current_as_of(matter_id, as_of)
        if current:
            index = TfidfIndex([(f.fact_id, f.text()) for f in current])
            top = confident_top(index.search(query, top_k=2))
            if top:
                best_id, _score = top
                best = next(f for f in current if f.fact_id == best_id)
                return AnswerResult(best.fact_id, best.text(), [matter_id])

        turns = self.episodic.for_matter(matter_id)
        turns = [t for t in turns if t.date <= as_of]
        if turns:
            index = TfidfIndex([(str(i), t.text) for i, t in enumerate(turns)])
            top = confident_top(index.search(query, top_k=2))
            if top:
                i = int(top[0])
                return AnswerResult(None, turns[i].text, [matter_id])

        return AnswerResult(None, "", [matter_id])


class FlatRagMemory:
    """Strawman-but-real baseline: everything (all matters, all facts, all
    superseded versions, all episodic turns) goes into one flat text index.
    No temporal filtering, no compartment boundary -- this is what you get
    if you bolt a single vector index onto the conversation log and call
    it "memory," which is a common first reach for this problem.
    """

    def __init__(self, fact_store: FactStore, episodic_log: EpisodicLog):
        self.facts = fact_store
        self.episodic = episodic_log

    def answer(self, query: str, matter_id: str, as_of: str) -> AnswerResult:
        docs = []
        touched = set()
        for m in self.facts.all_matters():
            for fid in self.facts._by_matter.get(m, []):
                f = self.facts._facts[fid]
                if f.valid_from <= as_of:  # no valid_until filtering: stale facts stay searchable
                    docs.append((f.fact_id, f.text()))
        for m in self.episodic.all_matters():
            for i, t in enumerate(self.episodic.for_matter(m)):
                if t.date <= as_of:
                    docs.append((f"turn:{m}:{i}", t.text))

        if not docs:
            return AnswerResult(None, "", [])

        index = TfidfIndex(docs)
        top = confident_top(index.search(query, top_k=2))
        if not top:
            return AnswerResult(None, "", [])
        best_id, _score = top

        if best_id.startswith("turn:"):
            _, m, _i = best_id.split(":", 2)
            touched.add(m)
            text = next(t for did, t in docs if did == best_id)
            return AnswerResult(None, text, list(touched))
        else:
            f = self.facts._facts[best_id]
            touched.add(f.matter_id)
            return AnswerResult(f.fact_id, f.text(), list(touched))


class FrozenSnapshotMemory:
    """Stand-in for a fine-tuning-cadence approach: facts are "baked in" as
    of a snapshot date (the last training run) and never updated again
    until the next (expensive, offline) fine-tune. Anything that changes
    after the snapshot is invisible until the next retrain. Compartments
    are also baked into one snapshot per matter here (best case for
    fine-tuning -- in practice a separate fine-tune per matter is normally
    cost-prohibitive, which is itself part of the argument against it).
    """

    def __init__(self, fact_store: FactStore, episodic_log: EpisodicLog, snapshot_date: str):
        self.snapshot_date = snapshot_date
        self._frozen: dict[str, list] = {}
        for m in fact_store.all_matters():
            self._frozen[m] = fact_store.current_as_of(m, snapshot_date)
        self.episodic = episodic_log

    def answer(self, query: str, matter_id: str, as_of: str) -> AnswerResult:
        current = self._frozen.get(matter_id, [])
        if current:
            index = TfidfIndex([(f.fact_id, f.text()) for f in current])
            top = confident_top(index.search(query, top_k=2))
            if top:
                best_id, _score = top
                best = next(f for f in current if f.fact_id == best_id)
                return AnswerResult(best.fact_id, best.text(), [matter_id])
        return AnswerResult(None, "", [matter_id])
