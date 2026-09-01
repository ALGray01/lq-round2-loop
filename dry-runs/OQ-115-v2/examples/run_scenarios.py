"""Runs every scenario in scenarios.json through the real Router and prints
a table -- this is what backs the "Example routing decisions" table in
README.md. Uses an isolated, throwaway cap-tracker state file so running it
repeatedly doesn't touch router/cap_state.json or change results run to run.

Run: python examples/run_scenarios.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from router.router import Router  # noqa: E402


def main():
    scenarios = json.loads((Path(__file__).parent / "scenarios.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        router = Router(cap_state_path=Path(tmp) / "cap_state.json")

        rows = []
        for s in scenarios:
            result = router.route(
                text=s["text"],
                stakes=s["stakes"],
                estimated_tokens=s.get("estimated_tokens", 2000),
                min_context_tokens=s.get("min_context_tokens", 0),
            )
            rows.append((s["label"], s["stakes"], result.decision.task_type.value,
                         result.classification.confidence, result.decision.chosen_model_id,
                         result.decision.human_review_required, result.decision.warnings))

        header = f"{'scenario':<38} {'stakes':<7} {'task_type':<24} {'conf':<5} {'chosen_model':<16} {'review?':<7} warnings"
        print(header)
        print("-" * len(header))
        for label, stakes, task_type, conf, model, review, warnings in rows:
            print(f"{label:<38} {stakes:<7} {task_type:<24} {conf:<5.2f} {model:<16} "
                  f"{('yes' if review else 'no'):<7} {'; '.join(warnings)}")


if __name__ == "__main__":
    main()
