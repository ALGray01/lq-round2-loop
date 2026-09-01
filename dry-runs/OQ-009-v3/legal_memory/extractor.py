"""Supplementary experiment: can a non-LLM heuristic do transcript-to-fact
extraction, the biggest gap this README names between this prototype and a
deployed system?

Everywhere else in this repo, facts are hand-authored alongside the
sessions that "produced" them (see `scenario.build_facts()`). A real system
needs an extraction step from raw transcript to structured fact -- normally
LLM-driven, and `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` are both confirmed
absent from this environment (see `real_library_check.py`), so an LLM
version can't be built here. This is the closest buildable substitute: a
generic, non-LLM heuristic (sentence-splitting + the same TF-IDF cosine
`rank()` used everywhere else in this repo) that reads raw session
transcripts and proposes candidate facts and supersessions on its own -- no
fact IDs, no supersession links, and no scenario-specific knowledge fed in.

`SIMILARITY_THRESHOLD` is fixed below, before running this, based on
general reasoning about short-text TF-IDF cosine scores. It is not
adjusted after seeing the output -- doing so would be exactly the "solved
backward" pattern FAILURE-CLASSES.md warns about. Whatever comes out is
reported as-is in README.md, not tuned to look better.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .scenario import Session, build_sessions
from .textsim import rank

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
MIN_SENTENCE_WORDS = 4
SIMILARITY_THRESHOLD = 0.35


@dataclass
class Candidate:
    candidate_id: str
    matter_id: str
    text: str
    learned_week: int
    source_session: str
    supersedes: str | None = None
    supersedes_score: float = 0.0


@dataclass
class ExtractionResult:
    candidates: list[Candidate] = field(default_factory=list)
    rejected_no_matter: list[tuple[str, str]] = field(default_factory=list)  # (session_id, sentence)


def split_sentences(text: str) -> list[str]:
    parts = SENTENCE_RE.split(text.strip())
    return [p.strip() for p in parts if len(p.strip().split()) >= MIN_SENTENCE_WORDS]


def extract(sessions: list[Session]) -> ExtractionResult:
    result = ExtractionResult()
    next_id = 1
    for session in sessions:
        for sentence in split_sentences(session.transcript):
            # `type(...) is str`, not `isinstance`, and `.strip()`, not just
            # truthiness: a whitespace-only matter_id passed the bare
            # `if not session.matter_id` check this used to be (bug class
            # found and fixed in graph_store.py/compartment_store.py by the
            # first audit round, reproduced here by the second round
            # because the fix wasn't applied everywhere); a `str` subclass
            # with a lying `__eq__` would defeat the `==` comparison below
            # regardless of this check's truthiness test (found by a third
            # audit round, fixed the same way as scenario.require_matter_id).
            if type(session.matter_id) is not str or not session.matter_id.strip():
                result.rejected_no_matter.append((session.session_id, sentence))
                continue
            candidate_id = f"extracted-{next_id}"
            next_id += 1
            same_matter = [
                (c.candidate_id, c.text) for c in result.candidates if c.matter_id == session.matter_id
            ]
            supersedes = None
            score = 0.0
            if same_matter:
                ranked = rank(sentence, same_matter, top_k=1)
                if ranked and ranked[0][1] >= SIMILARITY_THRESHOLD:
                    supersedes, score = ranked[0]
            result.candidates.append(Candidate(
                candidate_id=candidate_id,
                matter_id=session.matter_id,
                text=sentence,
                learned_week=session.week,
                source_session=session.session_id,
                supersedes=supersedes,
                supersedes_score=score,
            ))
    return result


def main() -> None:
    sessions = build_sessions()
    result = extract(sessions)
    supersessions = [c for c in result.candidates if c.supersedes]

    print(f"Total candidate facts extracted: {len(result.candidates)}")
    print(f"Supersession events detected: {len(supersessions)}")
    print(f"Sentences rejected for missing matter_id: {len(result.rejected_no_matter)}")
    print()

    print("=== Rejected sentences (no matter_id -- structural guarantee holds) ===")
    for session_id, sentence in result.rejected_no_matter:
        print(f"  [{session_id}] {sentence!r}")
    print()

    print("=== Detected supersession events ===")
    by_id = {c.candidate_id: c for c in result.candidates}
    for c in supersessions:
        original = by_id[c.supersedes]
        print(f"  {c.candidate_id} (session {c.source_session}, week {c.learned_week}) "
              f"supersedes {c.supersedes} (session {original.source_session}, score={c.supersedes_score:.3f})")
        print(f"    new:      {c.text!r}")
        print(f"    original: {original.text!r}")
    print()

    print("=== All extracted candidates, in order ===")
    for c in result.candidates:
        marker = f" [supersedes {c.supersedes}, score={c.supersedes_score:.3f}]" if c.supersedes else ""
        print(f"  {c.candidate_id} [{c.matter_id}] (session {c.source_session}, week {c.learned_week}){marker}")
        print(f"    {c.text!r}")


if __name__ == "__main__":
    main()
