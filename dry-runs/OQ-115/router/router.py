"""Router orchestration: classify -> pick tier -> pick lane -> call model ->
verify (if required) -> log the decision.

This is the "thin router" the brief asks for. It is intentionally a
library function, not a network proxy: route_request() can be called
directly (see cli.py, demo.py) or wrapped behind an HTTP handler later
without changing the decision logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from router import backends, lanes, logging_util, policy, verify
from router.classifier import Classification, classify


def _estimate_request_tokens(text: str) -> int:
    # Independent of the backend's post-hoc token count: this is the
    # PRE-call estimate used to pick a lane before we know the real cost.
    return max(1, len(text) // 4) + 400  # + headroom for the response


def _system_prompt(task_type: str, stakes: str) -> str:
    return (
        f"You are a legal drafting/review assistant. task_type={task_type}. "
        f"stakes={stakes}. Be precise, hedge appropriately, and do not assert "
        f"unverified case citations as settled fact."
    )


def _critic_system_prompt(task_type: str) -> str:
    return (
        f"You are a legal verification reviewer checking a colleague's draft "
        f"for a task_type={task_type} task before it is relied upon. Identify "
        f"any unsupported claims, missing hedges, or citations that cannot be "
        f"confirmed from the draft alone."
    )


@dataclass
class RoutingDecision:
    request_text: str
    classification: Classification
    tier_decision: policy.TierDecision
    lane_choice: lanes.LaneChoice
    draft_response: str
    draft_tokens: int
    verification: dict | None = field(default=None)

    def to_log_entry(self) -> dict:
        return {
            "request_preview": self.request_text[:200],
            "classification": self.classification.to_dict(),
            "tier_decision": self.tier_decision.to_dict(),
            "lane_choice": self.lane_choice.to_dict(),
            "draft_tokens": self.draft_tokens,
            "verification": self.verification,
        }


def route_request(
    text: str,
    explicit_stakes: str | None = None,
    config: dict | None = None,
    state: dict | None = None,
    state_path=None,
    log_path=None,
) -> RoutingDecision:
    config = config if config is not None else lanes.load_config()
    state_path = state_path if state_path is not None else lanes.DEFAULT_STATE_PATH
    state = state if state is not None else lanes.load_state(state_path)

    classification = classify(text, explicit_stakes=explicit_stakes)
    tier_decision = policy.decide_tier(classification.task_type, classification.stakes)

    estimated_tokens = _estimate_request_tokens(text)
    lane_choice = lanes.pick_lane(
        tier_decision.tier, classification.stakes, estimated_tokens, config, state
    )

    backend = backends.get_backend(config[lane_choice.lane]["provider"])
    system_prompt = _system_prompt(classification.task_type, classification.stakes)
    draft_text, draft_tokens = backend.complete(system_prompt, text, lane_choice.model)

    lanes.consume(lane_choice.lane, lane_choice.tier, draft_tokens, state)

    verification = None
    if tier_decision.verification_required:
        critic_system = _critic_system_prompt(classification.task_type)
        critic_text, critic_tokens = backend.complete(critic_system, draft_text, lane_choice.model)
        lanes.consume(lane_choice.lane, lane_choice.tier, critic_tokens, state)

        pattern_check = verify.verify_output(draft_text)
        verification = {
            "model_critic_response": critic_text,
            "pattern_check": pattern_check.to_dict(),
            "passed": pattern_check.passed,
        }

    lanes.save_state(state, state_path)

    decision = RoutingDecision(
        request_text=text,
        classification=classification,
        tier_decision=tier_decision,
        lane_choice=lane_choice,
        draft_response=draft_text,
        draft_tokens=draft_tokens,
        verification=verification,
    )

    logging_util.append_log(decision.to_log_entry(), path=log_path or logging_util.DEFAULT_LOG_PATH)

    return decision
