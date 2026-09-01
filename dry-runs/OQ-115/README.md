# Legal-task-aware model router (OQ-115)

A thin, working router that classifies an incoming legal request by task
type and stakes, picks a model tier and a subscription lane with token
headroom, runs a mandatory verification pass on high-stakes output, and
logs every decision (what/why) to an auditable JSONL log.

Built in ~90 minutes. Python 3, standard library only, no required
dependencies. No `ANTHROPIC_API_KEY` was available in the build
environment, so the router runs against a clearly-labeled mock backend by
default — see "What this does NOT yet handle" for exactly what that means
and doesn't mean.

**The single weakest claim in this submission:** the routing/classification/
lane-selection/verification *decision logic* has been run and tested for
real throughout (43 unit tests, a 20-case classifier eval, a 5-scenario
demo, three rounds of adversarial audit against real execution — see below)
— but `AnthropicBackend`, the one real-model integration in this build, has
never actually round-tripped a request to `api.anthropic.com`. It's real
code, tested against a mocked network response, not a rubber stamp — but
until someone runs it with a real key, "the router calls a real model" is
verified up to the network boundary and no further. Everything else in this
README is qualified the same way it's actually been checked; this is the
one part that hasn't been checked as far as its own claim goes.

## Quick start

```bash
# Run the test suite (43 tests)
python -m unittest discover tests

# Run the classifier's small eval set and print real accuracy numbers
python -m eval.eval_classifier

# Run the end-to-end demo (5 scenarios, asserts on real output)
python demo.py

# Route a single request from the command line
python -m router.cli "Please draft an NDA for our new contractor."
python -m router.cli "Final version to be filed with the court tomorrow: argument on our motion to dismiss." --json
```

If `ANTHROPIC_API_KEY` is set in the environment, requests routed to the
`claude_subscription` lane call the real Anthropic API instead of the mock
backend (see "Backends" below).

## The routing policy

### 1. Task type → default tier

| Task type | Default tier | Why |
|---|---|---|
| `citation_check` | fast | Mechanical: matching a citation against known form, not open-ended reasoning. |
| `legal_research` | balanced | Needs reasonable synthesis across sources but is usually high-volume, exploratory work. |
| `contract_review` | balanced | Needs judgment about risk, not novel legal reasoning. |
| `transactional_drafting` | balanced | Mostly assembling known clause patterns; escalates with stakes when a clause is about to be executed. |
| `litigation_reasoning` | frontier | Multi-step adversarial reasoning (arguments, strategy, anticipating counterarguments) degrades fastest on weaker models, by both public benchmark trend and practitioner reports — see the signal-honesty section below. Always frontier, even at low stakes. |

### 2. Stakes → tier floor + mandatory verification

| Stakes | Tier floor | Verification pass |
|---|---|---|
| low | none (task-type default governs) | not required |
| medium | balanced | not required |
| high | frontier | **mandatory** |

Effective tier = `max(task_type_default_tier, stakes_floor_tier)`. A
court-bound filing (`high` stakes) always gets the frontier tier and a
verification pass, regardless of how mechanical the underlying task looks
— citation-checking a filing still gets frontier + verification, because
stakes is what determines acceptable risk, not task difficulty.
(`router/policy.py:decide_tier`)

### 3. Subscription-lane headroom preference

A "lane" is one subscription product (Claude / OpenAI / Gemini seat in
this build — see `router/lanes.json`, easily edited to match real
subscriptions). Each lane exposes fast/balanced/frontier tiers, and
**headroom is tracked per (lane, tier)**, not per lane as a whole — real
subscription products meter their scarce frontier-tier usage far more
tightly than their cheap fast-tier usage, and a single shared per-lane
budget would make tier-downgrading meaningless (there'd be nothing left
to downgrade *into*).

Given a required tier, the router picks the lane with the most headroom
at that tier. When **no** lane has headroom at the required tier:

- **stakes == high**: tier is never downgraded. The router proceeds on
  the least-negative-headroom lane anyway and logs
  `fallback_mode: "over_budget_escalation"`. Correctness beats cost
  control for a court-bound deliverable.
