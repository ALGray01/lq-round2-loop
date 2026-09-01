"""TF-IDF cosine similarity, stdlib only, shared by every store in this repo.

Every memory backend compared in this repo (graph, compartment, flat
baseline) ranks candidate facts with this exact function. That is
deliberate: the eval is supposed to isolate memory *structure* (what a
store even lets you ask for) from ranking-algorithm quality. If each store
used its own similarity code, a win or loss could be an artifact of one
store having a better ranker, not a better memory architecture.
"""
from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def build_idf(documents: list[str]) -> dict[str, float]:
    """IDF over a corpus of documents (one per candidate fact/session)."""
    n = len(documents)
    df: Counter[str] = Counter()
    for doc in documents:
        for term in set(tokenize(doc)):
            df[term] += 1
    # +1 smoothing so an unseen term doesn't divide by zero and a term seen
    # in every document still gets a small positive weight.
    return {term: math.log((n + 1) / (count + 1)) + 1.0 for term, count in df.items()}


def tfidf_vector(text: str, idf: dict[str, float]) -> dict[str, float]:
    tokens = tokenize(text)
    if not tokens:
        return {}
    tf = Counter(tokens)
    length = len(tokens)
    return {term: (count / length) * idf.get(term, 0.0) for term, count in tf.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    shared = set(a) & set(b)
    numerator = sum(a[t] * b[t] for t in shared)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return numerator / (norm_a * norm_b)


def rank(query_text: str, candidates: list[tuple[str, str]], top_k: int = 3) -> list[tuple[str, float]]:
    """Rank candidates by cosine similarity to query_text.

    candidates: list of (id, text) pairs. Returns list of (id, score) sorted
    descending by score, ties broken by candidate id for determinism.
    """
    if top_k < 0:
        # `scored[:top_k]` with a negative top_k is valid Python but means
        # "drop the last |top_k| items," not "no limit" -- silently wrong,
        # not a crash, and easy to hit by accident. Found by adversarial
        # audit; reject it loudly instead.
        raise ValueError("top_k must be non-negative")
    if not candidates:
        return []
    corpus = [text for _, text in candidates] + [query_text]
    idf = build_idf(corpus)
    query_vec = tfidf_vector(query_text, idf)
    scored = []
    for cid, text in candidates:
        vec = tfidf_vector(text, idf)
        scored.append((cid, cosine(query_vec, vec)))
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return scored[:top_k]
