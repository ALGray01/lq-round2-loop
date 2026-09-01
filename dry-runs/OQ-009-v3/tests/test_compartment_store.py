import pytest

from legal_memory.compartment_store import CompartmentMemoryStore
from legal_memory.scenario import Fact


def make_facts():
    return [
        Fact("f1", "m1", "the rule is four years", learned_week=1, valid_from_week=1),
        Fact("f2", "m1", "the rule is now three years", learned_week=5, valid_from_week=5, supersedes="f1"),
        Fact("g1", "m2", "unrelated fact about matter two", learned_week=1, valid_from_week=1),
    ]


class TestCurrentLayerOnly:
    def test_returns_only_current_fact_not_superseded_one(self):
        store = CompartmentMemoryStore(make_facts())
        results = store.query("m1", "years")
        ids = [r[0] for r in results]
        assert "f2" in ids
        assert "f1" not in ids

    def test_has_no_as_of_parameter(self):
        store = CompartmentMemoryStore(make_facts())
        # A real as_of-style call should be a TypeError -- there is no
        # history to query against, by design.
        with pytest.raises(TypeError):
            store.query("m1", "years", as_of=1)


class TestMatterPartition:
    def test_query_requires_non_empty_matter_id(self):
        store = CompartmentMemoryStore(make_facts())
        with pytest.raises(ValueError):
            store.query(None, "years")

    def test_query_rejects_whitespace_only_matter_id(self):
        store = CompartmentMemoryStore(make_facts())
        with pytest.raises(ValueError):
            store.query("   ", "years")

    def test_query_rejects_str_subclass_with_lying_eq(self):
        # Same regression as GraphMemoryStore: a str subclass with __eq__
        # always True would defeat matter isolation via `==` if this were
        # only checked with isinstance() instead of type() is str.
        class EvilMatterId(str):
            def __eq__(self, other):
                return True

            def __hash__(self):
                return hash("evil")

        store = CompartmentMemoryStore(make_facts())
        with pytest.raises(ValueError):
            store.query(EvilMatterId("m1"), "years")

    def test_query_scoped_to_matter_excludes_other_matters(self):
        store = CompartmentMemoryStore(make_facts())
        results = store.query("m1", "unrelated fact about matter two")
        ids = [r[0] for r in results]
        assert "g1" not in ids


class TestGetText:
    def test_get_text_returns_original_text(self):
        store = CompartmentMemoryStore(make_facts())
        assert store.get_text("f2") == "the rule is now three years"

    def test_get_text_missing_id_raises_key_error(self):
        store = CompartmentMemoryStore(make_facts())
        with pytest.raises(KeyError):
            store.get_text("nope")


class TestSupersessionCycles:
    def test_direct_cycle_rejected_at_construction(self):
        facts = [
            Fact("cyc-a", "m1", "text a", learned_week=1, valid_from_week=1, supersedes="cyc-b"),
            Fact("cyc-b", "m1", "text b", learned_week=2, valid_from_week=2, supersedes="cyc-a"),
        ]
        with pytest.raises(ValueError):
            CompartmentMemoryStore(facts)
