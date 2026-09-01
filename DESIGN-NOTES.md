# Round 2 submission — loop design notes

*Supplementary note from Andrew Gray (ALGray01), sent alongside the
required `round2-submission.zip` and `ENTRY.md` — not itself part of the
graded artifact.*

## What this is

A short account of the loop's design, the reasoning behind it, and what
local testing actually surfaced — offered so the design intent is legible
without having to reconstruct it from ten separate transcripts.

## Architecture

The loop runs FULL CONTROL: `loop.sh` drives the `claude` CLI directly, one
continuous session per question. It tracks remaining turn budget itself
and switches between two phases:

- **Build**: open-ended work toward the strongest submission the budget
  allows, per the coached starter-kit wording (honest limitations, budget
  accordingly, verify before the cutoff).
- **Reserve**: entered once remaining turns drop below a computed
  threshold. Here the loop stabilizes what's built, then dispatches three
  parallel subagents that all share one underlying mandate — find the
  single most examination-averse claim in what's shipped and verify it
  against actual execution, not by reading — with a distinct specific lens
  each on top of that shared mandate: one attacking every security-relevant
  surface with crafted input, one hunting specifically for hollow or
  circular verification (a test that would pass regardless of whether the
  logic under it actually works), and one building a genuinely naive/boring
  alternative to whatever the strongest implicit "this is the right
  approach" claim is, whether or not the brief asked for a comparison.
  Findings get fixed by severity and re-verified by actually re-running the
  fix, not just re-reading the diff. A second audit round runs if enough
  budget remains.

Before any of that, the reserve phase drafts and commits an honest
self-assessment — what was actually verified versus assumed, the single
weakest claim in what's shipped, the most consequential design decision
and the alternative it beat, and what the next 30 minutes would be spent
on — immediately, rather than at the very end. That ordering turned out to
matter (see below).

Every commit is made under a generic, non-identifying local git identity
that gets set unconditionally at the start of each session, so the
published history never carries anything beyond what the loop itself
produced.

## Why these choices

Turn budget is a hard resource that runs out with no warning, so the two
design pressures that mattered most were: never let a mid-action cutoff
leave the repository incoherent, and never let the most examination-averse
part of the submission go unchecked just because it happened to run late.
The audit is still, fundamentally, one general "review this critically and
verify by execution" mandate — the same instinct behind any adversarial
self-review — just run three times in parallel through three different
lenses instead of once in the abstract. A single generalist pass tends to
default to whatever's easiest to check; giving the same underlying mandate
a specific angle each time — only attacking, only hunting for circular
verification, only building a real comparison — kept each pass going after
the specific thing a broader, undirected version of the same instruction
would have been most likely to skip.

## What testing actually surfaced

Before finalizing, the loop was run for real — at real cost, against the
same ten open questions this assessment targets, which the rules
explicitly permit for local testing — well over a dozen times, iterating
on what those runs actually showed rather than on assumption. Two findings
from that process are worth being upfront about:

- The `claude` CLI's own `--max-turns` enforcement reliably reports one
  more completed turn than the cap it was given when a call is genuinely
  cut off at that limit — a real, consistent reporting quirk, not an
  actual overspend. Left uncorrected, it could push the loop's own
  cumulative turn count one over budget on a run's very last call. Once
  found, the reserve-phase turn accounting was adjusted specifically to
  cancel it.
- Giving the audit three parallel, independently-scoped passes instead of
  one meant it did more real work per reserve turn — which occasionally
  meant it competed for the same fixed window as the final self-assessment
  write-up. The fix was structural rather than best-effort: draft that
  write-up immediately, before the audit even starts, so a late cutoff can
  only cost it some polish, never its existence.

Both were real, observed problems, not hypothetical ones, and both were
fixed and re-validated against further real runs before this submission
was finalized.

## What it's aiming for

The loop treats self-verification as load-bearing rather than a formality:
a claim that something works is expected to be backed by actually running
it, and a claim that one approach beats another is expected to be backed
by an actual, executed comparison — including the boring alternative built
specifically to test that claim, even where the brief didn't ask for one.
The same scrutiny is applied to the loop's own test and grading logic, on
the view that a check which is wrong in its own favor is invisible unless
something specifically goes looking for it.
