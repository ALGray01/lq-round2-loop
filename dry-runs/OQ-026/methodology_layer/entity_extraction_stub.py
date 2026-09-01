"""
A stand-in for what an entity-extraction tool (the brief names Isaacus/Kanon
specifically) already gives an LLM today: spans of text tagged with surface
entity types. No court hierarchy, no admissibility rule, no notion that two
authorities might conflict. This module is deliberately dumb -- it exists
only so demo.py can show it next to an InterpretiveAnnotation and make the
gap concrete instead of asserted.

This is a hand-written simulation of that class of tool's *output shape*,
not a call to the real Isaacus/Kanon API (no network access in this
environment, and no credentials were provided) -- see README.md's
Limitations section.
"""

from __future__ import annotations

import re


ENTITY_PATTERNS = [
    ("DEFINED_TERM", re.compile(r"\b(?:the )?(?:Buyer|Seller|Vendor|Purchaser|Licensor|Licensee)\b", re.I)),
    ("DATE", re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")),
    ("MONEY", re.compile(r"\$[\d,]+(?:\.\d+)?")),
    ("DURATION", re.compile(r"\b\d+\s+(?:day|month|year)s?\b", re.I)),
]


def extract_entities(clause_text: str) -> list[dict]:
    """Return raw entity spans, in the shape a Kanon/Isaacus-style NER pass
    would: type + text + offsets, nothing about what body of doctrine
    governs how the clause should be read."""
    entities = []
    for label, pattern in ENTITY_PATTERNS:
        for m in pattern.finditer(clause_text):
            entities.append({"type": label, "text": m.group(0), "start": m.start(), "end": m.end()})
    entities.sort(key=lambda e: e["start"])
    return entities
