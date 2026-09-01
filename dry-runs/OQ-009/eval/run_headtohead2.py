"""Generalization check: same three architectures, same retrieval-confidence
rule (memory_lab/retrieval.py's ABS_FLOOR/REL_MARGIN), against scenario2 (a
different domain/vocabulary, more paraphrased queries) -- not re-tuned to
fit. See README "Generalization check".

Usage: python -m eval.run_headtohead2
"""
from eval.run_headtohead import run

SNAPSHOT_DATE = "2026-02-10"  # matches the last query's as_of in scenario2 -- the same
# "literal maximum" principle applied in eval/run_headtohead.py for scenario 1.

if __name__ == "__main__":
    from scenario2.timeline import build_timeline
    from scenario2.queries import QUERIES

    report = run(
        build_timeline, QUERIES,
        title="Generalization check: same architectures, scenario2 (independent vocabulary)",
        snapshot_date=SNAPSHOT_DATE,
    )
    print(report)
    import os
    os.makedirs("results", exist_ok=True)
    with open("results/headtohead2_output.txt", "w") as f:
        f.write(report + "\n")
