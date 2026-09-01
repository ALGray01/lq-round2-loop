import pytest

from legal_memory.graph_store import GraphMemoryStore
from legal_memory.scenario import Fact, validate_no_supersession_cycles


def make_facts():
    return [
        Fact("f1", "m1", "the rule is four years", learned_week=1, valid_from_week=1),
        Fact("f2", "m1", "the rule is now three years", learned_week=5, valid_from_week=5, supersedes="f1"),
        Fact("g1", "m2", "unrelated fact about matter two", learned_week=1, valid_from_week=1),
    ]


class TestFactConstruction:
    def test_rejects_empty_matter_id(self):
        with pytest.raises(ValueError):
            Fact("f", "", "text", learned_week=1, valid_from_week=1)

    def test_rejects_none_matter_id(self):
        with pytest.raises(ValueError):
            Fact("f", None, "text", learned_week=1, valid_from_week=1)

    def test_rejects_whitespace_only_matter_id(self):
        # Adversarial-audit finding: `not "   "` is False in Python, so a
        # check of only `if not matter_id` lets this through silently.
        with pytest.raises(ValueError):
            Fact("f", "   ", "text", learned_week=1, valid_from_week=1)

    def test_rejects_non_string_matter_id(self):
        with pytest.raises(ValueError):
            Fact("f", 0, "text", learned_week=1, valid_from_week=1)

    def test_rejects_str_subclass_matter_id(self):
        # A str subclass passes isinstance(x, str) but not type(x) is str;
        # rejecting it here is what keeps the query-time `==` filter safe
        # from a subclass with an overridden __eq__ (see TestMatterPartition
        # below for the actual leak this would otherwise cause).
        class TaggedStr(str):
            pass

        with pytest.raises(ValueError):
            Fact("f", TaggedStr("m1"), "text", learned_week=1, valid_from_week=1)

    def test_accepts_real_matter_id(self):
        f = Fact("f", "m1", "text", learned_week=1, valid_from_week=1)
        assert f.matter_id == "m1"


class TestBiTemporalBoundary:
    def test_as_of_none_returns_current_superseding_fact(self):
        store = GraphMemoryStore(make_facts())
        results = store.query("m1", "years", as_of=None)
        ids = [r[0] for r in results]
        assert "f2" in ids
        assert "f1" not in ids

    def test_as_of_before_supersession_returns_original(self):
        store = GraphMemoryStore(make_facts())
        results = store.query("m1", "years", as_of=3)
        ids = [r[0] for r in results]
        assert "f1" in ids
        assert "f2" not in ids

    def test_as_of_exact_learned_week_of_successor_includes_successor(self):
        store = GraphMemoryStore(make_facts())
        # learned_week=5 for f2; as_of=5 should count f2 as known (boundary
        # is inclusive: <=), and therefore exclude the superseded f1.
        results = store.query("m1", "years", as_of=5)
        ids = [r[0] for r in results]
        assert "f2" in ids
        assert "f1" not in ids

    def test_as_of_one_week_before_successor_excludes_it(self):
        store = GraphMemoryStore(make_facts())
        results = store.query("m1", "years", as_of=4)
        ids = [r[0] for r in results]
        assert "f2" not in ids
        assert "f1" in ids


