from legal_memory.textsim import cosine, rank, tfidf_vector, tokenize, build_idf


def test_tokenize_lowercases_and_strips_punctuation():
    assert tokenize("Smith v. Jones!") == ["smith", "v", "jones"]


def test_cosine_identical_vectors_is_one():
    idf = build_idf(["breach of contract", "unrelated text"])
    v = tfidf_vector("breach of contract", idf)
    assert abs(cosine(v, v) - 1.0) < 1e-9


def test_cosine_empty_vector_is_zero():
    idf = build_idf(["some text"])
    v = tfidf_vector("some text", idf)
    assert cosine(v, {}) == 0.0
    assert cosine({}, v) == 0.0


def test_rank_orders_by_similarity_descending():
    candidates = [
        ("a", "breach of contract statute of limitations"),
        ("b", "completely unrelated topic about gardening"),
    ]
    results = rank("breach of contract limitations", candidates, top_k=2)
    assert results[0][0] == "a"
    assert results[0][1] >= results[1][1]


def test_rank_ties_broken_by_id():
    candidates = [("z", "same text"), ("a", "same text")]
    results = rank("same text", candidates, top_k=2)
    assert results[0][0] == "a"  # deterministic tie-break, not insertion order


def test_rank_empty_candidates_returns_empty_list():
    assert rank("anything", [], top_k=3) == []
