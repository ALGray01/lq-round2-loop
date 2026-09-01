# Threat Model: Prompt Injection Against Legal AI Agents

## Scenario

A law firm deploys an AI agent (built on Claude Code, or an equivalent
tool-using LLM agent) to help attorneys and paralegals triage client intake,
summarize opposing-counsel filings, draft correspondence, and manage case
files. The agent has standing access to a case file store and can take
actions on the firm's behalf: reading/writing files, drafting emails,
running local tooling. It is driven by a human operator (the attorney or
their staff), but a large fraction of the *content* it processes on any
given task — client documents, exhibits filed by the other side, emails from
opposing counsel or third parties, intake forms submitted by prospective
clients — originates from parties who are not the operator and may be
actively adversarial to the firm's interests.

This is the classic prompt-injection setup: an LLM agent cannot reliably
distinguish "instructions from my principal" from "data that happens to
contain text shaped like instructions," and everything in its context
window competes for control of its next action.

## Attacker

**Who:** Opposing counsel or their client, a hostile third party (e.g. a
scammer probing the firm's intake pipeline), or a compromised/malicious
sender of an email the agent is asked to process. In the multi-turn class,
the "attacker" may also be a user of the system itself (e.g. a client
using their own portal access) who does not hold the authority they claim.

**Access:** The attacker does not have credentials to the firm's systems and
cannot talk to the agent directly in most cases. What they *can* do is put
text in front of the agent indirectly: write a filing, send an email, submit
a web form, or (in the multi-turn class) simply have an extended
conversation with the agent and try to manipulate it turn by turn. They
control the content but not the delivery mechanism.

**Goal (what the attacker is trying to achieve):** one or more of:

1. **Exfiltration** — get privileged or confidential material (client
   secrets, settlement authority, litigation strategy, PII/PHI, negotiation
   notes) copied somewhere the attacker can read it (an email to an address
   they control, a public file, a response visible to them).
2. **Unauthorized action** — get the agent to take an action only the
   attorney/client should authorize: send a communication, waive privilege,
   agree to a settlement figure, alter or delete records, skip a required
   check (conflicts, authorization).
3. **Work-product corruption** — get the agent to insert false, damaging,
   or attacker-favorable content into a filing, admission, or correspondence
   (a fabricated admission of fault, a wrong deadline, a misstated amount)
   that the firm might file or send without independently re-verifying it.
4. **Instruction override** — get the agent to abandon the operator's actual
   task and instead execute instructions smuggled in through data,
   effectively hijacking the agent's principal—agent relationship.

## What the agent is protecting

- **Confidentiality / privilege**: attorney-client privileged communications
  and work product must not leave the firm's boundary (or be surfaced to
  the wrong party) because an untrusted document or message told the agent
  to.
- **Authority / chain of command**: only the human operator actually driving
  the session (not a document, not an email, not a claimed "supervisor"
  embedded in content) should be able to direct the agent's actions. The
  agent's job is to treat everything under case-file directories as *data
  to analyze*, never as *instructions to obey*.
- **Integrity of legal work product**: filings, correspondence, and records
  the agent drafts or touches must reflect what the firm actually decided,
  not what an adversary tricked the agent into writing or approving.
- **System/tool boundary**: the agent's tools (file writes, "sending"
  correspondence, running commands) should only be used for the operator's
  actual, current, explicitly-stated request — not for requests manufactured
  by content the agent merely read.

## Trust boundary in this test

- **Trusted**: the literal text the human operator types into the current
  session.
- **Untrusted**: everything else the agent's tools can read — files under
  `case_files/`, simulated "emails," simulated filings/exhibits, and
  (in the multi-turn class) a same-channel conversation whose *later*
  turns try to retroactively claim authority the *earlier* turns never
  established.

Note this last point deliberately blurs the boundary the way real social
engineering does: in the multi-turn class, everything nominally arrives via
the "trusted" operator channel, but the attack is that the operator's
identity/authority itself is being spoofed or escalated across turns — the
agent has no cryptographic way to verify that turn 4's speaker is the same
authorized party as turn 1's, or that a claim made in turn 3 ("the partner
approved this") is true.

## Out of scope for this exercise

- Attacks against the underlying model weights (jailbreak research at the
  RLHF level) — we test the deployed agent's behavior, not the model in
  isolation.
- Network/infra security (auth bypass, credential theft) — this is purely
  about content-borne instruction injection.
- Real email/web tool integrations — the harness simulates "sending" mail
  and "fetching" external content via filesystem conventions (see
  `README.md`) rather than wiring up live services, so no real message is
  ever sent to a real address in this test. This narrows the tool surface
  versus a fully-integrated production deployment (see Limitations in
  `README.md`).
