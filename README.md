# An autonomous loop for open-ended build tasks

This is the loop harness I submitted to LegalQuants' LQ Assess Round 2 in
August 2026, together with the design notes behind it and the output of the
test runs I used to develop it.

Round 2 was a loop-engineering exercise rather than a build exercise: you
don't answer the questions yourself. You submit a process that drives Claude
Code unattended, it runs alone in a sealed sandbox against each question on a
fixed turn budget, and whatever is on disk when the budget runs out is what
gets graded. My loop cleared nine of the ten questions and took first place.

**What this repository is.** A copy of my original working directory, cleaned
up for publication rather than a fresh rewrite. Everything here is what I
actually built and ran; what has been removed is material that wasn't mine to
publish — LegalQuants' own repositories, correspondence, and anything relating
to other candidates — along with build artefacts, virtualenvs and the original
git history. The submitted package also included an `ENTRY.md` carrying my
name, GitHub handle and email; that file is not published here. One bug has
been fixed since submission; see *One change since submission* below.

**Why publish it.** No particular agenda: if the loop is useful to you, take
it. It's here for anyone curious about how a harness like this is structured,
anyone who wants to see what an unattended loop actually produces when left
alone with a one-paragraph brief, and anyone who fancies building something
better on top of it. Questions and improvements are welcome.

## The idea

A turn budget is a hard resource that runs out with no warning, so the loop is
built around two pressures: never let a mid-action cutoff leave the repository
incoherent, and never let the most examination-averse part of the work go
unchecked just because it happened to run late.

It spends roughly three quarters of the budget in a **build** phase, committing
continuously so any cutoff still leaves something coherent on disk. Below a
computed threshold it switches to a **reserve** phase, which:

1. Drafts an honest self-assessment *first* — what was actually verified versus
   assumed, the weakest claim shipped, the most consequential decision and the
   alternative it beat. Doing this before the audit rather than after means a
   late cutoff can cost it polish but never its existence.
2. Dispatches three fresh-context subagents in parallel, all sharing one
   mandate — find the most examination-averse claim and verify it against
   actual execution, not by reading — each with a distinct lens:
   - an **attacker**, probing every security-relevant surface with crafted input;
   - a **verification sceptic**, hunting for hollow or circular checks that would
     pass whether or not the logic under them works;
   - a **baseline builder**, constructing the boring alternative to whatever the
     strongest implicit "this is the right approach" claim is.
3. Fixes findings by severity and re-verifies by re-running, not by re-reading
   the diff. A further audit round runs if enough budget remains.

`FAILURE-CLASSES.md` lists seven specific failure patterns the audit checks
explicitly, because a general "review this critically" instruction reliably
misses familiar-looking traps.

## How it was built

The original planning documents aren't published here — they quote
correspondence that isn't mine to republish — so this section covers what was
in them.

### The harness was built the way it tells the model to build

Design spec first, then a written implementation plan broken into seven tasks,
each done test-first: write the failing test, watch it fail, then write the
code. Every task was reviewed by a fresh-context subagent before being marked
done, with findings fixed and re-reviewed until clean. Then one whole-branch
review over the finished thing, which found two things the per-task reviews had
all passed:

- **The build phase wasn't capped at the distance to the reserve threshold.**
  On a 133-turn budget the reserve is roughly one invocation wide, so a single
  long build-phase call could run straight past the boundary and exhaust the
  budget before the reserve prompt — and the entire audit it triggers — was
  ever sent.
- **`lib/retry.sh` was sourced by `loop.sh` and never called from it.** Retry
  existed as a helper offered to the model in `CLAUDE.md`, while the
  orchestrator wrapping every `claude` invocation had none of its own.

Both are absence bugs. Nothing failed; something that should have happened
simply didn't, and no test was watching for it because no test had been written
to expect it. That is the failure mode the whole reserve phase exists to catch,
and it's why the audit's mandate is *verify by running it* rather than *review
the diff*.

### Why three reviewers rather than one

The first working version dispatched a **single** fresh-context auditor with a
general adversarial mandate plus the failure-class checklist. That's the obvious
design, and it does work.

It changed after I stopped and read eight completed dry runs together, in the
round, rather than one at a time as they finished. Four things came out of that
reading:

