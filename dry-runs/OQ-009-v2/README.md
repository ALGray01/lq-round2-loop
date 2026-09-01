# OQ-009: Memory architecture for a long-running legal-research agent

**Question:** Long-running legal-AI agents need memory. Knowledge graph
(Graphiti), layered compartments (Honcho/Cognee), fine-tuning, or something
else entirely — what's the right architecture for a legal-research bot that
builds context over weeks of use?

## Recommendation

A **bi-temporal, matter-partitioned fact graph over a preserved episodic
log** — architecturally closest to Graphiti, adapted to the two things that
are non-negotiable in legal work and that neither "layered compartments"
memory nor fine-tuning is built around:

1. **Point-in-time correctness.** Law changes underneath a running matter:
   statutes get amended, precedents get overturned, facts get corrected. The
   agent needs to answer both "what's true now" and "what did we believe
   three weeks ago, before we knew better" — the second question matters
   because a lawyer needs to know whether an earlier memo, argument, or
   filing was reasonable *at the time it was made*. That requires two
   independent timestamps per fact: when it was true in the world (valid
   time) and when the agent learned it (transaction time). This is exactly
   Graphiti's bi-temporal edge model; it is not something a session-summary
   or layered-persona memory (Honcho/Cognee) is designed to track, and it is
   actively destroyed by fine-tuning, which collapses "what we now believe"
   into weights with no record of when the belief changed or what it
   replaced.

2. **Confidentiality boundaries that must hold structurally, not by
   convention.** A legal-research agent will accumulate multiple clients'
   matters in the same long-running memory. An ethical wall between two
   matters cannot depend on every write path remembering to apply a filter —
   it has to be a property of the schema. Making `matter_id` a required,
   non-nullable field on every stored fact (enforced at construction, not
   just checked at query time) means a fact literally cannot be written
   without a matter to attach it to. A flat vector store's isolation, by
   contrast, is usually a metadata filter applied *at query time* — which
   fails the moment a chunk of text was never tagged, or a caller forgets to
   pass the filter. Both are ordinary, unglamorous bugs, and both are tested
   for below (T6, T7).

The design is not a pure knowledge graph, though. Two additions matter for
a legal use case specifically:

- **The raw episodic log (session transcripts) is kept verbatim and never
  discarded**, and every extracted fact carries a `source_session` pointer
  back into it. Graph extraction is lossy by construction — a lawyer citing
  the agent's memory needs to pull the actual sentence a fact came from, not
  trust a paraphrase. The graph is an index into the transcripts, not a
  replacement for them.
- **No fine-tuning of the base model on matter content, ever.** Legal facts
  are exactly the kind of high-volatility, high-stakes, must-be-forgettable
  information fine-tuning is worst at: it can't be updated same-day when a
  statute changes, it can't cite its source, it can't be scoped per client
  (a fine-tune trained on Matter A's facts has no way to un-know them for a
  Matter B session — the opposite of an ethical wall), and it can't be
  audited by opposing counsel or a judge the way "here is the transcript
  this came from" can. The only place fine-tuning has a legitimate role here
  is stable, non-factual behavior — output formatting, citation style,
  house tone — never case facts or legal conclusions.

## Why not the alternatives, specifically

**Graphiti as-is (pure knowledge graph, no episodic layer):** gets the
bi-temporal reasoning right but, used alone, tends to store only the
extracted triples and discard or de-prioritize the source text. For a legal
user, "the agent says X" is worthless without "here is where that came
from, verify it yourself" — hallucinated or mis-extracted relationships are
a much bigger liability in this domain than in Graphiti's original
consumer/assistant use case. Keeping the full transcript addressable is the
one addition on top of a Graphiti-style graph that this design insists on.

