"""Model capability registry, loaded from models.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REGISTRY_PATH = Path(__file__).parent / "models.json"

CAPABILITY_FIELDS = ("reasoning", "drafting", "factual_accuracy")


@dataclass(frozen=True)
class ModelProfile:
    id: str
    provider: str
    reasoning: int
    drafting: int
    factual_accuracy: int
    speed: int
    context_window_tokens: int
    cost_per_1m_blended_usd: float

    def capability(self, field: str) -> int:
        return getattr(self, field)


class RegistryError(RuntimeError):
    """Raised when the model registry file is missing or malformed.

    Unlike cap_tracker.py's state file (runtime-generated, safe to reset to
    zero usage on corruption), models.json is required configuration with
    no sensible empty default -- an audit found a missing/corrupt file
    produced a raw traceback here, same bug class as the already-fixed
    cap-state crash. The right fix here is a clear, actionable error
    instead, not silent degradation to an empty registry.
    """


def load_registry(path: Path | None = None) -> list[ModelProfile]:
    path = path or DEFAULT_REGISTRY_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_models = data["models"]
        models = []
        for m in raw_models:
            models.append(ModelProfile(
                id=m["id"],
                provider=m["provider"],
                reasoning=m["reasoning"],
                drafting=m["drafting"],
                factual_accuracy=m["factual_accuracy"],
                speed=m["speed"],
                context_window_tokens=m["context_window_tokens"],
                cost_per_1m_blended_usd=m["cost_per_1m_blended_usd"],
            ))
    except FileNotFoundError as e:
        raise RegistryError(f"model registry not found at {path}") from e
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise RegistryError(f"model registry at {path} is malformed: {e}") from e

    if not models:
        raise RegistryError(f"model registry at {path} contains no models")
    return models
