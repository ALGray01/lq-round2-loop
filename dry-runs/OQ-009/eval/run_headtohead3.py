"""Second generalization check: same three architectures, same
retrieval-confidence rule (un-retuned), against scenario3 (a third,
independently-authored domain/vocabulary). See README "Generalization
check, round 2".

Usage: python -m eval.run_headtohead3
"""
from eval.run_headtohead import run

SNAPSHOT_DATE = "2026-02-10"  # matches the last query's as_of, same "literal maximum"
# principle used for scenario 1 and scenario 2.

if __name__ == "__main__":
    from scenario3.timeline import build_timeline
    from scenario3.queries import QUERIES

    report = run(
        build_timeline, QUERIES,
        title="Generalization check, round 2: same architectures, scenario3 (third vocabulary)",
        snapshot_date=SNAPSHOT_DATE,
    )
    print(report)
    import os
    os.makedirs("results", exist_ok=True)
    with open("results/headtohead3_output.txt", "w") as f:
        f.write(report + "\n")
