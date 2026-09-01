"""Trivial-baseline sanity check for the classifier holdout evals.

Computes, directly from classifier_holdout_v1.json and
classifier_holdout_v2.json (no hand-counting):
  1. always-predict-"general" accuracy
  2. always-predict-<single most common non-general label> accuracy
  3. expected accuracy of uniform random guessing over 6 labels (just the math)

Answers the obvious follow-up to the classifier evaluation above: is 76%/45%
actually better than doing nothing clever at all? Does not touch router/,
tests/, or classifier_eval.py.

Run: python examples/classifier_trivial_baselines.py
"""
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = {
    "v1": os.path.join(HERE, "classifier_holdout_v1.json"),
    "v2": os.path.join(HERE, "classifier_holdout_v2.json"),
}

REAL_CLASSIFIER_ACCURACY = {
    # as reported in README ("Independent classifier evaluation"):
    "v1": (19, 25),
    "v2": (9, 20),
}

N_LABELS = 6  # litigation_reasoning, transactional_drafting, contract_review,
              # legal_research, citation_checking, general


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    print(f"Random-guessing baseline (1/{N_LABELS} labels): {1 / N_LABELS:.4f} = {100 / N_LABELS:.1f}%")
    print()

    for name, path in FILES.items():
        data = load(path)
        n = len(data)
        labels = [ex["expected_task_type"] for ex in data]
        counts = Counter(labels)

        general_count = counts.get("general", 0)
        general_acc = general_count / n

        non_general_counts = {k: v for k, v in counts.items() if k != "general"}
        max_non_general = max(non_general_counts.values())
        top_non_general_labels = sorted(k for k, v in non_general_counts.items() if v == max_non_general)
        majority_non_general_acc = max_non_general / n

        real_correct, real_total = REAL_CLASSIFIER_ACCURACY[name]
        real_acc = real_correct / real_total

        print(f"=== {name} ({path}) ===")
        print(f"  n = {n}")
        print(f"  label distribution: {dict(sorted(counts.items()))}")
        print(f"  always-'general' baseline: {general_count}/{n} = {general_acc:.1%}")
        print(f"  always-'{'/'.join(top_non_general_labels)}' (majority non-general) baseline: "
              f"{max_non_general}/{n} = {majority_non_general_acc:.1%}")
        print(f"  real classifier (reported in README): {real_correct}/{real_total} = {real_acc:.1%}")
        print()


if __name__ == "__main__":
    main()
