"""Supplementary experiment: can a generic, non-LLM heuristic do the
transcript -> Fact extraction step the Limitations section flags as the
biggest unbuilt gap?

This is NOT part of the core recommendation or the 7-case eval -- it is a
separate, honest attempt at the thing Reflection said was left undone
because no LLM was available in this environment. The extraction rule is
generic (sentence length + cosine similarity against the shared textsim
module already used everywhere else), not reverse-engineered from this
scenario's specific wording, and the similarity threshold below is fixed
*before* looking at what it produces and is not adjusted afterward --
doing otherwise would be exactly the "solved backward" pattern
FAILURE-CLASSES.md warns about. Whatever this produces, good or bad, is
reported as-is in README.md.

Rule, applied to sessions in chronological order, per matter:
  - A session with no matter_id cannot produce any Fact at all (Fact()
    requires one) -- this is itself a finding, not a bug to work around.
  - Each sentence becomes a candidate fact.
  - If a candidate's cosine similarity to the *current* (non-invalidated)
    facts already extracted for that matter exceeds SIMILARITY_THRESHOLD,
    it is treated as a supersession of the closest match: the old fact is
    invalidated and the new sentence becomes the current fact.
  - Otherwise it's a brand-new fact.

Run: python -m legal_memory.extractor
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from legal_memory.scenario import Fact, Session, build_sessions
from legal_memory.textsim import Corpus

# Chosen before running this module against the scenario, on the general
# reasoning that two short legal sentences about the same underlying fact
# typically share enough vocabulary to score above 0.3 cosine on TF-IDF,
# while two sentences about genuinely different facts typically don't.
# Not tuned afterward against what it produced.
SIMILARITY_THRESHOLD = 0.3
MIN_SENTENCE_WORDS = 4

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ExtractionEvent:
    session_id: int
    matter_id: str | None
    sentence: str
    outcome: str  # "rejected-no-matter" | "new-fact" | "supersedes:<fact_id>"


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def extract(sessions: list[Session]) -> tuple[list[Fact], list[ExtractionEvent]]:
    ordered = sorted(sessions, key=lambda s: s.session_id)

    all_sentences: list[str] = []
    sentence_owner: list[tuple[Session, str]] = []
    for s in ordered:
        for sent in _split_sentences(s.text):
            if len(sent.split()) < MIN_SENTENCE_WORDS:
                continue
            sentence_owner.append((s, sent))
            all_sentences.append(sent)

    extracted: list[Fact] = []
    events: list[ExtractionEvent] = []
    current_by_matter: dict[str, list[int]] = {}  # matter_id -> indices into `extracted` that are current
    next_id = 0

    for session, sentence in sentence_owner:
        if not session.matter_id:
            events.append(ExtractionEvent(session.session_id, session.matter_id, sentence, "rejected-no-matter"))
            continue

        current_indices = current_by_matter.get(session.matter_id, [])
        best_idx = None
        best_score = 0.0
        if current_indices:
            corpus = Corpus([extracted[i].text for i in current_indices] + [sentence])
            query_vec_idx = len(current_indices)  # the just-appended sentence is its own doc; rank others against it via corpus.rank isn't directly query-vs-doc, so score manually
            # textsim.Corpus.rank scores a *query string* against document indices;
            # here we want doc-vs-doc similarity, so call rank() with the sentence
            # itself as the query against the existing current facts only.
            ranked = corpus.rank(sentence, list(range(len(current_indices))))
            if ranked:
                best_local_idx, best_score = ranked[0]
                best_idx = current_indices[best_local_idx]

        if best_idx is not None and best_score > SIMILARITY_THRESHOLD:
            old_fact = extracted[best_idx]
            new_fact = Fact(
                fact_id=f"extracted-{next_id}", matter_id=session.matter_id, text=sentence,
                recorded_at=session.session_id, source_session=session.session_id,
                supersedes=old_fact.fact_id,
            )
            next_id += 1
            old_fact.invalidated_at = session.session_id
            extracted.append(new_fact)
            new_idx = len(extracted) - 1
            current_by_matter[session.matter_id] = [i for i in current_indices if i != best_idx] + [new_idx]
            events.append(ExtractionEvent(
                session.session_id, session.matter_id, sentence,
                f"supersedes:{old_fact.fact_id} (score={best_score:.3f}) "
                f"[from session {old_fact.source_session}: \"{old_fact.text}\"]"))
        else:
            new_fact = Fact(
                fact_id=f"extracted-{next_id}", matter_id=session.matter_id, text=sentence,
                recorded_at=session.session_id, source_session=session.session_id,
            )
            next_id += 1
            extracted.append(new_fact)
            new_idx = len(extracted) - 1
            current_by_matter.setdefault(session.matter_id, []).append(new_idx)
            if current_indices and best_idx is not None:
                closest = extracted[best_idx]
                score_note = (f"best_score={best_score:.3f}, closest existing was "
                              f"[session {closest.source_session}: \"{closest.text}\"]")
            else:
                score_note = "no existing facts yet"
            events.append(ExtractionEvent(session.session_id, session.matter_id, sentence, f"new-fact ({score_note})"))

    return extracted, events


def format_report(extracted: list[Fact], events: list[ExtractionEvent]) -> str:
    lines = ["=== Naive heuristic extraction: session transcripts -> candidate facts ===\n"]
    for e in events:
        lines.append(f"  session {e.session_id:>2} [{e.matter_id or 'UNTAGGED'}]: {e.outcome}")
        lines.append(f"      \"{e.sentence}\"")
    lines.append("")
    lines.append(f"Total candidate facts extracted: {len(extracted)}")
    superseded = sum(1 for f in extracted if f.invalidated_at is not None)
    lines.append(f"Supersession events detected: {superseded}")
    rejected = sum(1 for e in events if e.outcome == "rejected-no-matter")
    lines.append(f"Sentences rejected for missing matter_id: {rejected}")
    return "\n".join(lines)


if __name__ == "__main__":
    sessions = build_sessions()
    extracted, events = extract(sessions)
    print(format_report(extracted, events))
