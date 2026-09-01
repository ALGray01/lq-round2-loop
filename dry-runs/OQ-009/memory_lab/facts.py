"""Bi-temporal fact store: the structured layer of the hybrid memory design.

Each Fact is a (subject, predicate, object) triple scoped to a matter
(compartment), with a valid-time window (when it was true in the world,
per legal reality) separate from when it was recorded. Superseding a fact
closes the old one's valid_until and adds a new fact linked to it via
`supersedes` -- both remain queryable (bitemporal audit trail), but
`current_as_of` returns only what was live at a given moment.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Fact:
    fact_id: str
    matter_id: str
    subject: str
    predicate: str
    object: str
    source: str  # provenance: what document/conversation this came from
    valid_from: str  # ISO date string
    valid_until: Optional[str] = None  # None == still current
    supersedes: Optional[str] = None  # fact_id of the fact this replaces

    def text(self) -> str:
        return f"{self.subject} {self.predicate} {self.object}"


class FactStore:
    """A per-process temporal knowledge graph, partitioned by matter_id.

    Compartmentalization is enforced at the API level: every read requires
    a matter_id, and there is no method that returns facts across matters.
    That is the deliberate design choice (see README) -- privilege/conflict
    boundaries must be structural, not a filter someone can forget to apply.
    """

    def __init__(self):
        self._facts: dict[str, Fact] = {}
        self._by_matter: dict[str, list[str]] = {}

    def add(self, fact: Fact) -> None:
        if fact.fact_id in self._facts:
            raise ValueError(f"duplicate fact_id {fact.fact_id}")
        self._facts[fact.fact_id] = fact
        self._by_matter.setdefault(fact.matter_id, []).append(fact.fact_id)

    def supersede(self, old_fact_id: str, new_fact: Fact, at_date: str) -> None:
        old = self._facts[old_fact_id]
        if old.matter_id != new_fact.matter_id:
            raise ValueError("supersession must stay inside the same matter compartment")
        old.valid_until = at_date
        new_fact.supersedes = old_fact_id
        self.add(new_fact)

    def current_as_of(self, matter_id: str, as_of: str) -> list[Fact]:
        """Facts live in `matter_id` at `as_of`. Never crosses compartments."""
        out = []
        for fid in self._by_matter.get(matter_id, []):
            f = self._facts[fid]
            if f.valid_from <= as_of and (f.valid_until is None or as_of < f.valid_until):
                out.append(f)
        return out

    def history(self, matter_id: str, subject: str) -> list[Fact]:
        """Full version history for a subject within one matter, oldest first."""
        chain = [
            self._facts[fid]
            for fid in self._by_matter.get(matter_id, [])
            if self._facts[fid].subject == subject
        ]
        return sorted(chain, key=lambda f: f.valid_from)

    def all_matters(self) -> list[str]:
        return list(self._by_matter.keys())
