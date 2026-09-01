"""Structural tests only -- this experiment's whole point is that its
*extraction quality* is mediocre and reported honestly in README.md, not
asserted to be good. These tests lock in the guarantees that should hold
regardless of extraction quality: determinism, and that the untagged
session can never produce a Fact (matter_id is still required)."""
from legal_memory.extractor import extract
from legal_memory.scenario import build_sessions


def test_extraction_is_deterministic():
    sessions = build_sessions()
    facts_a, events_a = extract(sessions)
    facts_b, events_b = extract(sessions)
    assert [f.text for f in facts_a] == [f.text for f in facts_b]
    assert [e.outcome for e in events_a] == [e.outcome for e in events_b]


def test_untagged_session_never_produces_a_fact():
    sessions = build_sessions()
    facts, events = extract(sessions)
    assert all(f.source_session != 3 for f in facts), \
        "session 3 is untagged in the scenario; no Fact should trace back to it"
    rejected = [e for e in events if e.session_id == 3]
    assert rejected and all(e.outcome == "rejected-no-matter" for e in rejected)


def test_all_extracted_facts_have_a_real_matter_id():
    sessions = build_sessions()
    facts, _ = extract(sessions)
    assert all(f.matter_id for f in facts)
