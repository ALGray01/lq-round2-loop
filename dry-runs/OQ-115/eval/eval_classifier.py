"""Run the classifier against eval_set.json and report REAL numbers.

This is a small (n=20), hand-labeled, self-authored sanity check on the
heuristic classifier -- NOT a legal benchmark. It was written in the same
sitting as the classifier it tests, by the same process, which is exactly
the circularity trap called out in FAILURE-CLASSES.md item 2: a high
score here proves the classifier agrees with its own author's
expectations, not that either is "correct" in any deeper sense. Several
examples are deliberately phrased to NOT match the keyword lists (see the
"note" fields in eval_set.json) specifically so this report isn't 100%
by construction. Treat this as "does the heuristic behave the way its
author intended on cases they thought of," nothing more. See README.md
"What signal we actually route on" for how this is (and isn't) used.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from router.classifier import classify

EVAL_SET_PATH = Path(__file__).parent / "eval_set.json"
REPORT_PATH = Path(__file__).parent / "eval_report.json"


def run() -> dict:
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    per_case = []
    task_type_correct = 0
    stakes_checked = 0
    stakes_correct = 0

    confusion = defaultdict(lambda: defaultdict(int))

    for case in cases:
        c = classify(case["text"])
        expected_tt = case["expected_task_type"]
        tt_ok = c.task_type == expected_tt
        task_type_correct += int(tt_ok)
        confusion[expected_tt][c.task_type] += 1

        result = {
            "id": case["id"],
            "text": case["text"],
            "expected_task_type": expected_tt,
            "predicted_task_type": c.task_type,
            "task_type_correct": tt_ok,
            "task_type_confidence": c.task_type_confidence,
        }

        if "expected_stakes" in case:
            stakes_checked += 1
            stakes_ok = c.stakes == case["expected_stakes"]
            stakes_correct += int(stakes_ok)
            result["expected_stakes"] = case["expected_stakes"]
            result["predicted_stakes"] = c.stakes
            result["stakes_correct"] = stakes_ok

        per_case.append(result)

    n = len(cases)
    report = {
        "n": n,
        "task_type_accuracy": task_type_correct / n,
        "stakes_accuracy_on_checked_subset": (stakes_correct / stakes_checked) if stakes_checked else None,
        "stakes_checked_n": stakes_checked,
        "confusion_matrix": {k: dict(v) for k, v in confusion.items()},
        "per_case": per_case,
    }
    return report


def main() -> int:
    report = run()
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"n={report['n']}")
    print(f"task_type_accuracy={report['task_type_accuracy']:.2%}")
    if report["stakes_checked_n"]:
        print(
            f"stakes_accuracy_on_checked_subset={report['stakes_accuracy_on_checked_subset']:.2%} "
            f"(n={report['stakes_checked_n']})"
        )
    print("misses:")
    for case in report["per_case"]:
        if not case["task_type_correct"]:
            print(f"  #{case['id']}: expected={case['expected_task_type']} got={case['predicted_task_type']!r} :: {case['text'][:70]}")
        if case.get("stakes_correct") is False:
            print(f"  #{case['id']} (stakes): expected={case['expected_stakes']} got={case['predicted_stakes']!r}")
    print(f"\nfull report written to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
