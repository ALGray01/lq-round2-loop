"""Pluggable model backends.

MockBackend is deterministic and always available -- it produces a
clearly-labeled [MOCK] response so nobody mistakes it for a real model
output. It exists so the ROUTING logic (classification, tier selection,
lane/headroom bookkeeping, verification) can be exercised end-to-end and
tested without network access or API keys.

AnthropicBackend calls the real Anthropic Messages API and is used
automatically when ANTHROPIC_API_KEY is set in the environment (only for
the "claude_subscription" lane -- see router/lanes.json). No API key was
available in the environment this was built in, so AnthropicBackend was
exercised via its own unit test (test_backends.py) with the network call
monkeypatched, NOT against the live API. That is an explicit, honest gap
-- see README.md limitations.
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from abc import ABC, abstractmethod


class BackendError(Exception):
    pass


class Backend(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, model: str) -> tuple[str, int]:
        """Return (response_text, estimated_total_tokens)."""
        raise NotImplementedError


def _estimate_tokens(*texts: str) -> int:
    # Rough, provider-agnostic estimate: ~4 chars/token. Good enough for
    # headroom bookkeeping in this demo; not a billing-accurate count.
    total_chars = sum(len(t) for t in texts)
    return max(1, total_chars // 4)


class MockBackend(Backend):
    """Deterministic canned responses, clearly labeled as mock."""

    _TEMPLATES = {
        "litigation_reasoning": (
            "[MOCK:{model}] Draft argument outline: (1) the moving party bears "
            "the burden under the applicable standard; (2) key disputed facts "
            "identified in the record; (3) counterargument anticipated from "
            "opposing counsel and a proposed rebuttal. This is a draft outline, "
            "not final legal advice, and has not been checked against current "
            "authority in this jurisdiction."
        ),
        "transactional_drafting": (
            "[MOCK:{model}] Draft clause: \"Each party shall indemnify and hold "
            "harmless the other party from third-party claims arising out of "
            "its own breach of this Agreement, except to the extent caused by "
            "the indemnified party's negligence.\" This is a first-draft clause "
            "for internal review, not final contract language."
        ),
        "contract_review": (
            "[MOCK:{model}] Review notes: the indemnification clause is "
            "uncapped and one-directional, which is unusual and worth "
            "negotiating; the termination-for-convenience clause has no "
            "notice period specified. Recommend flagging both to the client "
            "before signature."
        ),
        "legal_research": (
            "[MOCK:{model}] Research summary: the general rule in this area "
            "typically turns on [jurisdiction-specific factor]; treatment "
            "varies by jurisdiction and this summary should be confirmed "
            "against current primary sources before being relied upon."
        ),
        "citation_check": (
            "[MOCK:{model}] Citation check: the case name and reporter format "
            "are consistent with standard Bluebook form; could not confirm "
            "subsequent negative treatment (overruling/reversal) without live "
            "access to a citator service."
        ),
    }

    _CRITIC_TEMPLATE = (
        "[MOCK:{model}] Verification review: draft is internally consistent "
        "with the request; no claims beyond what the draft itself supports; "
        "recommend a licensed attorney confirm any citations against a "
        "citator and confirm current-jurisdiction authority before this is "
        "relied upon or filed. No additional red flags identified in review."
    )

    def complete(self, system: str, user: str, model: str) -> tuple[str, int]:
        if "verification reviewer" in system:
            text = self._CRITIC_TEMPLATE.format(model=model)
            return text, _estimate_tokens(system, user, text)

        task_type = "legal_research"
        for t in self._TEMPLATES:
            if t in system:
                task_type = t
                break
        text = self._TEMPLATES[task_type].format(model=model)
        return text, _estimate_tokens(system, user, text)


class AnthropicBackend(Backend):
    """Real Anthropic Messages API call. Requires ANTHROPIC_API_KEY."""

    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise BackendError("ANTHROPIC_API_KEY not set")

    def complete(self, system: str, user: str, model: str) -> tuple[str, int]:
        payload = {
            "model": model,
            "max_tokens": 1024,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        req = urllib.request.Request(
            self.API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.API_VERSION,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise BackendError(f"Anthropic API error {e.code}: {e.read().decode('utf-8', 'replace')}") from e
        except urllib.error.URLError as e:
            raise BackendError(f"Anthropic API unreachable: {e}") from e

        text_parts = [block["text"] for block in body.get("content", []) if block.get("type") == "text"]
        text = "\n".join(text_parts)
        usage = body.get("usage", {})
        total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        if total_tokens == 0:
            total_tokens = _estimate_tokens(system, user, text)
        return text, total_tokens


def get_backend(provider: str) -> Backend:
    if provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return AnthropicBackend()
        except BackendError:
            return MockBackend()
    return MockBackend()