class TestMatterPartition:
    def test_query_requires_non_empty_matter_id(self):
        store = GraphMemoryStore(make_facts())
        with pytest.raises(ValueError):
            store.query(None, "years")
        with pytest.raises(ValueError):
            store.query("", "years")

    def test_query_rejects_whitespace_only_matter_id(self):
        store = GraphMemoryStore(make_facts())
        with pytest.raises(ValueError):
            store.query("   ", "years")

    def test_enforce_matter_false_still_requires_a_real_matter_id(self):
        # Regression: an earlier version gated the matter_id *requirement*
        # itself on enforce_matter, not just the filter -- so
        # enforce_matter=False silently accepted matter_id=None too. The
        # flag must only disable the internal filter.
        store = GraphMemoryStore(make_facts(), enforce_matter=False)
        with pytest.raises(ValueError):
            store.query(None, "years")

    def test_query_rejects_str_subclass_with_lying_eq(self):
        # Regression (third audit round, real adversarial finding): a str
        # subclass overriding __eq__ to always return True defeats the
        # `f.matter_id == matter_id` filter regardless of isinstance()
        # passing -- require_matter_id must reject anything that isn't
        # exactly `str`, not just anything that "is a" str.
        class EvilMatterId(str):
            def __eq__(self, other):
                return True

            def __hash__(self):
                return hash("evil")

        store = GraphMemoryStore(make_facts())
        with pytest.raises(ValueError):
            store.query(EvilMatterId("m1"), "years")

    def test_query_does_not_leak_across_matters_via_evil_eq(self):
        # Same attack, confirmed at the leak level: if the type check were
        # ever weakened back to isinstance(), this is the actual damage it
        # would cause -- Matter A facts surfacing in a Matter B query.
        class EvilMatterId(str):
            def __eq__(self, other):
                return True

            def __hash__(self):
                return hash("evil")

        store = GraphMemoryStore(make_facts())
        try:
            results = store.query(EvilMatterId("m2"), "years")
        except ValueError:
            return  # correctly rejected -- the fix works
        ids = [r[0] for r in results]
        assert "f1" not in ids and "f2" not in ids, (
            "matter isolation bypassed: Matter m1 facts leaked into a m2 query"
        )

    def test_query_scoped_to_matter_excludes_other_matters(self):
        store = GraphMemoryStore(make_facts())
        results = store.query("m1", "unrelated fact about matter two")
        ids = [r[0] for r in results]
        assert "g1" not in ids

    def test_enforce_matter_false_exposes_cross_matter_candidates(self):
        store = GraphMemoryStore(make_facts(), enforce_matter=False)
        results = store.query("m1", "unrelated fact about matter two")
        ids = [r[0] for r in results]
        assert "g1" in ids

    def test_enforce_time_false_ignores_as_of(self):
        store = GraphMemoryStore(make_facts(), enforce_time=False)
        results = store.query("m1", "years", as_of=1)
        ids = [r[0] for r in results]
        assert "f2" in ids  # would be excluded at as_of=1 if time were enforced


class TestEmptyInputs:
    def test_empty_store_returns_empty_list(self):
        store = GraphMemoryStore([])
        assert store.query("m1", "anything") == []

    def test_get_text_returns_original_text(self):
        store = GraphMemoryStore(make_facts())
        assert store.get_text("f1") == "the rule is four years"


class TestTopKValidation:
    def test_negative_top_k_raises(self):
        # Adversarial-audit finding: `scored[:-1]` silently drops the last
        # candidate instead of erroring or meaning "unlimited."
        store = GraphMemoryStore(make_facts())
        with pytest.raises(ValueError):
            store.query("m1", "years", top_k=-1)

    def test_zero_top_k_returns_empty_list(self):
        store = GraphMemoryStore(make_facts())
        assert store.query("m1", "years", top_k=0) == []


class TestSupersessionCycles:
    def test_direct_cycle_rejected_at_construction(self):
        # Adversarial-audit finding: A supersedes B and B supersedes A used
        # to silently remove both facts from every query with no error.
        facts = [
            Fact("cyc-a", "m1", "text a", learned_week=1, valid_from_week=1, supersedes="cyc-b"),
            Fact("cyc-b", "m1", "text b", learned_week=2, valid_from_week=2, supersedes="cyc-a"),
        ]
        with pytest.raises(ValueError):
            validate_no_supersession_cycles(facts)
        with pytest.raises(ValueError):
            GraphMemoryStore(facts)

    def test_dangling_supersedes_pointer_is_not_a_cycle(self):
        facts = [
            Fact("f1", "m1", "text", learned_week=1, valid_from_week=1, supersedes="does-not-exist"),
        ]
        validate_no_supersession_cycles(facts)  # should not raise
        GraphMemoryStore(facts)  # should not raise

    def test_normal_supersession_chain_is_not_flagged(self):
        validate_no_supersession_cycles(make_facts())  # should not raise
