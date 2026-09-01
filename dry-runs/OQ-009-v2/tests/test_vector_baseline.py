from legal_memory.scenario import Session
from legal_memory.vector_baseline import VectorBaseline


def _sessions():
    return [
        Session(1, 1, "m1", "the statute of limitations is four years"),
        Session(2, 1, "m2", "the statute of limitations is four years"),
        Session(3, 2, "m1", "the statute of limitations is three years"),
    ]


def _sessions_with_true_tie():
    # Session 1 and 3 have byte-identical text -> identical TF-IDF vectors ->
    # a genuine cosine tie, so the recency tie-break is what decides order
    # (unlike a same-word-overlap-but-different-vocabulary tie, which is not
    # actually a score tie once IDF-weighted norms are taken into account --
    # see the corrected test below, and the removed false assumption it replaces).
    return [
        Session(1, 1, "m1", "the statute of limitations is four years"),
        Session(2, 1, "m2", "completely unrelated content about trusts"),
        Session(3, 2, "m1", "the statute of limitations is four years"),
    ]


def test_matter_filter_excludes_other_matters():
    store = VectorBaseline(_sessions())
    results = store.query("statute of limitations", matter_filter="m1", top_k=5)
    assert all(s.matter_id == "m1" for s in results)


def test_no_filter_can_return_any_matter():
    store = VectorBaseline(_sessions())
    results = store.query("statute of limitations", matter_filter=None, top_k=5)
    matters = {s.matter_id for s in results}
    assert "m2" in matters


def test_recency_biased_prefers_later_session_on_tied_score():
    store = VectorBaseline(_sessions_with_true_tie())
    results = store.query_recency_biased("statute of limitations", matter_filter="m1", top_k=2)
    scores_are_actually_tied = store._corpus.rank("statute of limitations", [0, 2])
    assert round(scores_are_actually_tied[0][1], 9) == round(scores_are_actually_tied[1][1], 9), (
        "test setup assumption broken: sessions 1 and 3 no longer score identically"
    )
    ids = [s.session_id for s in results]
    assert ids[0] == 3, "recency bias should prefer the later session on a genuine tie"


def test_as_of_session_argument_does_not_constrain_results():
    """Documents the structural gap this baseline is meant to expose: passing
    as_of_session does NOT stop a later session's content from surfacing for
    a question scoped to an earlier point in time."""
    store = VectorBaseline(_sessions())
    results = store.query_recency_biased("statute of limitations", matter_filter="m1",
                                          as_of_session=1, top_k=2)
    ids = {s.session_id for s in results}
    assert 3 in ids, "flat baseline has no transaction-time filter to honor as_of_session"