**Honcho/Cognee-style layered compartments:** these architectures split
memory into layers optimized for *modeling the user* — preferences,
personality, working vs. long-term recall — which is the right shape for a
companion or tutoring agent that needs to build a theory of mind about one
person over time. A legal-research bot's hard problem isn't modeling the
attorney's preferences (though a thin layer of that is still useful for
style/verbosity); it's modeling *the matter's facts* and their validity
over time, plus keeping matters walled off from each other. Layered
compartments have no native notion of "this fact was superseded on this
date but was believed true before that" — they keep a current layer, not a
versioned history of layers. This is not just argued in prose: the eval
below includes a third system, `CompartmentMemoryStore`, built to be as
fair a stand-in for this family as the flat baseline is for naive RAG — it
reuses the graph's own matter partition (isolation is not the axis this
family is weak on) but its `query()` method has no `as_of` parameter at
all, because a layered-compartment design has no prior layer to query
against once the current one is updated. It scores 5/7: it matches the
graph on isolation (T6, T7) and on every current-state question (T1, T3,
T5), and fails on exactly the two point-in-time questions (T2, T4) —
which is the empirical version of the claim in this paragraph, not just an
assertion of it.

**Fine-tuning:** fails on recency (weekly/daily changing case law vs. a
retrain cycle), auditability (a judge or opposing counsel cannot be shown
"the weights," only a citation-backed answer), per-client isolation (no
clean way to "forget" one client's facts when serving another without
separate fine-tunes per client, which is its own confidentiality and cost
disaster), and correction (a wrong fact baked into weights has no
transaction-time undo the way invalidating a graph edge does). It is the
wrong tool for volatile, must-be-provable, must-be-partitioned knowledge —
which describes essentially everything a legal-research memory needs to
hold.

## What was actually built

Not just the proposal — a runnable, pure-Python (stdlib only, no
network/install dependency) implementation of the proposed design and two
realistic alternatives, plus a head-to-head evaluation, so the claims above
are checked against actual execution rather than argued from first
principles alone.

```
legal_memory/
  scenario.py           synthetic 12-session, 2-matter, 7-week research history
                        with scripted fact evolution (see below)
  graph_store.py        proposed design: bi-temporal, matter-partitioned fact store
  compartment_store.py  stand-in for Honcho/Cognee-style layered compartments:
                        same matter partition as the graph, but no as_of
                        parameter exists in its API at all -- current layer only
  vector_baseline.py    stand-in for naive flat RAG: TF-IDF/cosine over raw
                        session transcripts, with a fair-shot matter filter
                        and a recency-biased variant (the obvious naive fix
                        for "no temporal reasoning")
  textsim.py             TF-IDF cosine similarity, shared verbatim by all
                         three systems so the comparison isolates memory
                         *structure*, not ranking-algorithm quality
  eval_harness.py        7 test cases + scorer + two scorer sanity checks
  benchmark.py           measures actual query/build latency vs. corpus size
  extractor.py           supplementary experiment: non-LLM heuristic transcript
                         -> fact extraction (see below); not part of the core eval
results/eval_output.txt  actual captured output of the last run
tests/                   34 pytest unit tests: bi-temporal boundary
                         semantics, matter partitioning, baseline
                         tie-breaking, and extractor structural guarantees
                         (independent of the scenario-level eval)
```

Run it yourself:

```
python -m legal_memory.eval_harness   # the head-to-head comparison
python -m pytest tests/ -q            # 34 unit tests, all passing
python -m legal_memory.benchmark      # scale measurements (see Limitations)
```

### The scenario

Two matters run in parallel over 12 sessions / ~7 weeks:

- **Doe v. Acme** (contract dispute): starts with a 4-year statute of
  limitations under the (fictional) state commercial code; the defendant's
  name is corrected mid-matter (`Acme Corp` → `Acme Corporation Inc.`); the
  statute is later amended to 3 years; a precedent case (`Smith v. Jones`)
  cited early on is overturned (`Roe v. Big Co.`) partway through.
