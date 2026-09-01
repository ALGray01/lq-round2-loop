import pytest

from legal_memory.scenario import Fact, build_facts, build_sessions


def test_fact_requires_nonempty_matter_id():
    with pytest.raises(ValueError):
        Fact(fact_id="x", matter_id="", text="t", recorded_at=1, source_session=1)
    with pytest.raises(ValueError):
        Fact(fact_id="x", matter_id=None, text="t", recorded_at=1, source_session=1)


def test_fact_accepts_valid_matter_id():
    f = Fact(fact_id="x", matter_id="doe_v_acme", text="t", recorded_at=1, source_session=1)
    assert f.matter_id == "doe_v_acme"


def test_build_facts_all_have_unique_ids_and_valid_matters():
    facts = build_facts()
    ids = [f.fact_id for f in facts]
    assert len(ids) == len(set(ids)), "fact_ids must be unique"
    assert all(f.matter_id in ("doe_v_acme", "estate_wu") for f in facts)


def test_build_sessions_has_exactly_one_untagged_session():
    sessions = build_sessions()
    untagged = [s for s in sessions if s.matter_id is None]
    assert len(untagged) == 1, "scenario should have exactly one untagged session (the T6 tagging-drift trap)"
    assert untagged[0].session_id == 3


def test_supersession_chain_references_real_fact_ids():
    facts = build_facts()
    ids = {f.fact_id for f in facts}
    for f in facts:
        if f.supersedes is not None:
            assert f.supersedes in ids, f"{f.fact_id} supersedes unknown fact {f.supersedes}"
