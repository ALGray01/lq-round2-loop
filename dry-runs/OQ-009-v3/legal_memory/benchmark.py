"""Real scale measurement: build/query latency vs. corpus size.

Neither `GraphMemoryStore` nor `VectorBaseline` builds an index at
construction time beyond storing the fact list -- ranking happens entirely
inside `query()`, via `textsim.rank()`, which rebuilds a TF-IDF corpus over
the *matter-scoped candidate set* every call. So "build" here means store
construction (cheap, just list storage) and "query" means the real
per-query TF-IDF cost, which is what actually matters for a long-running
system: this is measured directly with `time.perf_counter`, not assumed.

A long-running legal practice accumulates more matters over time, not one
matter that grows without bound -- so N here scales the number of matters
(10 facts each), and every query stays scoped to one matter. That is the
realistic shape of growth this benchmark is checking.
"""
from __future__ import annotations

import random
import time

from .graph_store import GraphMemoryStore
from .scenario import Fact

WORDS = (
    "contract breach statute limitations tolling demand letter precedent "
    "overturned amendment defendant plaintiff trustee vendor invoice "
    "fiduciary duty appellate motion filing counsel matter client research"
).split()


def make_facts(n_matters: int, facts_per_matter: int = 10, seed: int = 0) -> list[Fact]:
    rng = random.Random(seed)
    facts = []
    for m in range(n_matters):
        matter_id = f"matter-{m}"
        for i in range(facts_per_matter):
            text = " ".join(rng.choices(WORDS, k=12))
            facts.append(Fact(f"m{m}-f{i}", matter_id, text, learned_week=i, valid_from_week=i))
    return facts


def time_it(fn, repeats: int = 5) -> float:
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best * 1000.0  # ms


def main() -> None:
    print(f"{'N facts':<12}{'N matters':<12}{'build ms':<12}{'query ms':<12}")
    print("-" * 48)
    for n_matters in (10, 100, 500, 2000):
        facts = make_facts(n_matters)
        build_ms = time_it(lambda: GraphMemoryStore(facts))
        store = GraphMemoryStore(facts)
        target_matter = "matter-0"
        query_ms = time_it(lambda: store.query(target_matter, "contract breach statute limitations"))
        print(f"{len(facts):<12}{n_matters:<12}{build_ms:<12.3f}{query_ms:<12.3f}")


if __name__ == "__main__":
    main()