**1. The same blind spot kept surfacing, and the audit never closed it.** Three
of the eight runs independently named their own weakest claim in nearly the same
words: verified only against my own harness, never against a genuinely
independent real counterpart. The runs could *see* it — they just couldn't fix
it, because nothing instructed them to. It became a seventh failure class,
worded to demand actually obtaining the real counterpart rather than adding more
internal test coverage, and to say precisely why if the budget genuinely didn't
allow it.

**2. The audit checked comparisons but never built one.** As written, it only
asked whether an *existing* comparison was fair against a real steelman — so if
a submission simply never made one, there was nothing to check, and the claim
that some approach was the right one went unexamined precisely because nothing
had been put up against it. Hence the **baseline builder**: find the strongest
implicit "this is the right approach" claim, build the naive version of it, run
both, and report the result honestly even where it undercuts the claim.

**3. Subagent dispatch is turn-cheap, so serial dispatch was wasting the
budget.** Across all eight runs a full audit round cost only a handful of the
loop's own turns, regardless of how much work the subagent did internally — the
loop is charged for dispatching, not for the work. One auditor at a time was
leaving most of that capacity unused. Three dispatched in parallel, in the same
response, cost about what one did.

**4. A single generalist pass drifts toward whatever is cheapest to check.**
This is the actual design claim. All three subagents share one underlying
mandate — find the most examination-averse claim and verify it against real
execution — and splitting that across three narrow lenses (only attack, only
hunt for circular verification, only build the comparison) is what stops each
pass from quietly skipping the expensive question. Worth being straight about
its evidential status: that's a judgement formed from reading the runs, not a
controlled experiment. I never ran the same question with one auditor and with
three and compared the results.

The same reading added a **recall check** as the first question of the
self-assessment: write down from memory what you built and how the key pieces
work, then verify each factual claim in that recollection against the actual
code and output, and correct what memory got wrong. Confidently misremembered
behaviour is the thing self-assessment most reliably gets wrong, and it stays
invisible from the inside unless something specifically sends you to look.

### What the real runs changed

Eighteen runs across the ten questions, several of them re-runs of the same
question after a fix, all on my own machine at my own cost. Four changes came
out of them that I would not have arrived at by reasoning:

**The reserve was raised from 20% to 25% of budget.** A run on OQ-130 showed the
heavier three-persona audit could consume an entire tight reserve window and
never reach the final reflection pass at all.

**The self-assessment is drafted first, not last.** OQ-130 and OQ-112 both lost
their Reflection section to a cutoff on the final call. The fix is ordering
rather than effort: draft and commit it *before* the audit is dispatched, so a
late cutoff can cost it polish but never its existence. `tests/test_content.sh`
asserts that the draft step appears earlier in the prompt file than the dispatch
step, because the ordering is the entire fix.

**The `--max-turns` off-by-one.** When a call is genuinely cut off at a cap of
N, the CLI reports N+1 completed turns. It's consistent — every observed cutoff
across every run matches it, and the same pattern shows in the public reference
runner's own metadata — but left uncorrected it pushes the loop's cumulative
count one turn over budget on a run's final call. The reserve phase now caps one
turn lower to cancel it exactly. One edge case survives, where only a single
turn remains, and it's documented in the code rather than papered over.

A separate and larger variance is *not* fixed: a call that finishes naturally
rather than being cut off has been observed to overrun its own cap by more than
one turn (109 against a cap of 106). Different mechanism, no bound established
from the data I have. Raising the reserve was partly about giving that variance
somewhere to be absorbed.

**The stuckness detector had to learn the difference between broken and
obedient.** The circuit breaker is ported from the public reference runner: two
consecutive loops of two turns or fewer means the session has stopped working,
so stop. It then killed healthy runs twice, in two different ways.

- A build-phase call sitting right at the reserve boundary can legitimately be
  allowed as little as one turn, and returns one turn. That isn't stuckness,
  it's compliance. Now a loop only counts as tiny if it stopped *short of what
  it was allowed* (`turns < cap`).
- A session very near the end of its budget twice declined to start another
  round, each time explaining that it couldn't finish what it started. That's
  good judgement, not a stall. The breaker is now disarmed once remaining turns
  fall below the minimum-round threshold, where stopping early costs almost
  nothing anyway; above that line it stays fully armed, because a genuinely
  stuck session can still burn a meaningful part of the reserve.

