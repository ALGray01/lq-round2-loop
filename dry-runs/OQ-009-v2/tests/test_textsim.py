from legal_memory.textsim import Corpus, cosine, tfidf_vector, tokenize, build_idf


def test_tokenize_lowercases_and_strips_punctuation():
    assert tokenize("Smith v. Jones, 2024!") == ["smith", "v", "jones", "2024"]


def test_identical_documents_score_near_one():
    idf = build_idf([["breach", "of", "contract"], ["breach", "of", "contract"]])
    v = tfidf_vector(["breach", "of", "contract"], idf)
    assert cosine(v, v) > 0.999


def test_disjoint_vocabulary_scores_zero():
    idf = build_idf([["breach", "contract"], ["trust", "spendthrift"]])
    a = tfidf_vector(["breach", "contract"], idf)
    b = tfidf_vector(["trust", "spendthrift"], idf)
    assert cosine(a, b) == 0.0


def test_empty_vector_scores_zero_not_crash():
    assert cosine({}, {"x": 1.0}) == 0.0
    assert cosine({}, {}) == 0.0


def test_corpus_rank_orders_by_relevance():
    corpus = Corpus([
        "the statute of limitations is three years",
        "the trust instrument has a spendthrift clause",
        "completely unrelated filler text about weather",
    ])
    ranked = corpus.rank("statute of limitations", [0, 1, 2])
    assert ranked[0][0] == 0
    assert ranked[0][1] > ranked[1][1] >= ranked[2][1]


def test_corpus_rank_restricted_to_candidate_subset():
    corpus = Corpus(["statute of limitations", "statute of limitations", "trust clause"])
    ranked = corpus.rank("statute", [2])
    assert [i for i, _ in ranked] == [2]
