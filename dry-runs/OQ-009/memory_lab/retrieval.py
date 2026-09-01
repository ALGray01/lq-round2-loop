"""Stdlib TF-IDF cosine similarity search.

Honest disclosure (see README limitations): this stands in for a real
embedding-based vector search. No ANTHROPIC_API_KEY / embedding API was
available in this build environment, so an embedding-based nearest-neighbor
index was not runnable end-to-end. TF-IDF cosine similarity is a real,
legitimate lexical IR technique (not a mock) -- it will behave differently
from a semantic embedding index on paraphrase-heavy queries, but the
supersession/compartment-leakage failure modes this test targets are
structural (does the *architecture* track validity/scope at all), not a
function of embedding quality, so the substitution does not change what
the head-to-head test is measuring.
"""
import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# A fixed absolute cosine-similarity cutoff (0.15) was the first version of
# this guard, and it worked on scenario/ (real matches ~0.30-0.45, spurious
# stopword-only overlap ~0.05-0.06) but was shown, by scenario2/ -- a second,
# independently-authored corpus -- to reject a real episodic match that
# scored only 0.119 in a sparser two-turn corpus (see README "Generalization
# check"). The failure mode a fixed cutoff can't see: what matters isn't the
# top score in isolation, it's whether the top candidate is *meaningfully
# ahead of the runner-up*, which is scale-invariant across corpus size and
# vocabulary. Replaced with a relative-margin rule, verified against both
# scenarios' real candidate-score distributions (see confident_top below).
ABS_FLOOR = 0.02       # guards the degenerate one-candidate-with-near-zero-overlap case
REL_MARGIN = 1.3       # top score must be at least this many times the runner-up's


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class TfidfIndex:
    """A tiny from-scratch TF-IDF cosine similarity index over documents.

    Each document is (doc_id, text). `search` returns doc_ids ranked by
    cosine similarity to the query, highest first.
    """

    def __init__(self, documents: list[tuple[str, str]]):
        self.doc_ids = [d[0] for d in documents]
        self._tokens = {doc_id: tokenize(text) for doc_id, text in documents}
        self._df = Counter()
        for toks in self._tokens.values():
            for term in set(toks):
                self._df[term] += 1
        self._n_docs = max(len(documents), 1)
        self._doc_vecs = {doc_id: self._vectorize(toks) for doc_id, toks in self._tokens.items()}

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log((self._n_docs + 1) / (df + 1)) + 1.0

    def _vectorize(self, tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        return {term: count * self._idf(term) for term, count in tf.items()}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(v * b.get(k, 0.0) for k, v in a.items())
        norm_a = math.sqrt(sum(v * v for v in a.values()))
        norm_b = math.sqrt(sum(v * v for v in b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def search(self, query: str, top_k: int = 3) -> list[tuple[str, float]]:
        q_vec = self._vectorize(tokenize(query))
        scored = [(doc_id, self._cosine(q_vec, vec)) for doc_id, vec in self._doc_vecs.items()]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]


def confident_top(ranked: list[tuple[str, float]]) -> tuple[str, float] | None:
    """Return the top (doc_id, score) if it's a confident match, else None.

    "Confident" means: nonzero, above the absolute noise floor, and (when
    there's more than one candidate) ahead of the runner-up by REL_MARGIN --
    a tie or near-tie is exactly what stopword-only overlap looks like
    (every candidate scores the same), while a real match stands out from
    the rest regardless of how large its own absolute score happens to be.
    """
    if not ranked or ranked[0][1] <= ABS_FLOOR:
        return None
    if len(ranked) == 1:
        return ranked[0]
    top_id, top_score = ranked[0]
    second_score = ranked[1][1]
    if second_score <= 0:
        return ranked[0]
    if top_score / second_score >= REL_MARGIN:
        return ranked[0]
    return None
