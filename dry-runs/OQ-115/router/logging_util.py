"""Append-only JSONL audit log of routing decisions.

Every routed request produces one line: what was decided (task type,
stakes, tier, lane, model, verification outcome) and why (the rationale
strings collected from classifier/policy/lanes). This is what makes the
router's choices auditable rather than merely asserted, per the brief.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOG_PATH = Path(__file__).parent.parent / "logs" / "routing_log.jsonl"


def append_log(entry: dict, path: Path = DEFAULT_LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = dict(entry)
    entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
