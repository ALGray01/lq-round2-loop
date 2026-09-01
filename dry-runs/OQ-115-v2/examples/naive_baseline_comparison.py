"""Two naive baseline routers, for comparison against router/ (see README's
"Why this and not a generic router" claim). Written by the reserve-phase
adversarial audit's Baseline builder persona, not by the same process that
built router/ -- see README's Reflection for why that independence matters.

Both baselines read router/models.json directly (no hand-copied model data)
and ignore task type, stakes, and cap state entirely -- that's the point:
they are "the obvious thing you'd do if you didn't build this router."

  a) always_cheapest: lowest cost_per_1m_blended_usd, every request.
  b) always_frontier: highest `reasoning` tier, every request (ties broken
     by lowest cost among the tied models, since a real "just use the best"
     lawyer has no principled way to break the tie either).

Run: python examples/naive_baseline_comparison.py
"""

from __future__ import annotations

import json
from pathlib import Path

MODELS_PATH = Path(__file__).parent.parent / "router" / "models.json"
SCENARIOS_PATH = Path(__file__).parent / "scenarios.json"


def load_models():
    data = json.loads(MODELS_PATH.read_text())
    return data["models"]


def always_cheapest(models):
    return min(models, key=lambda m: m["cost_per_1m_blended_usd"])["id"]


def always_frontier(models):
    best_reasoning = max(m["reasoning"] for m in models)
    candidates = [m for m in models if m["reasoning"] == best_reasoning]
    return min(candidates, key=lambda m: m["cost_per_1m_blended_usd"])["id"]


def main():
    models = load_models()
    scenarios = json.loads(SCENARIOS_PATH.read_text())

    cheapest_pick = always_cheapest(models)
    frontier_pick = always_frontier(models)

    print(f"always_cheapest pick (every scenario): {cheapest_pick}")
    print(f"always_frontier pick (every scenario): {frontier_pick}")
    print()

    header = f"{'scenario':<38} {'stakes':<7} {'naive-cheapest':<16} {'naive-frontier':<16}"
    print(header)
    print("-" * len(header))
    for s in scenarios:
        print(f"{s['label']:<38} {s['stakes']:<7} {cheapest_pick:<16} {frontier_pick:<16}")


if __name__ == "__main__":
    main()
