"""Episodic layer: raw conversational turns, scoped by matter (compartment).

This is the "what did we discuss" memory -- distinct from the structured
fact graph's "what is currently true" memory. Modeled loosely on
Honcho/Cognee's session-layer idea: turns belong to a session, sessions
belong to a matter, and nothing here is ever read across matter boundaries.
"""
from dataclasses import dataclass


@dataclass
class Turn:
    matter_id: str
    session_id: str
    date: str  # ISO date string
    speaker: str
    text: str


class EpisodicLog:
    def __init__(self):
        self._turns: list[Turn] = []

    def append(self, turn: Turn) -> None:
        self._turns.append(turn)

    def for_matter(self, matter_id: str) -> list[Turn]:
        return [t for t in self._turns if t.matter_id == matter_id]

    def all_matters(self) -> list[str]:
        seen = []
        for t in self._turns:
            if t.matter_id not in seen:
                seen.append(t.matter_id)
        return seen
