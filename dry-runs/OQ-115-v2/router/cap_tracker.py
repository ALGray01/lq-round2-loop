"""Subscription token-cap tracking.

The brief's core pain point: lawyers burn through subscription token caps
because nothing is watching cumulative usage per model. This tracker keeps
a local, persisted running total of tokens consumed per model within the
current billing period and reports remaining headroom so the policy layer
can steer low/medium-stakes work away from a model that's close to its cap
-- reserving headroom on the strong models for when stakes are high.

State is a flat JSON file; this is intentionally simple (no DB) since a
solo/small-firm router doesn't need more, and it keeps the whole submission
dependency-free. See README for how a real deployment would swap this for
a shared store across a firm.
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STATE_PATH = Path(__file__).parent / "cap_state.json"

# Illustrative monthly token caps per model, standing in for a firm's
# actual subscription/plan limits. Override via CapTracker(caps=...) or by
# editing the state file's "caps" section.
DEFAULT_CAPS = {
    "claude-opus": 2_000_000,
    "claude-sonnet": 8_000_000,
    "claude-haiku": 20_000_000,
    "gpt-frontier": 2_000_000,
    "gpt-mini": 20_000_000,
    "gemini-pro": 8_000_000,
}


@dataclass
class CapStatus:
    model_id: str
    cap: int
    used: int

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.cap


class CapTracker:
    def __init__(self, state_path: Path | None = None, caps: dict[str, int] | None = None):
        self.state_path = state_path or DEFAULT_STATE_PATH
        self.caps = dict(caps or DEFAULT_CAPS)
        self.usage: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        # A corrupted or hand-edited state file (crash mid-write, disk full,
        # concurrent writer, manual tampering) must degrade gracefully, not
        # brick every subsequent CLI invocation with a raw traceback -- this
        # file is read on every single command. Fall back to a clean slate
        # for whatever part is unusable, and say so on stderr.
        self.usage = {}
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            print(f"warning: {self.state_path} is corrupted ({e}); starting from zero usage", file=sys.stderr)
            return

        raw_usage = data.get("usage", {}) if isinstance(data, dict) else {}
        raw_caps = data.get("caps", {}) if isinstance(data, dict) else {}
        self.usage = self._clean_numeric_map(raw_usage, "usage")
        self.caps.update(self._clean_numeric_map(raw_caps, "caps"))

    @staticmethod
    def _clean_numeric_map(raw: dict, label: str) -> dict:
        cleaned = {}
        if not isinstance(raw, dict):
            print(f"warning: ignoring malformed '{label}' section in cap state file", file=sys.stderr)
            return cleaned
        for key, value in raw.items():
            # math.isfinite rejects inf/-inf/nan -- json.loads happily parses
            # Infinity/NaN (a Python extension of the JSON spec), and any
            # sufficiently large JSON number literal (e.g. 1e400) silently
            # overflows to float('inf') in plain float() parsing. Either path
            # would otherwise pass `value >= 0` and defeat cap enforcement by
            # making a known model's cap or usage unbounded.
            valid = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value >= 0
            )
            if valid:
                cleaned[key] = value
            else:
                print(f"warning: ignoring invalid {label} entry {key!r}: {value!r}", file=sys.stderr)
        return cleaned

    def save(self) -> None:
        # Write-then-rename instead of a direct write, so a crash or
        # concurrent read never observes a half-written (truncated/invalid
        # JSON) state file -- os.replace is atomic on both POSIX and Windows.
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=self.state_path.parent, prefix=".cap_state_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"caps": self.caps, "usage": self.usage}, f, indent=2)
            os.replace(tmp_path, self.state_path)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    def status(self, model_id: str) -> CapStatus:
        cap = self.caps.get(model_id, float("inf"))
        used = self.usage.get(model_id, 0)
        return CapStatus(model_id=model_id, cap=cap, used=used)

    def record_usage(self, model_id: str, tokens: int) -> CapStatus:
        if tokens < 0:
            raise ValueError(f"tokens must be >= 0, got {tokens}")
        self.usage[model_id] = self.usage.get(model_id, 0) + tokens
        self.save()
        return self.status(model_id)

    def has_headroom(self, model_id: str, estimated_tokens: int) -> bool:
        status = self.status(model_id)
        return status.remaining >= estimated_tokens
