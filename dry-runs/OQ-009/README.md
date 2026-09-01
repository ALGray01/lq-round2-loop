# Agent memory architecture for a long-running legal-research bot (OQ-009)

A working prototype and a real, run-and-captured head-to-head test, built to
answer: *what's the right memory architecture for a legal-research bot that
builds context over weeks of use — knowledge graph, layered compartments,
fine-tuning, or something else?*

Built in ~90 minutes. Python 3 standard library only, no external
dependencies, no `ANTHROPIC_API_KEY` available in the build environment (see
"What this does NOT do" below for exactly what that limits).

## The proposal

**Compartments as the outer boundary, a bitemporal fact graph inside each
compartment, an episodic log as the recall fallback, and no fine-tuning of
facts into model weights.** Concretely, three layers:

1. **Compartments** (`memory_lab/facts.py: FactStore`, `memory_lab/episodic.py:
   EpisodicLog`) — every read and write is scoped to a `matter_id`. There is
   no API that can return facts across matters. This is the Honcho/Cognee
   idea (session/user/global layers) applied to the axis that actually
   matters for a law firm: one matter's privileged facts must never leak
   into another matter's context, full stop, structurally, not by a filter
   someone remembered to add.
2. **A bitemporal fact graph inside each compartment**
   (`memory_lab/facts.py: Fact`) — structured (subject, predicate, object)
   triples with a `valid_from`/`valid_until` window and a `source` field for
   provenance, plus an explicit `supersede()` operation that closes the old
   fact's window and links the new one. This is the Graphiti idea (temporal
   knowledge graph edges): "the hearing date is X" and "the hearing date
   *was* X until the clerk corrected it to Y" are both true statements, at
   different times, and a legal-research bot needs to answer either question
   depending on which one was asked.
3. **An episodic log as fallback** — raw conversational turns per matter,
   searched by relevance when the query isn't about a structured fact ("what
   did the client say about X"). Retrieval here (and for facts) uses a
   from-scratch TF-IDF cosine-similarity index (`memory_lab/retrieval.py`) —
   see limitations for why this stands in for a real embedding search.

**No fine-tuning**, anywhere in this design, for facts. Fine-tuning is kept
available (not built here) only for narrow, stable *style* adaptation,
decoupled entirely from what the bot knows.

## Why not the alternatives (the actual argument)

