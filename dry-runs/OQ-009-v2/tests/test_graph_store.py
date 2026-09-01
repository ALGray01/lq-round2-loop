import pytest

from legal_memory.graph_store import GraphMemoryStore
from legal_memory.scenario import Fact


def _facts():
    return [
        Fact(fact_id="old", matter_id="m1", text="the rule is four years",
             recorded_at=1, source_session=1, invalidated_at=5,
             valid_from=10, valid_until=None),
        Fact(fact_id="new", matter_id="m1", text="the rule is three years",
             recorded_at=5, source_session=5, invalidated_at=None,
             valid_from=20, valid_until=None, supersedes="old"),
        Fact(fact_id="other-matter", matter_id="m2", text="the rule is four years",
             recorded_at=1, source_session=1),
    ]


def test_query_requires_matter_id_argument_present():
    store = GraphMemoryStore(_facts())
    with pytest.raises(TypeError):
        store.query(query_text="the rule")  # matter_id omitted entirely


@pytest.mark.parametrize("bad_matter_id", [None, ""])
def test_query_rejects_falsy_matter_id_value(bad_matter_id):
    store = GraphMemoryStore(_facts())
    with pytest.raises(ValueError):
        store.query(bad_matter_id, "the rule")


def test_now_mode_returns_only_current_belief():
    store = GraphMemoryStore(_facts())
    results = store.query("m1", "the rule", top_k=5)
    ids = [f.fact_id for f in results]
    assert "new" in ids
    assert "old" not in ids


def test_as_of_transaction_boundary_recorded_at_is_inclusive():
    # "new" has recorded_at=5; asking as_of session 5 should already see it.
    store = GraphMemoryStore(_facts())
    results = store.query("m1", "the rule", as_of_transaction_session=5, top_k=5)
    ids = [f.fact_id for f in results]
    assert "new" in ids


def test_as_of_transaction_boundary_invalidated_at_is_inclusive_exclusion():
    # "old" has invalidated_at=5; asking as_of session 5 should NOT see it
    # (it is considered already superseded at the moment of supersession).
    store = GraphMemoryStore(_facts())
    results = store.query("m1", "the rule", as_of_transaction_session=5, top_k=5)
    ids = [f.fact_id for f in results]
    assert "old" not in ids


def test_as_of_transaction_one_session_before_invalidation_sees_old_belief():
    store = GraphMemoryStore(_facts())
    results = store.query("m1", "the rule", as_of_transaction_session=4, top_k=5)
    ids = [f.fact_id for f in results]
    assert "old" in ids
    assert "new" not in ids  # recorded_at=5 > 4, doesn't exist yet


def test_valid_time_boundary_valid_from_is_inclusive():
    store = GraphMemoryStore(_facts())
    results = store.query("m1", "the rule", as_of_valid_time=20, top_k=5)
    ids = [f.fact_id for f in results]
    assert "new" in ids  # valid_from=20, as_of=20 -> included


def test_valid_time_boundary_valid_until_is_exclusive():
    facts = _facts()
    facts.append(Fact(fact_id="capped", matter_id="m1", text="capped rule",
                       recorded_at=1, source_session=1,
                       valid_from=10, valid_until=15, invalidated_at=5))
    store = GraphMemoryStore(facts)
    # as_of_valid_time exactly at valid_until should be excluded (half-open interval)
    results = store.query("m1", "capped rule", as_of_transaction_session=4,
                           as_of_valid_time=15, top_k=5)
    ids = [f.fact_id for f in results]
    assert "capped" not in ids


def test_matter_partition_never_crosses():
    store = GraphMemoryStore(_facts())
    results = store.query("m1", "the rule", top_k=5)
    assert all(f.matter_id == "m1" for f in results)


def test_enforce_time_false_ignores_all_temporal_bounds():
    store = GraphMemoryStore(_facts(), enforce_time=False)
    results = store.query("m1", "the rule", top_k=5)
    ids = {f.fact_id for f in results}
    assert {"old", "new"} <= ids, "with time enforcement off, superseded facts leak back in"


def test_enforce_matter_false_leaks_across_matters():
    store = GraphMemoryStore(_facts(), enforce_matter=False)
    results = store.query("m1", "the rule", top_k=5)
    ids = {f.fact_id for f in results}
    assert "other-matter" in ids, "with matter enforcement off, other matters' facts leak in"


def test_query_ignoring_matter_wall_mixes_matters_by_design():
    store = GraphMemoryStore(_facts())
    results = store.query_ignoring_matter_wall("the rule", top_k=5)
    matters = {f.matter_id for f in results}
    assert len(matters) > 1, "this method exists specifically to demonstrate the unwalled case"