- **Estate of Wu** (probate/trust dispute): deliberately shares vocabulary
  with Matter A — a vendor named "Acme Cleaning Services," a "3-year statute
  of limitations," "breach of contract" — so a text-similarity search has a
  real, non-contrived chance of confusing the two matters. One intake
  session (session 3) is deliberately left untagged with no `matter_id`,
  simulating the realistic case of a memo filed before a matter number
  existed in the system.

This is scripted ground truth, not real client data — see Limitations.

### The seven test cases and actual results

```
TEST                        GRAPH   COMPART.  BASELINE  NOTES
--------------------------------------------------------------------------------------------------------------
T1-current-sol              PASS    PASS      FAIL      Current statute of limitations after the amendment
T2-point-in-time-sol        PASS    FAIL      PASS      Belief before the amendment was learned (as of session 4)
T3-precedent-current        PASS    PASS      PASS      Whether Smith v. Jones is still good law, now
T4-point-in-time-precedent  PASS    FAIL      FAIL      Whether Smith was good law as of week 3, before the overturning was learned
T5-party-name-control       PASS    PASS      PASS      Party name correction -- a control case, fair shot for both alternatives
T6-isolation-tagging-drift  PASS    PASS      FAIL      Matter-scoped query hitting an untagged source session
T7-isolation-no-filter      PASS    PASS      FAIL      What a skipped matter filter exposes (routing-bug simulation)
--------------------------------------------------------------------------------------------------------------
TOTAL: graph 7/7   compartment 5/7   baseline 3/7
```

Full output, including the retrieved fact/session IDs behind each verdict,
is in `results/eval_output.txt` (regenerate with the command above — it's
deterministic).

Neither alternative is a strawman. The **flat baseline** wins T2, T3, and
T5 outright, and T5 was included specifically as a control it should be
able to win (a plain supersession where the corrected text happens to
phrase itself similarly to the query). The **compartment store** wins
everything except the two point-in-time cases — it correctly answers every
"what's true now" question and correctly keeps the two matters apart,
exactly what its architecture is built for; it fails T2 and T4 for the
precise structural reason argued above (no prior-layer history to query
against), not from a ranking mistake. The baseline loses on:

- **T1, T4** — no transaction-time axis at all, so it cannot distinguish
  "what's current" from "what we used to believe," and a recency-biased
  retrieval variant (the obvious naive fix, also implemented and tested)
  still leaks a *later* session's content into a query scoped to an
  *earlier* point in the matter, because recency is not the same thing as
  "as of."
- **T6, T7** — matter isolation implemented as a query-time metadata filter
  either misses the one correct source because it was never tagged (T6,
  realistic drift), or is completely bypassed when a caller forgets to pass
  it (T7, realistic bug) — while the graph store's `query()` has no
  callable form that omits `matter_id`, which was verified directly rather
  than just asserted:

  ```
  $ python -c "from legal_memory.graph_store import GraphMemoryStore; \
               from legal_memory.scenario import build_facts; \
               GraphMemoryStore(build_facts()).query(query_text='x')"
  TypeError: GraphMemoryStore.query() missing 1 required positional argument: 'matter_id'
  ```

  An adversarial audit (see Reflection) caught that this only enforced the
  argument's *presence*, not its value: `query(None, ...)` or `query('', ...)`
  originally returned `[]` silently instead of raising. Fixed: `query()` now
  raises `ValueError` for any falsy `matter_id`, verified directly:

  ```
  $ python -c "from legal_memory.graph_store import GraphMemoryStore; \
               from legal_memory.scenario import build_facts; \
               GraphMemoryStore(build_facts()).query(None, 'x')"
  ValueError: query() requires a non-empty matter_id
  ```

### Sanity-checking the scorer itself (FAILURE-CLASSES #4)

A scorer that always agrees with the system it's designed to favor proves
nothing. Before trusting the 7/7 result, the harness independently disables
each of the design's two structural claims in turn — `GraphMemoryStore`'s
`enforce_time` and `enforce_matter` flags, same facts and same ranking code,
one axis switched off at a time — and confirms the exact same scorer flips
the cases that axis is responsible for back to FAIL:

```
=== Sanity check: break the graph store's TIME enforcement (FAILURE-CLASSES #4) ===

  T2-point-in-time-sol: FAIL -- forbidden fact(s) surfaced: ['A-sol-v2']
  T4-point-in-time-precedent: FAIL -- forbidden fact(s) surfaced: ['A-precedent-v2']
  Confirmed: scorer correctly flags every previously-passing case in this
  axis as failing once that axis's enforcement is removed.

=== Sanity check: break the graph store's MATTER-PARTITION enforcement (FAILURE-CLASSES #4) ===

  T2-point-in-time-sol: FAIL -- top-1 was B-vendor-sol, expected one of ['A-sol-v1']
  T6-isolation-tagging-drift: FAIL -- forbidden fact(s) surfaced: ['A-sol-v2']
  T7-isolation-no-filter: FAIL -- forbidden fact(s) surfaced: ['B-vendor-sol']
  Confirmed: scorer correctly flags every previously-passing case in this
  axis as failing once that axis's enforcement is removed.
```

Note `enforce_matter=False` is a test-only escape hatch on the store's
internal filter, used only to prove the scorer would catch it if the
partition were ever removed — it does not mean the partition can be
bypassed in normal use: `Fact()` still requires `matter_id` at construction
regardless of this flag, and `query()` still requires a non-empty
`matter_id` argument (see below).

## Limitations (honest)

- **`CompartmentMemoryStore` models the *architectural pattern*
  (current-layer-only, matter-partitioned), not the actual Honcho or Cognee
  libraries.** Neither was installed or run; this is a from-first-principles
  implementation of what their defining property (compartmentalized, current
  understanding, no bi-temporal edge history) would do on this scenario, not
  a benchmark of those specific products. If either library's real
  implementation adds some form of history tracking beyond what their
  core design papers/docs describe, that would need to be checked directly
  against the library, not inferred from this stand-in. It also gets matter
  isolation "for free" only because it reuses `GraphMemoryStore`'s exact
  `Fact` schema and non-nullable `matter_id` — a real Honcho/Cognee-style
  system might not enforce a per-compartment key that strictly, so the
  claim "isolation is not this family's weak point" (see above) is
  demonstrated for *this stand-in's* inherited partition mechanism, not
  independently verified for either library's actual compartment
  implementation. (Found by a third audit round; recorded here rather than
  quietly assumed.)
- **Synthetic scenario, not real client data.** The 12 sessions were
  scripted to contain the specific failure modes being tested for
  (supersession, overturned precedent, matter-vocabulary collision). It
  demonstrates that the *mechanism* works and that a flat baseline
  structurally cannot do the same things — it does not demonstrate what
  either system does on messy, real legal-research transcripts at scale.
- **No generative LLM in this loop.** The eval measures *retrieval*
  correctness (does the right fact/session surface, scoped and dated
  correctly), not the quality of a generated answer built on top of it.
  That's deliberate — it isolates the memory-architecture variable from
  prompt/model quality — but a full system still needs an evaluation of
  what an LLM does with correct-vs-incorrect retrieved context.
- **Ranking is TF-IDF cosine similarity for both systems, not real
  embeddings.** This was a deliberate choice to keep the prototype
  dependency-free (no network/install risk), and it's a fair comparison
  precisely because both systems use the identical ranking code — but a
  production system would use embeddings, which could change the
  baseline's specific win/loss pattern on any one query (T2/T3/T5) without
  changing the structural argument (no transaction-time axis, no
  required-field isolation) that the losses on T1/T4/T6/T7 actually rest
  on.
- **Extraction from transcript to fact is manual in the core eval.** In the
  7-case comparison above, facts are hand-authored alongside the sessions
  that "produced" them. A real system needs an extraction step (likely
  LLM-driven) from transcript to structured fact. No LLM was available in
  this environment to build that step for real (see the supplementary
  experiment below for what was tried instead and what it found).
- **Scale.** The 7-case eval uses 12 sessions, 2 matters, ~10 facts — too
  small to say anything about real scale on its own, so this was actually
  measured (`python -m legal_memory.benchmark`, synthetic random text,
  `time.perf_counter`, real output below) rather than left as an assumption:

  ```
  N facts/sessions  graph build ms  baseline build ms  graph query ms  baseline query ms
  ---------------------------------------------------------------------------------------
  100               1.42            1.19               0.25            0.21
  1000              13.59           12.78              0.25            0.34
  5000              64.98           61.46              0.51            0.46
  20000             277.21          255.06             1.31            1.18
  ```

  Two findings, one of which surprised me: **query-time latency stays low
  and roughly flat** as N grows, because a query is always scoped to one
  matter (the benchmark grows the number of matters along with N, which is
  the realistic case — a long-running practice accumulates more matters
  over time, not one matter with 20,000 facts) — matter-partitioning
  functions as sharding almost by accident, which is a genuine point in the
  design's favor I hadn't argued for going in. The **real scaling risk is
  index construction**, not per-query cost: `GraphMemoryStore` and
  `VectorBaseline` both rebuild their entire TF-IDF corpus from every fact
  in the store at construction time, with no incremental-update path.
  Neither store supports adding one new fact without re-indexing
  everything, so a naive implementation that re-constructs the store on
  every new session over weeks of continuous use would pay full
  reindex cost (277ms at 20,000 facts, growing linearly) on every single
  addition — this is the concrete argument for the proper indexing a real
  deployment needs (which is exactly what Graphiti's actual implementation
  provides on top of Neo4j, and what this prototype does not build).

## Supplementary experiment: can a non-LLM heuristic do the extraction step?

The Limitations section above names transcript-to-fact extraction as the
biggest gap between this prototype and a deployed system, and says an LLM
would be needed to do it — but this environment has neither an
`ANTHROPIC_API_KEY` nor the `anthropic` package installed (checked directly,
not assumed). Rather than leave that as pure assertion, `legal_memory/extractor.py`
tries the closest thing buildable without either: a generic, non-LLM
heuristic (sentence-splitting + the same shared TF-IDF cosine similarity
used everywhere else in this repo) that reads the raw session transcripts
and proposes candidate facts and supersessions on its own — no fact IDs, no
supersession links, nothing scenario-specific fed in.

**The similarity threshold (`SIMILARITY_THRESHOLD = 0.3`) was fixed before
running this, based on general reasoning about short-text TF-IDF cosine
scores, and was not adjusted after seeing the output below.** Changing it
post-hoc to make the numbers look better would be the exact "solved
backward" pattern FAILURE-CLASSES.md warns about — so what follows is
reported as it came out, not tuned.

Run: `python -m legal_memory.extractor`. Real output (abridged; full output
is reproducible with that command):

```
Total candidate facts extracted: 18
Supersession events detected: 3
Sentences rejected for missing matter_id: 2
```

Compared against the 3 supersession events the hand-authored scenario
actually contains (party-name correction at session 4, statute amendment at
session 7, precedent overturned at session 10), the heuristic did
**noticeably worse than the hand-authored ground truth**, in ways worth
naming precisely rather than averaging into one score:

- **Party-name correction (session 4): missed entirely.** The corrected
  sentence scored only 0.147 against the original — well under threshold —
  so it was filed as an unrelated new fact instead of a correction.
- **Statute amendment (session 7): missed, and close.** The amendment
  sentence scored 0.267 against the original 4-year rule — just under the
  0.3 threshold. This is the kind of near-miss that would tempt
  after-the-fact threshold-lowering, which is exactly why the threshold was
  fixed before running.
