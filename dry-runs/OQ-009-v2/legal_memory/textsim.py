"""Pure-stdlib TF-IDF cosine similarity.

Used identically by both the proposed graph store and the flat-vector
baseline, so the head-to-head comparison isolates the variable under test
(memory structure: temporal + matter partitioning) rather than differences
in ranking-algorithm quality. No numpy/sklearn dependency -> no install or
network risk (see CLAUDE.md network/install reliability note).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _tf(tokens: list[str]) -> Counter:
    return Counter(tokens)


def build_idf(documents: Iterable[list[str]]) -> dict[str, float]:
    documents = list(documents)
    n = len(documents)
    df: Counter = Counter()
    for tokens in documents:
        for term in set(tokens):
            df[term] += 1
    return {term: math.log((n + 1) / (count + 1)) + 1.0 for term, count in df.items()}


def tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = _tf(tokens)
    return {term: count * idf.get(term, 0.0) for term, count in tf.items()}


def cosine(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    common = set(vec_a) & set(vec_b)
    dot = sum(vec_a[t] * vec_b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class Corpus:
    """Fits IDF once over a set of documents, then scores queries against them."""

    def __init__(self, texts: list[str]):
        self.texts = texts
        self._tokens = [tokenize(t) for t in texts]
        self.idf = build_idf(self._tokens)
        self._vectors = [tfidf_vector(t, self.idf) for t in self._tokens]

    def rank(self, query: str, candidate_indices: list[int]) -> list[tuple[int, float]]:
        """Rank a subset of documents (by index into self.texts) against query."""
        q_tokens = tokenize(query)
        q_vec = tfidf_vector(q_tokens, self.idf)
        scored = [(i, cosine(q_vec, self._vectors[i])) for i in candidate_indices]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored
