import pytest

from legal_memory.compartment_store import CompartmentMemoryStore
from legal_memory.scenario import Fact


def _facts():
    return [
        Fact(fact_id="old", matter_id="m1", text="the rule is four years",
             recorded_at=1, source_session=1, invalidated_at=5),
        Fact(fact_id="new", matter_id="m1", text="the rule is three years",
             recorded_at=5, source_session=5),
    ]


def test_has_no_as_of_parameters_at_all():
    store = CompartmentMemoryStore(_facts())
    with pytest.raises(TypeError):
        store.query("m1", "the rule", as_of_transaction_session=1)


def test_returns_only_current_layer():
    store = CompartmentMemoryStore(_facts())
    results = store.query("m1", "the rule", top_k=5)
    ids = [f.fact_id for f in results]
    assert ids == ["new"]


def test_rejects_falsy_matter_id():
    store = CompartmentMemoryStore(_facts())
    with pytest.raises(ValueError):
        store.query("", "the rule")