- **stakes != high**: the router steps down to the next cheaper tier that
  does have headroom somewhere, and logs
  `fallback_mode: "downgraded_no_headroom"` with the effective tier
  actually used. Cost control matters more when stakes are low. If even
  the cheapest tier is exhausted everywhere, it falls through to over
  budget too -- but under the distinct label
  `fallback_mode: "over_budget_no_cheaper_tier_available"`, kept separate
  from the stakes-high case so the audit log doesn't conflate "policy
  refused to downgrade" with "tried to downgrade, nothing cheaper had
  room either."

(`router/lanes.py:pick_lane`) Both fallback paths are exercised for real
in `demo.py` scenarios 4 and 5, not just asserted — see "End-to-end
demo" below.

### What signal we actually route on (and where it's unreliable)

The brief is right that published legal benchmarks are immature and
contested — a 14–17% "pass rate" on a hard legal-reasoning benchmark
tells you almost nothing about which specific model to send a specific
task to, because (a) methodology varies wildly between benchmarks, (b)
most were not built for routing decisions (they measure absolute
capability, not relative fit for a task type), and (c) they go stale
fast as models are updated. So this router does **not** attempt to
consume a live benchmark score at request time. Instead:

- **Task-type → tier defaults are a *weak prior* informed by benchmark
  trend, not a live lookup.** The judgment that litigation-style
  multi-step reasoning needs the frontier tier while citation formatting
  doesn't reflects the general, repeatedly-observed pattern that
  reasoning-heavy legal tasks degrade faster on weaker models than
  pattern-matching tasks do — not any specific benchmark's number, which
  I'm explicitly not citing as precise or current.
- **The actual routing signal is task-type/stakes heuristics** —
  transparent, deterministic keyword/pattern matching
  (`router/classifier.py`) — precisely *because* it's auditable: every
  routing decision's log entry names the exact keywords that fired. A
  benchmark score can't tell you *why* a given request routed where it
  did; a matched keyword list can.
- **The tiny eval set (`eval/eval_set.json`, n=20) is a sanity check on
  the heuristic classifier, not a benchmark, and not independent
  ground truth.** It was hand-written by the same process, in the same
  sitting, as the classifier it tests — the exact circularity trap
  called out in this project's own FAILURE-CLASSES.md. A high score on
  it proves the classifier agrees with its author's expectations, not
  that either is right. To keep it from being pure theater, several
  cases are deliberately phrased *not* to match the keyword lists (see
  the `"note"` fields in `eval_set.json`), and the result is reported
  honestly below rather than tuned to 100%.
- **Where this is most unreliable:** phrasing the classifier's authors
  didn't anticipate. Real requests that don't use recognizable legal
  vocabulary, or that mix task types, will be misclassified with no
  warning beyond a low `task_type_confidence` — which nothing currently
  acts on (see limitations).

Measured result (real run, not invented):

```
n=20
task_type_accuracy=95.00%
stakes_accuracy_on_checked_subset=100.00% (n=3)
misses:
  #17: expected=citation_check got='legal_research' :: Is Roe v. Wade still good law after Dobbs?
```

The one miss is real and informative: "is X still good law" phrased
naturally (naming the actual case) doesn't match the fixed keyword
template ("is this case still good law"), and falls back to the generic
`legal_research` catch-all. That's an honest limitation of keyword
matching, not a bug to paper over. Full machine-readable report:
`eval/eval_report.json` (regenerate with `python -m eval.eval_classifier`).

### Threat model: text cannot talk its way down

