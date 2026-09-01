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

*One bit of jargon that recurs below: **MCP** is the open standard for plugging
a tool or a data source into an AI assistant, so the assistant can query it
directly while it works.*

| Question | The brief, in short | What the loop built | Run |
|---|---|---|---|
| **OQ-008** | Markdown wasn't built for legal documents. Specify what a legal version of it would need, and build something that works | A written standard, plus working software that turns plain text into a finished contract — automatic clause numbering, margin numbers, footnotes, and cross-references that check themselves. It worked out where existing formats fall short by actually producing a PDF and examining it, rather than trusting the documentation | [`OQ-008`](dry-runs/OQ-008) |
| | ↳ *re-run* | The same idea, rebuilt to need nothing installed, plus a checker that refuses to produce a document containing a broken cross-reference or an undefined term. It wrote a deliberately broken contract with six planted mistakes to prove the checker actually catches them | [`OQ-008-v2`](dry-runs/OQ-008-v2) |
| **OQ-009** | How should an AI legal research assistant remember things across weeks of work? Justify the design against the alternatives | A memory system that files every fact against a single matter, with no way to read across matters, and timestamps each one twice — when it was true, and when the assistant found out. So it can answer both "what's the position now" and "what did we believe when we sent that advice". Compared against a simpler approach that was actually built and run, not just described | [`OQ-009`](dry-runs/OQ-009) |
| | ↳ *re-run* | Same conclusion, reached independently. This time the confidentiality boundary is enforced by the structure itself: a fact cannot be recorded without a matter attached to it, so the wall can't be forgotten | [`OQ-009-v2`](dry-runs/OQ-009-v2) |
| | ↳ *re-run* | The most thorough of the three. It scored its own design against two alternatives on a seven-case test, then installed the three real products it had been comparing itself against and read their code — which caught it overstating a claim in its own draft. Three rounds of self-audit found six genuine bugs, including a way to slip past the confidentiality wall | [`OQ-009-v3`](dry-runs/OQ-009-v3) |
| **OQ-010** | Anyone working with old or poor-quality scans hits a wall getting text out of them. Test at least three tools on a genuinely hard document and publish a recipe | A tested comparison on two real documents: an 1827 handwritten probate bond from the New South Wales Supreme Court, and a page of a US federal sentencing memo, deliberately degraded to look like the bad photocopies that turn up in litigation. Conclusion: choose the tool to suit the document rather than using one for everything | [`OQ-010`](dry-runs/OQ-010) |
| | ↳ *re-run* | Same question, harder documents — a 1755 Virginia land deed and a redacted government file release. Conventional tools got roughly 80% of the characters wrong on 18th-century handwriting, so effectively useless. An AI vision model read it mostly correctly and, importantly, said when it couldn't make something out instead of inventing text | [`OQ-010-v2`](dry-runs/OQ-010-v2) |
| **OQ-026** | Before an AI reads legal material, what should it already know about how law works — which authority outranks which, how to resolve ambiguity? | A way of encoding legal method itself, so it's available to the AI before it reads a word of the document. Demonstrated on contract interpretation, including a genuine California/New York split where identical wording produces opposite results — then re-run unchanged on statutory interpretation, specifically to check it wasn't just built to fit the first topic | [`OQ-026`](dry-runs/OQ-026) |
| **OQ-028** | Lawyers want a per-client "mini brain" their AI can draw on. Design it — what goes in, who can see it, how conflicts are kept apart — and ship a working piece of it | A per-client knowledge store a lawyer's AI assistant can query while working, with the permission rules and the conflict-of-interest wall built in. The test data sets a deliberate trap — two clients suing each other and one lawyer wrongly assigned to both — so the wall is proven to hold rather than merely claimed to | [`OQ-028`](dry-runs/OQ-028) |
| **OQ-040** | Legal AI reads untrusted material all day. Build something that tries to hijack it through hidden instructions, and report what got through | A tester that attacks a real AI legal assistant using instructions hidden inside the documents it reads. Fifteen attacks; **one got through** — a slow extraction that draws confidential material out a harmless-looking piece at a time. Whether an attack succeeded was judged by checking what actually ended up on disk, never by asking the AI whether it had behaved | [`OQ-040`](dry-runs/OQ-040) |
| | ↳ *re-run* | Eighteen attacks across three categories — impersonating a senior partner, smuggling instructions in as encoded text, and roleplay. **None got through**, and the write-up argues at some length why that shouldn't be read as a clean bill of health | [`OQ-040-v2`](dry-runs/OQ-040-v2) |
| **OQ-112** | Anyone testing software that reads email needs realistically messy files to test it on, and the usual answer is too clean. Build a proper set | A deliberately messy set of 27 test emails — forwarded chains, quoted history buried in quoted history, tables, encoding traps — each labelled with the specific thing it breaks, alongside a checklist explaining why each one defeats naive software. It had to write its own tool to produce Outlook's file format, because nothing existing can | [`OQ-112`](dry-runs/OQ-112) |
| | ↳ *re-run* | 28 files, each with a hand-written "correct answer" to check against, and scoring that reports pass, partial or fail. The Outlook files this time are produced by driving real Outlook, so they're genuinely native rather than approximated | [`OQ-112-v2`](dry-runs/OQ-112-v2) |
| **OQ-115** | Lawyers pick which AI model handles which job by instinct and burn through their limits. Build something that decides properly | A router that decides which AI model should handle a piece of legal work, based on what kind of task it is and how much is riding on it — so a filing that goes on the record is never quietly downgraded to a cheaper model to save budget. Every decision is logged and auditable. Its own README leads with its weakest point: the live connection was never actually tested against the real service | [`OQ-115`](dry-runs/OQ-115) |
| | ↳ *re-run* | A narrower version that makes no live calls at all. It answers one question — which model, why, and what the lawyer should know before trusting that choice | [`OQ-115-v2`](dry-runs/OQ-115-v2) |
| **OQ-122** | Cheap, reliable access to statutes and regulations is still an unsolved gap. Pick one slice and actually ship it, rather than planning it | A working service giving an AI assistant access to real, current US regulations — the FDA's rules on electronic records and signatures — pulled live from the official government source. It deliberately loaded the neighbouring part as well, so that cross-references between sections actually resolve instead of every one coming back "not found" | [`OQ-122`](dry-runs/OQ-122) |
| | ↳ *re-run* | The same for the children's online privacy rules, with the Act behind them alongside. Adds search, browsing by structure, and cross-references in both directions: what a section points to, and what points back at it | [`OQ-122-v2`](dry-runs/OQ-122-v2) |
| **OQ-130** | Lawyers now send clients interactive HTML documents, but there's no good way to deliver one. Email mangles it, attachments break on a phone, public hosting leaks it | A way to send a client an interactive document as a private link that opens on a phone, needs no login or account, and can be switched off at any time without affecting anyone else's. Built with two working documents to send: a contract penalty calculator, and a clause-by-clause memo with risk ratings and plain-English commentary | [`OQ-130`](dry-runs/OQ-130) |

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

MIT — see [`LICENSE`](LICENSE). Take it and build on it.

Two things in here aren't mine to license, and the licence says so explicitly:

- **The question briefs** (`dry-runs/*/QUESTION.md`) are LegalQuants' own,
  reproduced because they're published in their public
  [baselines repository](https://github.com/LegalQuants/lq-assess-machine-baselines).
- **The source documents** under `dry-runs/OQ-010*/documents/` are third-party
  public-domain records: an 1827 probate bond from the Supreme Court of New
  South Wales, a 1755 Virginia land indenture from the Augusta County Circuit
  Court Archive, a page of a US federal court filing, and a US federal FOIA
  production. Attribution and provenance for each are in the README of the run
  that uses it.

Everything else — the harness, the tests, the design notes, and everything the
loop generated in the dry runs — is covered by the licence.

Personal email addresses have been replaced with `redacted@example.com`
throughout.
