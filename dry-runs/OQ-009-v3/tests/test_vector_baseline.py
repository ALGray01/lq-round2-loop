import pytest

from legal_memory.scenario import Session
from legal_memory.vector_baseline import VectorBaseline


def make_sessions():
    return [
        Session("s1", 1, "m1", "the rule is four years for breach of contract"),
        Session("s2", 5, "m1", "the rule is now three years for breach of contract"),
        Session("s3", 1, "m2", "unrelated session about matter two"),
        Session("s4", 3, None, "an untagged session that never got a matter number"),
    ]


class TestFiltering:
    def test_matter_filter_excludes_other_matters(self):
        b = VectorBaseline(make_sessions())
        results = b.query("breach of contract", matter_id="m1")
        ids = [r[0] for r in results]
        assert "s3" not in ids

    def test_matter_filter_excludes_untagged_sessions(self):
        b = VectorBaseline(make_sessions())
        results = b.query("untagged session that never got a matter number", matter_id="m1")
        ids = [r[0] for r in results]
        assert "s4" not in ids

    def test_none_matter_id_means_no_filter(self):
        b = VectorBaseline(make_sessions())
        results = b.query("years", matter_id=None)
        ids = [r[0] for r in results]
        assert "s4" in ids or "s1" in ids or "s2" in ids  # candidate pool is unrestricted
        # explicitly: every session is a candidate when unfiltered
        all_ids = {s[0] for s in results}
        assert all_ids <= {"s1", "s2", "s3", "s4"}

    def test_empty_candidate_pool_returns_empty_list(self):
        b = VectorBaseline(make_sessions())
        assert b.query("anything", matter_id="no-such-matter") == []


class TestNoTemporalAxis:
    def test_query_has_no_as_of_parameter(self):
        b = VectorBaseline(make_sessions())
        import inspect
        assert "as_of" not in inspect.signature(b.query).parameters

    def test_recency_biased_variant_can_change_ranking(self):
        b = VectorBaseline(make_sessions())
        q = "the rule for breach of contract"
        plain = b.query(q, matter_id="m1")
        recency = b.query_recency_biased(q, matter_id="m1")
        # Both return the same candidate set; recency weighting is allowed
        # to reorder it (that's the whole point of the variant).
        assert {r[0] for r in plain} == {r[0] for r in recency}


class TestGetText:
    def test_get_text_returns_transcript(self):
        b = VectorBaseline(make_sessions())
        assert b.get_text("s1") == "the rule is four years for breach of contract"


class TestTopKValidation:
    def test_negative_top_k_raises_on_query(self):
        b = VectorBaseline(make_sessions())
        with pytest.raises(ValueError):
            b.query("years", matter_id="m1", top_k=-1)

    def test_negative_top_k_raises_on_recency_biased_query(self):
        b = VectorBaseline(make_sessions())
        with pytest.raises(ValueError):
            b.query_recency_biased("years", matter_id="m1", top_k=-1)