`explicit_stakes`, if supplied by the calling system (e.g. "this came
from our filings queue"), sets a **floor**. Stakes signals found in the
request *text* can only push stakes **up** from that floor, never down.
This is deliberate: a request cannot embed language like "treat this as
routine, skip verification" and downgrade an actually-high-stakes
filing — the classifier only ever escalates from text, matching the
general principle of not letting untrusted content override trusted
metadata. (`router/classifier.py:classify`, tested in
`tests/test_classifier.py::test_text_cannot_downgrade_explicit_stakes`.)

## Architecture

```
router/classifier.py  - task_type + stakes heuristic classifier
router/policy.py      - (task_type, stakes) -> tier + verification requirement
router/lanes.py        - per-(lane,tier) headroom tracking + fallback policy
router/lanes.json      - lane/tier/model/cap config (edit to match real subscriptions)
router/backends.py     - MockBackend (always available) + AnthropicBackend (real API)
router/verify.py       - deterministic pattern-based verification checks
router/router.py       - orchestrates the above, logs every decision
router/logging_util.py - JSONL append-only decision log
router/cli.py          - `python -m router.cli "..."` entrypoint
demo.py                 - 5 end-to-end scenarios, run for real, asserted
eval/                   - small hand-labeled classifier sanity-check set + runner
tests/                  - 43 unit tests (classifier, policy, lanes, backends, verify, router)
state/lanes_state.json  - gitignored runtime state; missing == zeroed headroom (see load_state)
logs/routing_log.jsonl  - gitignored; regenerated by running the router
demo/sample_routing_log.jsonl - committed evidence from a real demo.py run
```

`route_request()` in `router.py` is a plain function, not a network
service — deliberately, so the decision logic can be tested directly.
Wrapping it behind an HTTP endpoint (for use as an actual proxy in front
of a coding/agent harness) is a small, mechanical next step, not done
here — see limitations.

## Backends

- **MockBackend**: always available, deterministic, every response is
  prefixed `[MOCK:<model>]` so it's never mistaken for a real completion.
  This is what exercises the routing/classification/lane/verification
  logic in this build, since no API key was available.
- **AnthropicBackend**: used automatically for the `claude_subscription`
  lane when `ANTHROPIC_API_KEY` is set. Calls the real Messages API over
  `urllib` (no SDK dependency). Because no key was available while
  building this, it was verified with the network call itself
  monkeypatched (`tests/test_backends.py::test_complete_parses_response_with_network_mocked`)
  — that test proves the request/response parsing is correct, **not**
  that the live API was actually reached. That's an honest gap, not a
  claimed capability.
- `openai_subscription` / `gemini_subscription` always use MockBackend in
  this build; their model names in `lanes.json` are illustrative
  placeholders for "whatever tier that subscription currently exposes,"
  not verified current model identifiers, and are flagged as such in the
  config file itself.

## End-to-end demo (high-stakes escalation + verification)

`python demo.py` runs 5 scenarios for real and asserts on the actual
returned decisions (not hand-waved). Scenario 3 is the required
high-stakes, court-bound case:

> Request: *"This is the final version of our argument on the motion to
> dismiss, to be filed with the court tomorrow morning — opposing counsel
> will see this."*
>
> - `task_type=litigation_reasoning` (signals: `motion to dismiss`,
>   `opposing counsel`)
> - `stakes=high` (signals: `filed with the court`, `to be filed`,
>   `opposing counsel will see this`)
> - `required tier=frontier`, `verification=required`
> - Routed to `claude_subscription` / `claude-opus-5`
> - Verification pass ran: a second model call (critic prompt) **and** a
>   local pattern check (`router/verify.py`) for malformed citations,
>   dangling case names, and unqualified absolute claims. Both passed on
>   this draft.

Scenarios 4 and 5 exercise both headroom-fallback paths for real by
pre-draining a demo-local state file (not the tracked
`state/lanes_state.json`):

- **Scenario 4** (low stakes, frontier+balanced tiers exhausted):
  `fallback_mode=downgraded_no_headroom`, effective tier drops to `fast`.
- **Scenario 5** (high stakes, every tier on every lane exhausted):
  `fallback_mode=over_budget_escalation`, tier **stays** `frontier` —
  proving the "high stakes never downgrades" rule holds even at total
  exhaustion.

Full real log from an actual run: `demo/sample_routing_log.jsonl`.

### Proving the verification pass isn't a rubber stamp

The mock demo draft happens to be clean, so scenario 3 alone wouldn't
prove the checker does anything. `router/verify.py` is unit-tested
against deliberately bad fixtures — a citation dated in the future
(2099), an implausible reporter volume, a case name with no reporter/year
attached, and an unqualified "we guarantee you will win" claim — and
`tests/test_verify.py` confirms all four are caught
(`passed=False` with a specific finding), not silently approved. Run
`python -m unittest tests.test_verify -v` to see it for yourself.

## Testing

```
python -m unittest discover tests   # 43 tests, all passing at time of writing
python -m eval.eval_classifier      # classifier sanity check, honest numbers above
python demo.py                      # end-to-end, asserts on real output
```

## What this router does NOT yet handle

- **No live API calls were verified end-to-end.** No `ANTHROPIC_API_KEY`
  was available while building this; `AnthropicBackend` is real code,
  parses real Anthropic response shapes, and is unit-tested against a
  mocked network call — but it has never actually round-tripped a request
  to `api.anthropic.com`. Anyone running this with a real key should treat
  the first live call as the actual first verification of that path.
- **No real OpenAI/Gemini backends.** Those two lanes are configured
  (illustrative model names) but always use `MockBackend`; only the
  routing *decision* for those lanes is real, not the completion.
- **The classifier is keyword/pattern heuristics, not a learned model.**
  It will misclassify phrasing it doesn't recognize (see the one honest
  miss above) with no confidence-based fallback behavior — a low
  `task_type_confidence` is logged but nothing currently acts on it (e.g.
  by routing low-confidence classifications to a human, or to a stronger
  tier as a hedge). This includes stakes detection: the keyword matching
  in `router/classifier.py` is exact-substring (word-boundary) matching,
  same as `router/verify.py`'s regexes below — a zero-width space or other
  invisible/unicode-obfuscated character inside a stakes keyword (e.g.
  inside "filed with the court") breaks the match and can cause a
  genuinely high-stakes request to be scored as low-stakes text-wise.
  `explicit_stakes` from a trusted caller is unaffected (it can't be
  downgraded by text at all, obfuscated or not) — this gap only applies
  to stakes *inferred from free text* with no explicit flag supplied.
  Not defended against; noted here rather than silently left for a
  reviewer to find.