Both are the same lesson. A stuckness detector that can't distinguish *stopped
because we told it to* from *stopped because it broke* will eventually kill a
run that was working.

## Layout

| Path | What it is |
|---|---|
| `submission/` | The submitted harness: `loop.sh`, prompt templates, `CLAUDE.md`, `FAILURE-CLASSES.md`, budget and retry helpers |
| `tests/` | Test suite for the harness itself — budget arithmetic, retry, reserve cap, process-group handling, integration |
| `scripts/` | The local dry-run driver, and packaging scripts |
| `dry-runs/` | Output of my own local test runs (see caveat below) |
| `DESIGN-NOTES.md` | The design note as sent at submission time — the fuller account is in *How it was built* above |

`scripts/dry_run.sh` sources each question from LegalQuants' own public
baselines repository, which it expects to find checked out alongside this one:

```bash
git clone https://github.com/LegalQuants/lq-assess-machine-baselines
```

Without it, that script and `tests/test_dry_run_check.sh` will not run.

## About `dry-runs/`

**These are my own local test runs, not the graded ones.** They were run at my
own cost on my own machine while developing the loop. The graded runs happened
later, on LegalQuants' infrastructure, and produced different artefacts. Nothing
here should be read as the submission that was scored.

They are included because they show what the loop actually produces when left
alone with a one-paragraph brief and no supervision.