- **Precedent overturning (session 10): detected, but not of the right
  target.** Something real actually broke the naive sentence-splitter here:
  splitting on `(?<=[.!?])\s+` treats "Smith **v.** Jones" as a sentence
  boundary (the period in the case-citation abbreviation "v."), fragmenting
  the citation across two "sentences" every time it appears, which produced
  two separate session-9 fragments ("Drafting motion; cited Smith v." and
  "Jones for the tolling argument.") instead of one sentence. Quoting the
  extractor's own logged lines directly rather than paraphrasing them (see
  below for why that distinction matters here specifically):

  ```
  session 10 ... supersedes:extracted-11 (score=0.473) [from session 9: "Jones for the tolling argument."]
      "Confirmed: Smith is no longer good law for the tolling argument."
  session 12 ... supersedes:extracted-10 (score=0.404) [from session 9: "Drafting motion; cited Smith v."]
      "Revised motion to drop the Smith v."
  session 12 ... supersedes:extracted-2 (score=0.343) [from session 2: "Jones: demand letter tolls the statute of limitations."]
      "Jones tolling argument and rely on the 3-year statute of limitations directly."
  ```

  So: session 10's overturning notice superseded session 9's *"Jones for
  the tolling argument"* fragment — not the original session-2 precedent
  claim ("Jones: demand letter tolls the statute of limitations."), which
  is the one a correct extractor should have invalidated at that point.
  That original session-2 fact was only superseded two sessions later, by
  session 12's "Jones tolling argument and rely on the 3-year statute of
  limitations directly." (score 0.343) — and only because that fragment
  happened to share enough vocabulary with it, not because the heuristic
  understood the citation was the same case. Session 9's other fragment,
  "Drafting motion; cited Smith v.," was separately superseded by session
  12's "Revised motion to drop the Smith v." None of these three events
  touch each other's targets; they're three independent, partially-wrong
  supersession chains produced by the same citation-splitting bug.

  This bullet itself was wrong twice before landing on the version above:
  a first draft (written from a manual index count) said session 10
  superseded a "same-session" fragment; a second draft (written from
  memory of an earlier corrected version, without re-reading the log)
  said it superseded "Drafting motion; cited Smith v." instead of "Jones
  for the tolling argument." Both were caught the same way — by an
  independent adversarial audit re-running `python -m legal_memory.extractor`
  and diffing the claim against the real output, not by re-reasoning about
  it from memory. The version above is transcribed directly from a fresh
  run's output (quoted above verbatim), not paraphrased, specifically to
  stop this from happening a third time.
- **Matter isolation held.** Both sentences from the untagged session 3
  were rejected outright (`Fact()` still requires a non-empty `matter_id`,
  even here) rather than silently attributed to the wrong matter or
  dropped without a trace — the structural guarantee argued for above did
  its job even when fed through a much sloppier pipeline than the
  hand-authored one.

**What this experiment actually shows:** not that extraction is impossible,
but a concrete, unstaged illustration of *why* it's hard — a citation
abbreviation broke sentence boundaries, and two of three real supersessions
scored under a reasonable, non-tuned threshold. A production extractor
needs at minimum legal-citation-aware segmentation (not generic
sentence-splitting) and probably an LLM's semantic judgment rather than
lexical overlap for detecting "this corrects that." This is evidence for
the Limitations claim, not a working replacement for it — the core 7-case
eval above still relies on hand-authored facts, and this heuristic is not
part of that eval or its scoring.

## Reflection