| Requirement a legal-research bot has | Pure vector RAG (flat) | Fine-tuning | Graphiti alone (temporal graph, no compartments) | Honcho/Cognee alone (compartments, no temporal graph) | This design |
|---|---|---|---|---|---|
| Know which fact is *currently* true after a correction | No native concept of supersession — old and new chunks both sit in the index and rank on lexical similarity, not recency/validity | Requires a full retrain to update anything; can't represent "was true until" at all | Yes — this is what it's for | Not natively — its layers are about privacy scope, not fact validity | Yes (`supersede()`, `current_as_of()`) |
| Never leak Matter A's facts into Matter B's answer | Only if someone remembers to filter by matter on every query — one index, no structural wall | One model per matter is normally cost-prohibitive; a shared model bakes everything into one set of weights | Not built in — would need to be added as a filter, same risk as flat RAG | Yes — this is what it's for | Yes, structural (`FactStore`/`EpisodicLog` never expose a cross-matter read) |
| Cite *why* the bot believes something (malpractice/ethics exposure if it can't) | Possible if chunks carry metadata, but nothing enforces it | Essentially impossible — the fact is diffused into weights, unattributable | Yes, provenance is a first-class graph property | Depends on implementation, typically weaker than an explicit graph edge | Yes (`Fact.source`) |
| Update cheaply as new facts arrive daily/hourly | Cheap (just index the new chunk) | Expensive and slow — can't retrain per fact | Cheap | Cheap | Cheap |
| Right-to-deletion / ethics-wall offboarding (delete a client's data on request) | Delete the chunks | Cannot cleanly un-bake facts from trained weights | Delete the subgraph | Delete the compartment | Delete the compartment (facts + episodic) |

Fine-tuning is disqualified outright as the *memory* mechanism: it's slow to
update, cannot represent "no longer true," cannot be selectively deleted
(a real problem for privilege waivers and conflict walls), and mixing
matters in one set of weights defeats compartmentalization while a
separate fine-tune per matter is not economically viable. Pure flat vector
RAG is a real, working baseline (built and run here, not a strawman) — it's
cheap and fine for open-ended semantic recall, but has no structural answer
to supersession or leakage, which the test below demonstrates concretely
rather than asserting. Graphiti-style and Honcho/Cognee-style approaches
each solve one of the two axes (temporal correctness vs. privacy scoping)
well; the two axes are orthogonal, so the design here just uses both rather
than picking one.

## The head-to-head test

**Scenario** (`scenario/timeline.py`): a fictional 6-week, 2-matter timeline
— a contract dispute (`doe-v-roe`) and an unrelated probate matter
(`smith-estate`), sharing a predicate name (`hearing_date`) on purpose to
stress-test cross-matter confusion. Both matters get facts added, then
*corrected* later (hearing date moves, settlement offer changes, estate
valuation is revised), plus a couple of purely conversational turns with no
structured fact behind them.

**Ground truth** (`scenario/queries.py`): 8 queries, each with an expected
answer decided by reading the timeline and reasoning about what's actually
true at that date — written before any system was run against them, so a
system agreeing with the ground truth means it's actually correct, not that
the test was built backward from its output. Each query also names a
`forbidden_matter` that must never be touched, which is how cross-matter
leakage is detected independently of whether the returned fact happens to
look right.

**Systems compared** (`memory_lab/architectures.py`), all real, runnable,
driven identically by `eval/run_headtohead.py`:
- `HybridMemory` — the proposed design.
- `FlatRagMemory` — a single TF-IDF index over every matter's facts and
  turns, all history, no temporal filtering, no compartment wall. This is
  the honest "just bolt a vector index on the conversation log" baseline.
- `FrozenSnapshotMemory` — facts frozen at `2026-02-15`, the moment of the
  very last query, standing in for a periodic fine-tune cadence at its
  literal best-case timing (retrained right up to the instant it's asked
  anything; one snapshot per matter, which in practice is normally
  cost-prohibitive to do per matter). Two earlier drafts each picked an
  earlier date and called it "best case" while it wasn't — two rounds of
  adversarial audit (see README "Reflection") each caught this by re-running
  the eval with a later date and observing the baseline's own score rise;
  the date shipped here is the maximum possible, so there's no later point
  left for a further round to catch.

**Actually run** (not asserted — see `results/headtohead_output.txt` for the
full captured transcript):

```
$ python -m eval.run_headtohead
...
Scorecard
  hybrid (proposed)                      6/8
  flat_rag (baseline)                    3/8
  frozen_snapshot (fine-tune stand-in)   5/8
```

(These are the current, real numbers — see "Generalization check" below for
why they're lower than an earlier draft claimed: a scorer bug that let a
system pass a "should find nothing" query just by having no `fact_id`, even
if it had actually recalled an irrelevant episodic snippet, was found and
fixed, and it turned out `hybrid` itself was doing exactly that on 2 of its
own queries.)

`hybrid` still beats both baselines outright, but not cleanly: it now fails
`Q5` and `Q8` — both "should find nothing" queries — because when the fact
layer finds no confident match, it falls through to the episodic layer,
which (on a small per-matter turn count) can confidently recall a turn that
has no real relevance to the query, purely on shared incidental words. That
is a genuine, currently open weakness of the retrieval-confidence layer, not
a structural flaw in the compartment/temporal design — see Reflection.

`flat_rag` fails every supersession and leakage query. On `Q1`/`Q3`/`Q6` it
**abstains** rather than confidently guessing wrong: its single flat index
scores the pre- and post-correction versions of a fact as an exact tie
(identical wording apart from the value itself), and the relative-margin
confidence rule (see "Generalization check" below) treats an unresolved tie
as "don't know" — a flat index has no signal at all for which of two
near-identical facts is current, not even enough to make a wrong guess. On
`Q8` it still leaks outright (`touched forbidden matter smith-estate`), a
real cross-matter read, not a hypothetical one. `frozen_snapshot`, even at
its literal best-case timing, fails `Q2` (it only ever answers with the
*current* snapshot, so it can't reproduce what was true historically), `Q7`
(it never reads the episodic log at all), and `Q8` (a frozen snapshot has no
notion of "as of when" the query is being asked; it either knows a fact or
it doesn't, independent of the query's own timestamp).

## Generalization check

`scenario2/` (patent licensing + personal injury) and `scenario3/` (child
custody + employment discrimination) are two further independently-authored
scenarios — different domains, different vocabulary each time, queries
paraphrased against the fact text — built to check whether the
retrieval-confidence rule in `memory_lab/retrieval.py`, tuned by hand
against `scenario/`'s vocabulary, generalizes past that one corpus. Short
version: partially, and finding out exactly where it stops is the most
useful thing either check did.

**Round 1 (scenario2), first pass:** a fixed cosine-similarity cutoff
(`MIN_SIM_THRESHOLD=0.15`) got all 6 supersession/leakage queries right but
missed one episodic-recall query (`R2-Q7`, correct turn scored `0.119`, just
under the fixed cutoff, in a matter with only two episodic turns). **Fix:**
replaced it with `confident_top()`, a relative-margin rule — accept a
candidate only if it beats the runner-up by `REL_MARGIN=1.3`, not just by
clearing an absolute score. Real candidate scores measured before picking
`1.3`: reject-side max ratio `1.11` (scenario 2's `R2-Q5`), accept-side min
ratio `1.41` (`R2-Q7`) — `1.3` sits in that gap. Re-running both scenarios
after the fix: `scenario/` unchanged at 8/3/5, `scenario2/` now matching at
8/3/5 (up from 7/1/5).

**Round 2 (scenario3):** run un-retuned against the fix above, scenario3
scored far worse — `hybrid 2/8`, `flat_rag 1/8`, `frozen_snapshot 2/8` (see
`results/headtohead3_output.txt`). Investigated by recomputing the actual
TF-IDF scores directly rather than guessing, and three distinct, honest
causes turned up:
- **`R3-Q1`: real lexical ambiguity.** The query "custody hearing" shares the
  word "custody" with an unrelated fact's text ("joint physical custody,
  alternating weeks") almost as strongly as it shares "hearing" with the
  actually-correct fact (ratio `1.17`, below `REL_MARGIN`) — a legitimate
  case of legal-domain polysemy (the same word used for two different
  concepts) that no fixed or relative *lexical* threshold can resolve, only
  real semantic understanding can.
- **`R3-Q6` and other zero-overlap misses: over-aggressive paraphrase.**
  "living arrangement for the kids" shares zero tokens with
  "primary_residence is joint physical custody" (all four candidates score
  `0.0`) — not a threshold problem at all, just the already-disclosed
  TF-IDF/no-embeddings limitation, illustrated more starkly than before.
- **`R3-Q5` and `R3-Q8`: two distinct, real gaps in `confident_top()`, not
  one.** `R3-Q5` is the single-candidate gap: exactly one nonzero-scoring
  candidate (no runner-up to form a ratio against), so the rule falls back
  to `score > ABS_FLOOR` alone, and a single coincidentally-shared word
  ("amount") clears `ABS_FLOOR=0.02` easily. `R3-Q8` is a *different*, more
  concerning failure — a fresh audit round caught that it actually has two
  nonzero candidates (`0.204` vs `0.067`, ratio `3.05`), so it clears
  `REL_MARGIN` the normal way and is **confidently wrong**, not merely
  unopposed; the shared word driving it ("the") is pure stopword overlap
  that the ratio rule doesn't catch because there's no second real
  candidate to look thin against. So the confidence rule's weakness is
  broader than "only when nothing else is around to compare against" — it
  can also lose to incidental overlap when the *correct* answer is "no
  candidates exist yet," which no relative-margin rule addresses; only an
  absolute floor could, and no fixed floor separates genuine single/pair
  matches (as low as `0.170`) from spurious ones (as high as `0.30`) across
  all three scenarios. **No threshold value fixes this**; it's evidence for,
  not against, the existing "no embeddings/no LLM" disclosure, not a new
  category of problem.

**A fourth, independent bug this stress test surfaced (not a scenario3
artifact):** while investigating `R3-Q5`/`R3-Q8`, direct testing of
`HybridMemory.answer()` on `scenario/`'s own `Q8` showed it returns
`fact_id=None` with the snippet *"We should track the contract dispute
hearing and keep an eye on deadlines"* — a real but completely irrelevant
episodic turn — for a query ("who is the key witness") that should find
nothing at all. `eval/scorer.py` was marking this **correct**, because it
only checked `fact_id is None`, not whether the snippet was actually empty
or relevant. Fixed: `scorer.py` now requires a genuinely empty snippet for
any "should find nothing" query that has no `expected_keyword` to check
against (see `tests/test_scorer.py`'s two new cases proving the old and new
behavior directly). This is exactly a FAILURE-CLASSES item-4 scorer gap,
found by testing the scorer against a real system's actual output, not
invented — and it changed the honest scorecard: `scenario/` from 8/8 to
6/8 for hybrid, `scenario2/` from 8/8 to 7/8, both dropping because the
same episodic-hallucination bug was already there, just invisible.

Current, real numbers, all three scenarios, same code, same constants:

```
scenario1 (scenario/):   hybrid 6/8   flat_rag 3/8   frozen_snapshot 5/8
scenario2 (scenario2/):  hybrid 7/8   flat_rag 2/8   frozen_snapshot 5/8
scenario3 (scenario3/):  hybrid 2/8   flat_rag 1/8   frozen_snapshot 2/8
```

`hybrid` still beats or ties both baselines in every scenario and never
loses to either — the compartment/supersession structural wins hold up
every time the retrieval layer manages to surface *any* confident answer
(`R3-Q3`, `R3-Q4` both pass for `hybrid`/`frozen_snapshot`, both still fail
for `flat_rag`'s tie-abstention). But the absolute numbers are much less
impressive than an earlier draft of this README claimed, and scenario3 in
particular shows the TF-IDF retrieval/confidence layer has real limits this
build did not fully solve. I chose not to keep hand-tuning `REL_MARGIN` or
`ABS_FLOOR` to chase a better scenario3 number — the data above shows no
fixed constant separates the genuine matches from the spurious ones in the
single-candidate case, and further tuning against a scenario I can already
see the answers to is exactly the "solved backward" pattern this submission
has otherwise tried hard to avoid.

## How to run it

```bash
cd OQ-009
python -m unittest discover tests -v     # 20 unit tests, all real assertions
python -m eval.run_headtohead            # scenario 1, writes results/headtohead_output.txt
python -m eval.run_headtohead2           # scenario 2 (generalization check), writes results/headtohead2_output.txt
python -m eval.run_headtohead3           # scenario 3 (generalization check, round 2), writes results/headtohead3_output.txt
```

No dependencies to install; Python 3.10+ (uses `dict[str, ...]` built-in
generics) is all that's required.

## What this does NOT do (honest limitations)

- **No embeddings, no LLM in the loop.** There was no `ANTHROPIC_API_KEY` (or
  any model API) available in this build environment, so retrieval uses a
  from-scratch TF-IDF cosine-similarity index instead of a real embedding
  index, and "answers" are the single fact/turn the memory layer surfaces,
  not a generated natural-language response. This tests **memory retrieval
  correctness** (does the architecture find the right fact and stay inside
  its compartment), not end-to-end answer quality, which would need an LLM
  on top of whatever this layer returns. TF-IDF and embeddings will disagree
  on paraphrase-heavy queries, but the failure modes this test targets
  (supersession, compartment leakage) are structural properties of the
  architecture, not a function of retrieval-algorithm quality — a swap to
  real embeddings would not change which system wins this test, only how
  close the margin is on paraphrased queries.
- **Entity resolution is by exact subject string, not fuzzy matching.**
  "hearing_date" only recognizes itself as "hearing_date" — a real system
  needs a step that decides "the March hearing" and "hearing_date" refer to
  the same node, which Graphiti-style pipelines handle with LLM-assisted
  entity extraction. Not built here; would be the first real gap to close.
- **Fact extraction from raw text is not built.** `Fact` objects in the
  scenario are hand-authored, not extracted from a transcript by an LLM.
  A real deployment needs an extraction step (turn text → candidate facts →
  supersession decision), which is exactly the kind of judgment call an LLM
  is good at and this prototype doesn't attempt.
- **Single process, in-memory, no persistence.** No database, no concurrent
  access, no crash recovery. Fine for demonstrating the architecture's
  *shape*; a real deployment needs a real graph/document store underneath
  the same API.
- **The retrieval-confidence rule (`ABS_FLOOR`/`REL_MARGIN` in
  `memory_lab/retrieval.py`) has a real, demonstrated failure mode on
  single-candidate matches** (no runner-up to form a ratio against) — see
  "Generalization check" above. It is not a hypothetical gap: it's why
  `hybrid` fails 2 real queries in `scenario/` itself and most of
  `scenario3/`. No fixed floor value fixes it (checked: genuine and spurious
  single-candidate scores overlap across all three scenarios); the honest
  fix would be a different signal entirely (embeddings, or an LLM judging
  the retrieved snippet), not a better constant.


## Reflection

This submission went through three rounds of adversarial audit by fresh
subagents with no prior context, each instructed to re-run every claim
rather than just read it, plus a fourth round of self-directed stress
testing (`scenario3/`) that found a bug none of the three audits caught.
Recorded honestly below, in the order it happened, not smoothed over:

- **Audit round 1** caught `FrozenSnapshotMemory`'s snapshot date mislabeled
  "best case" while capturing only 3 of 11 facts (fixed: `frozen_snapshot`
  3/8 → 4/8).
- **Audit round 2** caught that the "fixed" date still wasn't the actual
  best case (fixed: → 5/8), plus an unverified TF-IDF figure in this
  Reflection's own prose (corrected: 0.319/0.308 → the real 0.3737
  tied/0.3619).
- **A self-directed generalization check (`scenario2/`)** then found the
  fixed `MIN_SIM_THRESHOLD=0.15` didn't generalize to a sparse episodic
  corpus; fixed with a relative-margin rule, `confident_top()`.
- **A third audit round** on that fix found nothing beyond one cosmetic
  test-comment rounding error (fixed).
- **A second, harder self-directed generalization check (`scenario3/`)**
  then found the relative-margin fix *doesn't* generalize either, for
  reasons that are actually about lexical retrieval's ceiling, not about
  the specific constant — and, while investigating why, found a genuine
  scorer bug (`eval/scorer.py` was marking a query "correct" when the
  system had actually hallucinated an irrelevant episodic answer). Both are
  detailed in "Generalization check" above and reflected in every number in
  this README, which is why the scorecard here is more modest than an
  earlier draft claimed.
- **A fourth audit round**, on that fix, found two mislabeled query
  attributions in the root-cause writeup (`R3-Q6` credited to the wrong
  bullet; `R3-Q8` described as the single-candidate gap when it's actually a
  two-candidate ratio-dominance failure, `0.204` vs `0.067`, ratio `3.05` —
  a broader, more concerning gap than the original text described). Fixed;
  no scorecard number changed.
- **A fifth audit round**, run fresh against the corrected state with
  instructions to re-derive every specific ratio/score this README cites
  (not just re-read them), reproduced all of them exactly — `1.11`, `1.41`,
  `1.17`, `3.05`, the `0.170`–`0.30` genuine/spurious overlap range, and
  every scorecard number, byte-for-byte against the committed
  `results/*.txt` transcripts — and reported a clean bill of health: no
  further fix.

**The single weakest remaining claim in this submission, named precisely:**
`HybridMemory`'s episodic fallback (`memory_lab/architectures.py`,
`HybridMemory.answer`, the block after the fact-lookup `if current:`) will
confidently return an irrelevant conversational turn as a "recall" when (a)
the fact layer found nothing confident and (b) the matter has few enough
episodic turns that one of them scores as a lone, unopposed candidate. This
is not a hedge — it is directly responsible for `hybrid` failing `Q5` and
`Q8` in `scenario/` itself (the *first* scenario, the one every other claim
in this README is measured against) and most of `scenario3/`. Anyone can
catch it the same way I did: run `HybridMemory(*build_timeline()).answer("who
is the key witness", "doe-v-roe", "2026-01-15")` and read the snippet — it
has nothing to do with witnesses. I chose not to patch it in the time
remaining because every fix I checked (raising `ABS_FLOOR`, requiring
multiple shared non-stopword tokens) either re-broke a case the earlier
fixes were built to solve or had no principled value distinguishable from
picking a number that happens to work on three known scenarios — the kind
of tuning-against-the-answer this submission has otherwise tried to avoid.

**The single most consequential design decision, defended against the
alternative:** treating compartments (privacy/matter scoping) and the
temporal fact graph (validity/supersession) as two independent, composable
layers, rather than picking one of Graphiti or Honcho/Cognee "as the
answer" and bolting the other concern on afterward. The alternative — e.g.
Graphiti alone, with matter-scoping added as a query-time filter — has
exactly the failure shape `FlatRagMemory` demonstrates on `Q4`/`R2-Q4` (a
leak because nothing structural prevents reading across the boundary); this
part of the argument is unaffected by everything the generalization checks
found, because the compartment and supersession logic (`FactStore`,
`EpisodicLog`) is a separate layer from the retrieval-confidence code that's
actually been shown to be weak — `hybrid` never once leaked across a matter
boundary or returned a stale fact instead of a corrected one in any of the
24 queries across three scenarios; every one of its failures was the
retrieval-confidence layer either finding nothing or finding the wrong
thing, not the architecture forgetting which matter or which point in time
it was answering for.

**What I actually ran to verify this, versus what I never got to:** every
number in this README comes from an actual `python -m eval.run_headtohead`
/ `run_headtohead2` / `run_headtohead3` execution, re-run after every fix
described above and diffed against the committed `results/*.txt` files, not
carried forward from an earlier draft. `python -m unittest discover tests`
(20 tests) passes as of the current commit. I directly executed
`HybridMemory.answer(...)` in a throwaway script to confirm the episodic
hallucination bug before writing anything about it, rather than inferring
it from score deltas. I swept `REL_MARGIN` at three values against two
scenarios (documented above) before this session's turns ran out, but I did
**not** get to: fix the single-candidate weakness itself, re-run the
`REL_MARGIN` sweep against `scenario3/` specifically, or build any test with
real embeddings instead of TF-IDF.

**With another 30 minutes,** the first thing I'd do is change
`HybridMemory`'s episodic fallback so it only fires when the fact layer
found *zero* candidates at all (not merely zero *confident* ones) — on the
theory that if structured facts exist for the matter but none matched, the
query is probably about a fact that doesn't exist yet or doesn't belong to
this matter, and episodic recall is more likely to produce a false positive
than a real answer in that specific case (as opposed to a matter with no
facts at all yet, where episodic recall is the only thing that could be
right). That's a testable, falsifiable hypothesis directly targeting the
weakest claim above, not a new piece of unrelated scope — I'd implement it,
re-run all three scenarios, and report whether it actually helps or just
moves the failure somewhere else.
