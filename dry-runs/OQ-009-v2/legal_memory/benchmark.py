"""Quantifies the "O(n) linear scan" limitation named in README.md instead of
just asserting it. Generates synthetic facts/sessions at increasing corpus
sizes and times real queries against GraphMemoryStore and VectorBaseline.

Run: python -m legal_memory.benchmark
"""
from __future__ import annotations

import random
import time

from legal_memory.scenario import Fact, Session
from legal_memory.graph_store import GraphMemoryStore
from legal_memory.vector_baseline import VectorBaseline

_VOCAB = (
    "statute limitations breach contract precedent tolling defendant "
    "plaintiff trust spendthrift vendor clause amendment appellate holding "
    "demand letter filing motion discovery deposition damages liability "
    "negligence indemnification jurisdiction venue arbitration settlement"
).split()


def _random_text(rng: random.Random, n_words: int = 20) -> str:
    return " ".join(rng.choice(_VOCAB) for _ in range(n_words))


def _make_facts(n: int, seed: int = 0) -> list[Fact]:
    rng = random.Random(seed)
    matters = [f"matter_{i}" for i in range(max(1, n // 50))]
    facts = []
    for i in range(n):
        recorded_at = rng.randint(1, 200)
        invalidated = recorded_at + rng.randint(1, 50) if rng.random() < 0.2 else None
        facts.append(Fact(
            fact_id=f"f{i}", matter_id=rng.choice(matters), text=_random_text(rng),
            recorded_at=recorded_at, source_session=recorded_at, invalidated_at=invalidated,
        ))
    return facts, matters


def _make_sessions(n: int, seed: int = 0) -> list[Session]:
    rng = random.Random(seed)
    matters = [f"matter_{i}" for i in range(max(1, n // 50))]
    return [Session(i, i // 2, rng.choice(matters), _random_text(rng)) for i in range(n)]


def _time_it(fn, repeats: int = 20) -> float:
    start = time.perf_counter()
    for _ in range(repeats):
        fn()
    return (time.perf_counter() - start) / repeats


def run(sizes: list[int] = (100, 1000, 5000, 20000)) -> list[dict]:
    rows = []
    for n in sizes:
        facts, matters = _make_facts(n)
        sessions = _make_sessions(n)

        t0 = time.perf_counter()
        graph = GraphMemoryStore(facts)
        graph_build_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        baseline = VectorBaseline(sessions)
        baseline_build_s = time.perf_counter() - t0

        rng = random.Random(42)
        query_text = _random_text(rng)
        matter_id = matters[0]

        graph_query_s = _time_it(lambda: graph.query(matter_id, query_text, top_k=3))
        baseline_query_s = _time_it(lambda: baseline.query(query_text, matter_filter=matter_id, top_k=3))

        rows.append(dict(
            n=n,
            graph_build_ms=graph_build_s * 1000,
            baseline_build_ms=baseline_build_s * 1000,
            graph_query_ms=graph_query_s * 1000,
            baseline_query_ms=baseline_query_s * 1000,
        ))
    return rows


def format_report(rows: list[dict]) -> str:
    lines = [f"{'N facts/sessions':<18}{'graph build ms':<16}{'baseline build ms':<19}"
             f"{'graph query ms':<16}{'baseline query ms':<18}"]
    lines.append("-" * 87)
    for r in rows:
        lines.append(f"{r['n']:<18}{r['graph_build_ms']:<16.2f}{r['baseline_build_ms']:<19.2f}"
                      f"{r['graph_query_ms']:<16.2f}{r['baseline_query_ms']:<18.2f}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== Scale benchmark: linear-scan cost as corpus size grows ===\n")
    rows = run()
    print(format_report(rows))
    print("\nBoth stores are O(n) per query in this prototype (candidate")
    print("filtering + TF-IDF scoring is a full scan every time); the numbers")
    print("above are this run's actual measurements, not an estimate.")