- **Audits performed (eight rounds, each a fresh subagent with no prior
  context):**
  - *Round 1* found the codebase's claims otherwise checked out under real
    execution (baseline win/loss pattern is a real steelman result, the
    then-single sanity check reproduced exactly, `eval_output.txt` matched
    a fresh run byte-for-byte), plus one real gap: `GraphMemoryStore.query(None, ...)`
    / `query('', ...)` — a caller *supplying* a falsy `matter_id` rather
    than omitting it — silently returned `[]` instead of raising, narrower
    than the "cannot query without a matter" claim as originally worded.
    Fixed by rejecting any falsy `matter_id` with `ValueError`.
  - *Round 2* re-verified the round-1 fix directly, then found that the
    scorer's own sanity check (FAILURE-CLASSES #4) only exercised the
    *temporal* structural claim (`enforce_time`), not the *matter-isolation*
    one — the isolation claim was true (the auditor independently confirmed
    it by monkeypatching) but was never self-tested by the harness itself.
    It also flagged `TestCase.allow_baseline_empty` as dead code (T6's
    baseline never actually returns empty — it returns a confidently wrong
    top-1 instead) and a latent, never-triggered `top_k=-1` slice-semantics
    quirk in both stores (harmless: the harness always calls with `top_k=3`).
    Fixed: added a first-party `enforce_matter` flag to `GraphMemoryStore`
    and a second automated sanity check that breaks matter-partitioning and
    confirms the same scorer flips T2/T6/T7 to FAIL; removed the dead
    `allow_baseline_empty` branch. Did not fix the `top_k=-1` quirk —
    it's never reachable with real inputs and adding validation for an
    input that can't occur would be exactly the kind of unnecessary
    defensiveness this assessment's own instructions warn against; noting
    it here instead is the honest choice.
  - *Round 3* audited the `CompartmentMemoryStore` addition (built after
    rounds 1-2, as the deliberate scope-raising improvement below) directly:
    confirmed its "current layer" candidate sets are never trivially-sized
    (2-3 real candidates, not 1), confirmed the forbidden-fact FAILs on
    T2/T4 are decisive (the forbidden fact wins top-1 by 2-3.5x TF-IDF
    margin, not a near-tie), and confirmed `results/eval_output.txt` hashes
    identically to a fresh run (SHA-256 match). It also found one real
    disclosure gap — fixed above — that the compartment store's matter
    isolation is inherited for free from `GraphMemoryStore`'s schema, not
    independently demonstrated for either real library's own compartment
    mechanism.
  - *Round 4* re-verified essentially everything from scratch after the
    extraction experiment was added (34/34 tests, byte-identical eval
    output including both sanity checks, `matter_id` attacked with `''`,
    `None`, `0`, and whitespace-only, all failing safe) and found one real,
    medium-severity issue: the "Precedent overturning" bullet in the
    extraction write-up had the supersession target wrong — it named
    session 9's "Drafting motion; cited Smith v." fragment when the actual
    logged output showed session 10's event superseded the *other*
    session-9 fragment, "Jones for the tolling argument." This was the
    same error class the write-up already claimed to have fixed once
    (round-3-era self-correction, described below) — a second instance of
    it had slipped in regardless. Fixed by quoting the extractor's raw
    output lines verbatim in that bullet instead of paraphrasing them from
    memory, specifically to remove the step (recalling which fragment was
    which) that produced the mistake twice.
  - *Round 5* specifically re-checked the round-4 fix character-by-character
    against a fresh `python -m legal_memory.extractor` run (no third
    recurrence of the error), spot-checked the scale-benchmark numbers
    (confirmed genuinely live `time.perf_counter` timing — re-running gives
    slightly different numbers than the README table, which is expected and
    was never claimed to be deterministic, unlike the eval), and tried
    `GraphMemoryStore([])` / `CompartmentMemoryStore([])` / `VectorBaseline([])`
    with empty inputs (all return `[]` cleanly). Found nothing new.
  - *Round 6* (final, budget-constrained) spot-checked two previously
    unverified extraction scores (0.147, 0.267) against fresh output,
    matched, confirmed `SIMILARITY_THRESHOLD`/`MIN_SENTENCE_WORDS` are used
    exactly as described, confirmed `benchmark.py`'s matter-count-scales-
    with-N claim against the actual source line, and ran all four
    executable modules (`eval_harness`, `pytest`, `extractor`, `benchmark`)
    fresh to confirm none have silently broken. Found nothing new.
  - *Round 7* (budget nearly exhausted, single targeted check) verified the
    extractor's summary triplet (18 facts / 3 supersessions / 2 rejected)
    against fresh output verbatim — the one specific number block no prior
    round had explicitly named as checked. Held up exactly.
  - *Round 8* (final, budget essentially exhausted): one check only —
    `python -m legal_memory.eval_harness` vs. `results/eval_output.txt`,
    byte-for-byte match confirmed. Stopping the audit process here.
  - All eight rounds' fixes were re-verified by actually re-running the eval
    (`python -m legal_memory.eval_harness`) and confirming results were
    unchanged or changed only as intended, not by re-reading the diff.