Each run folder keeps its `QUESTION.md` so the output can be read against the
brief it was answering. Those briefs are LegalQuants' own, and are published in
their public [baselines repository](https://github.com/LegalQuants/lq-assess-machine-baselines).
For OQ-115 and OQ-122 the second run was given a shorter version of the brief
than the first; every other re-run had identical wording.

### What the loop built, run by run

Eighteen runs across the ten questions. Several questions were run more than
once; each re-run is a **fresh, independent session** starting from an empty
directory, not a hand-edited continuation of the one before, so the differences
between them are the loop's own variation rather than mine.

| Question | The brief, abridged | What the loop built | Run |
|---|---|---|---|
| **OQ-008** | Specify what an open legal-markdown standard needs that CommonMark, Pandoc and HTML+CSS don't, and ship a reference implementation for one drafting workflow | `SPEC.md`, plus `lmd` — a Python compiler for a legal-markdown dialect with stable-anchor section numbering, margin paragraph numbers, validated cross-references, defined-term tracking and footnotes. 20 pytest tests. The HTML+CSS pagination gaps were found by actually generating a PDF from its own output and inspecting it, not by reading the specs | [`OQ-008`](dry-runs/OQ-008) |
| | ↳ *re-run* | Same shape, rebuilt on the pure standard library with no dependencies. Adds a linter that exits non-zero on undefined terms, dangling cross-refs and duplicate ids, and `examples/broken.lmd` — a fixture with six deliberately planted errors, there to prove the linter rejects bad input rather than merely accepting good input. 22 tests, including an HTML-escaping check against hostile input | [`OQ-008-v2`](dry-runs/OQ-008-v2) |
| **OQ-009** | The right memory architecture for a legal-research bot that builds context over weeks — knowledge graph, layered compartments, fine-tuning or something else — justified against the alternatives, with a head-to-head test | `memory_lab`: matter-scoped compartments as the outer boundary, a bitemporal fact graph inside each, an episodic log as recall fallback, and no fine-tuning of facts. From-scratch TF-IDF retrieval. A flat-RAG baseline built and actually run rather than described | [`OQ-009`](dry-runs/OQ-009) |
| | ↳ *re-run* | Same recommendation reached independently, argued harder: `matter_id` made a required non-nullable field enforced at construction, so a fact cannot be written without a matter to attach it to — with the ethical-wall bypass that prevents written as explicit test cases | [`OQ-009-v2`](dry-runs/OQ-009-v2) |
| | ↳ *re-run* | The most thorough of the three. A real 7-case eval scoring the design 7/7 against a compartment stand-in at 5/7 and flat RAG at 3/7, with two sanity checks proving the scorer isn't rigged; `graphiti-core`, `honcho-ai` and `cognee` installed and their source read directly, which caught an overclaim in its own earlier draft; 60 unit tests. Three rounds of audit found six real bugs, including a matter-isolation bypass via a `str` subclass with a lying `__eq__` | [`OQ-009-v3`](dry-runs/OQ-009-v3) |
| **OQ-010** | Test at least three OCR candidates on a real hard legal document and publish a recommended pipeline, preprocessing included — concrete recipe over generic comparison | A tested comparison against two real documents: an 1827 handwritten probate bond from the Supreme Court of New South Wales, and page 3 of the *United States v. Manafort* sentencing memorandum, deliberately degraded (rotation, blur, noise, JPEG recompression) with a synthetic redaction bar to simulate what discovery actually delivers. Recommends routing by document type rather than picking one engine | [`OQ-010`](dry-runs/OQ-010) |
| | ↳ *re-run* | Different documents, harder: a 1755 Virginia land indenture from the Augusta County archive, and a FOIA production. RapidOCR, EasyOCR, PaddleOCR and a multimodal vision model, scored by character error rate. Classical engines came in above 80% CER on 18th-century cursive — functionally unusable — against roughly 15–21% for vision, which also flagged what it couldn't read instead of guessing | [`OQ-010-v2`](dry-runs/OQ-010-v2) |
| **OQ-026** | The methodology layer that should encode legal data before an LLM sees it — precedent relations, interpretive principles, authority weighting, doctrinal hierarchy — demonstrated on one bounded area of law | A schema for the layer above entity extraction, executed on contract ambiguity: the UCC §1-303 hierarchy, the canons of construction, and the genuine California/New York split on extrinsic evidence (*Pacific Gas & Electric* against *W.W.W. Assocs.*), where the same facts produce opposite rules. Then re-run with the identical schema on federal statutory interpretation — major questions, the overruling of *Chevron*, the rule of lenity — specifically to test whether it generalised rather than asserting that it did | [`OQ-026`](dry-runs/OQ-026) |
| **OQ-028** | Design a per-client "mini brain" MCP — what's ingested, permission model, refresh cadence, conflict-of-interest isolation, firm-wide interaction — and ship the schema plus one working endpoint | A SQLite schema, an MCP tool contract, and a working `query_client_brain` endpoint over real JSON-RPC stdio. The seed data encodes an adversarial scenario on purpose — two clients suing each other and a lawyer wrongly staffed on both — so the ethical wall is tested against a planted conflict rather than asserted. The executed test suite drives the real server subprocess, true-negative cases included | [`OQ-028`](dry-runs/OQ-028) |
| **OQ-040** | Build a prompt-injection tester for legal agents: threat model, 10+ cases across 3 attack classes, run against a vanilla Claude Code agent, report what got past | A harness attacking a real `claude` CLI agent — not a mock — deliberately left unhardened, in a throwaway sandbox, with success judged by inspecting the filesystem and transcript afterwards rather than by asking the model to grade itself. 15 cases; **1 got past**: a salami-slicing attack that extracts privileged material a harmless-looking slice at a time | [`OQ-040`](dry-runs/OQ-040) |
| | ↳ *re-run* | 18 cases across direct, indirect and multi-turn classes — spoofed managing partner, base64-smuggled instructions, fiction and roleplay jailbreaks. **0 got past.** The write-up argues against reading that as a clean bill of health, and the detector has its own unit tests, run before it was trusted against real transcripts | [`OQ-040-v2`](dry-runs/OQ-040-v2) |
| **OQ-112** | A messy native `.eml`/`.msg` corpus for testing document pipelines, since Enron is too clean: a feature checklist explaining why each breaks naive parsers, 15–30 files, and a harness | 22 messiness features documented with the parser failure each one causes, and 27 synthetic native files (24 `.eml`, 3 `.msg`) tagged to them, plus a harness that runs a real extraction task and grades it. Includes a from-scratch writer for the OLE compound-file format, built because no Python package can *write* `.msg` | [`OQ-112`](dry-runs/OQ-112) |
| | ↳ *re-run* | 28 files with hand-authored ground truth per file and a PASS/PARTIAL/FAIL scoring harness. The five `.msg` fixtures are generated through real Outlook COM automation rather than hand-rolled, so the binary format is genuinely native | [`OQ-112-v2`](dry-runs/OQ-112-v2) |
| **OQ-115** | A legal-task-aware model router: map legal task types to model tiers, layer in stakes, and stop subscription caps silently downgrading work that matters | A router classifying by task type and stakes, picking a model tier and a subscription lane with token headroom, forcing a verification pass on high-stakes output, and logging every decision to auditable JSONL. 43 unit tests, a 20-case classifier eval, three audit rounds. Its README names its own weakest claim up front: the real Anthropic backend was never round-tripped against the live API | [`OQ-115`](dry-runs/OQ-115) |
| | ↳ *re-run* | Scoped deliberately narrower — a dependency-free decision library and CLI making no live model calls at all, returning which model, why, and what caveats the lawyer should know before trusting the choice | [`OQ-115-v2`](dry-runs/OQ-115-v2) |
| **OQ-122** | Ship a working MCP server over real primary law — retrieval by citation plus a real structured query — solving currency, hierarchy and cross-references honestly rather than papering over them | An MCP server over 21 CFR Part 11 (electronic records and signatures), ingested live from the official eCFR API. Part 1 Subpart J is ingested alongside it specifically so the cross-references in §11.1(f) actually resolve, leaving an honest mix of resolved and out-of-scope citations instead of marking everything external | [`OQ-122`](dry-runs/OQ-122) |
| | ↳ *re-run* | 16 CFR Part 312 (the COPPA Rule) from eCFR, with its enabling statute 15 U.S.C. §§6501–6506 from GovInfo alongside it. Adds hierarchy browsing, full-text search, and cross-references in both directions — what a section cites, and what cites it | [`OQ-122-v2`](dry-runs/OQ-122-v2) |
| **OQ-130** | Turn an interactive HTML legal explainer into a per-client, access-controlled link that renders on mobile and can be revoked — proved on two real explainers, desktop and phone | An Express delivery layer where the token *is* the access control: admin routes to issue and revoke, `/d/:token` for the client, no login or account. Two genuinely interactive explainers to deliver — a liquidated-damages calculator and a six-clause memo with risk badges and collapsible commentary — plus an operator dashboard | [`OQ-130`](dry-runs/OQ-130) |


## Running the tests

```bash
cd tests && ./run_all.sh
```

The suite uses a stub in place of the real `claude` binary, so it runs without
network access or a live model.

A clean clone should go green. One test — `test_dry_run_check.sh` — reports
`SKIP` and exits 0 unless the baselines repository is checked out alongside
this one, since it exercises the dry-run driver that depends on it.

The suite takes a few minutes: several tests drive real subprocesses with
timeouts, backoff sleeps and process-group signals rather than mocking them.

## One change since submission

`submission/loop.sh` is otherwise exactly as filed, with a single fix.

Each invocation writes its stdout, stderr and a completion sentinel to files
whose paths were previously fixed:

```
/tmp/loop_<loop_num>_<attempt>.out   .err   .exit
```

The loop launches the call in the background and then polls for the `.exit`
sentinel to know the call has finished. Because those paths depend only on the
loop and attempt number, **two `loop.sh` runs on the same machine share them** —
so one run's sentinel can satisfy the other's poll, handing it a foreign exit
code and a foreign output file to parse. Predictable names in a world-writable
directory are also the classic insecure-temporary-file pattern (CWE-377): on a
shared host, another user can pre-create the path as a symlink and have the
script write through it.

It never bit during the assessment, because each question runs in its own
sandbox and nothing else is running `loop.sh`. It surfaced here, running the
test suite repeatedly on one laptop.

The fix is to give each run a private scratch directory:

```bash
RUN_TMP="$(mktemp -d "${TMPDIR:-/tmp}/loop.XXXXXXXXXX")"
trap cleanup_run_tmp EXIT
```

`mktemp -d` gives an unguessable name and 0700 permissions, and the directory
is removed on exit.

## Source material and licensing

The documents under `dry-runs/OQ-010*/documents/` are public-domain records
retrieved from public archives (a 1755 Virginia land indenture from the Augusta
County Circuit Court Archive, and a US federal FOIA production). Attribution and
provenance are recorded in that run's own README. Everything else under
`dry-runs/` was generated by the loop.

Personal email addresses have been replaced with `redacted@example.com`
throughout.