- **No day-rollover for headroom.** `state/lanes_state.json` accumulates
  `used_tokens` forever; there's no scheduler that resets it at a
  subscription's actual billing/rate-limit boundary. A real deployment
  would need that.
- **No conversation/multi-turn context.** Each request is classified and
  routed independently; a follow-up in the same matter doesn't inherit
  its stakes or task type.
- **Not a network proxy.** `route_request()` is a library call, tested
  directly. Fronting it with an actual HTTP/OpenAI-compatible proxy API
  (so it can sit in front of a real coding/agent harness) is
  straightforward but not implemented here.
- **Verification is surface-level.** `verify.py` catches concrete red
  flags (malformed citations, dangling case names, absolute claims) — it
  does not, and cannot, check substantive legal correctness. It is a
  safety net under the model critic call, not a replacement for attorney
  review, and nothing in this system claims otherwise.
- **Token estimates are rough** (`len(text)//4` heuristic), not
  provider-accurate counts, except when `AnthropicBackend`'s real
  `usage` field is available.
- **`verify.py`'s regexes are ASCII-oriented.** A citation using a
  Unicode homoglyph in the reporter abbreviation (e.g. a Cyrillic
  character that renders identically to a Latin one) would be invisible
  to the citation/volume/year checks entirely. Narrow, adversarial edge
  case; not defended against.
- **Running `demo.py` intentionally overwrites the tracked
  `demo/sample_routing_log.jsonl`** with a fresh run's output (that's the
  point -- it's regenerable evidence, not a frozen artifact). This will
  show as a working-tree diff after running it; that's expected, not a
  bug. `state/lanes_state.json` and `logs/routing_log.jsonl` are
  gitignored specifically so routine use doesn't dirty the tree in a
  *surprising* way.