- **Single weakest remaining claim:** the "structural isolation" argument
  rests on `matter_id` being a required, non-empty argument in this
  prototype's `Fact` and `GraphMemoryStore.query()` — now verified for both
  the omitted-argument and falsy-value cases. But that guarantee only holds
  inside this code; a real system still needs the *fact-extraction* step
  (LLM-driven, not built here) to itself always supply a *correct*
  `matter_id`, and that step is exactly the kind of place a prompt-level
  bug could silently supply a wrong-but-truthy matter id (not caught by any
  check here). The structural argument is real but one layer up from where
  extraction actually happens — someone auditing this should look there
  first.
- **Most consequential design decision:** keeping the full episodic
  transcript as the source of truth alongside the graph, rather than
  building a pure Graphiti-style graph-only memory. The alternative
  (graph-only) is more storage-efficient and closer to Graphiti's actual
  reference design, and I rejected it because a legal user's real question
  is usually "show me exactly where this came from," and a graph edge
  alone can't answer that once the extraction that produced it is
  forgotten — provenance mattered more here than efficiency.
- **What I actually ran vs. what I never verified:** ran the full 7-case,
  three-system eval and captured its real output (`results/eval_output.txt`,
  re-confirmed byte-identical by SHA-256 in round 3), ran both scorer-sanity
  checks against deliberately broken variants (time axis and matter-partition
  axis) and confirmed each fails exactly as expected, ran direct interpreter
  checks confirming the `matter_id` requirement is enforced by the language,
  not just asserted in prose, and ran the non-LLM extraction heuristic and
  reported its real (mediocre) results rather than tuning it until it
  looked better. I never built or ran a real LLM-driven extraction step, or
  any comparison involving a real embedding model, a real generative LLM
  answering from retrieved context, or the actual Honcho/Cognee libraries
  themselves — confirmed `ANTHROPIC_API_KEY` and the `anthropic` package
  are both absent from this environment rather than assuming it, so the
  LLM-driven version specifically could not be attempted here at all.
- **With another 30 minutes:** fix the naive extractor's most concrete,
  named failure — legal-citation-aware sentence segmentation (so "Smith v.
  Jones" survives as one unit instead of splitting at the citation's own
  period) — and re-run the same extraction experiment to see whether that
  alone recovers the precedent-overturning chain, without touching the
  similarity threshold that's still governing whether corrections get
  detected at all. That's a smaller, honestly-scoped next step; the
  bigger one (a real LLM-driven extractor, then re-running the 7-case eval
  against its output instead of hand-authored facts) remains the actual
  biggest gap between what's demonstrated here and a deployed system, and
  still isn't attemptable in this environment specifically.
  Earlier in this Reflection process (before attempting extraction), the
  remaining budget went to two other things buildable without external
  dependencies: 31 pytest unit tests (of the 34 total now in `tests/` —
  3 more were added afterward for the extractor's structural guarantees)
  locking in the bi-temporal boundary
  semantics (one test's own premise was wrong on first write — assumed a
  TF-IDF tie that turned out not to be one once IDF-weighted norms were
  actually computed — caught by running it, not by inspection), and an
  actual scale benchmark (`legal_memory/benchmark.py`) that replaced an
  unverified "O(n), not benchmarked" limitation with real measured
  numbers and a corrected, more precise claim: query latency stays flat
  because matter-partitioning shards the search space, but full corpus
  reindexing on every new fact (no incremental index) is the real scaling
  risk for weeks of continuous use.
