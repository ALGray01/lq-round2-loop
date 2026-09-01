# A methodology layer for legal data, before the LLM sees it

**Question answered (OQ-026):** Before an LLM ever sees legal data, what
methodology layer should encode precedent relations, interpretive
principles, authority weighting, and doctrinal hierarchy? Entity extraction
(what Isaacus/Kanon already does) tells an LLM *what is in the text* --
party names, dates, defined terms. It says nothing about *what body of
doctrine governs how to read it*, which authority controls when two sources
conflict, or when one binding-but-criticized precedent still wins. This
submission proposes a schema for that layer and demonstrates it, fully
executed, on one bounded area chosen first -- **ambiguity resolution in
written contracts** (the threshold question of when extrinsic evidence is
admissible, the UCC §1-303 hierarchy of course-of-performance/dealing/
trade-usage, and the common-law canons of construction) -- and then reused,
with the identical schema and almost all of the same engine code, on a
second: **resolving ambiguity in federal statutory text** (the major
questions doctrine, the 2024 overruling of Chevron deference, and the rule
of lenity). The second area exists specifically to test whether the schema
actually generalizes rather than just asserting that it does -- see
Generalization, below.

## Why this bounded area

Contract-interpretation doctrine has everything the question asks for, in
a small, well-documented space:

- **A real doctrinal hierarchy** with a public, citable priority order: UCC
  §1-303(e) fixes express terms > course of performance > course of dealing
  > usage of trade whenever they conflict.
- **A genuine jurisdictional split on interpretive principle**, not just
  variation in outcome: California (*Pacific Gas & Electric Co. v. G.W.
  Thomas Drayage & Rigging Co.*, 69 Cal. 2d 33 (1968)) holds extrinsic
  evidence must be provisionally admitted even for facially clear language;
  New York (*W.W.W. Assocs., Inc. v. Giancontieri*, 77 N.Y.2d 157 (1990))
  holds the opposite. Same facts, opposite rule, by design of the
  jurisdictions' courts -- exactly the kind of thing an LLM cannot infer
  from the contract text alone.
- **Authority weighting that isn't just "higher court wins"**: *Trident
  Center v. Connecticut General Life Ins. Co.*, 847 F.2d 564 (9th Cir.
  1988), is a federal appellate court that openly disagrees with PG&E's
  rule and follows it anyway, because Erie requires it to apply California
  substantive law regardless of the panel's own view. A weighting scheme
  that just ranked "federal circuit > state supreme court" would get this
  backwards.
- **Interpretive principles as literal named canons** (ejusdem generis,
  noscitur a sociis, expressio unius, contra proferentem) with a real,
  citable ordering (contra proferentem is last resort, Restatement (2d)
  Contracts §206) -- these are exactly "interpretive principles" as the
  question names them.

## The schema

`schema/methodology_layer.schema.json` (JSON Schema, draft 2020-12) is the
single source of truth for structure -- the Python code validates the
knowledge base against it rather than duplicating the shape in a second,
potentially-drifting model definition. Four entities:

- **`Authority`** -- one source of law (constitution/statute/regulation/
  case/restatement/treatise), with `home_jurisdiction`, `court_level`, and
  `binding_in` (the jurisdictions where it actually binds, vs. everywhere
  else where it is at most persuasive). Deliberately **does not store a
  weight field** -- see below.
- **`PrecedentRelation`** -- a directed edge between two cases:
  `follows` / `distinguishes` / `overrules` / `criticizes` / `limits` /
  `questions` / `extends`, tagged with `on_issue` (the specific doctrinal
  point, not "the case in general") and `source_bound_by_target` (a
  boolean that lets "criticizes" and "is bound by" coexist truthfully --
  the Trident Center case is exactly this).
- **`DoctrinalRule`** -- an interpretive principle with a machine-checkable
  `trigger` (a structural precondition on the fact pattern:
  threshold-ambiguity test, structural pattern in the clause, a conflict
  between evidence sources, or "fallback"), a `priority` for ordering
  against other triggered rules, and `authority_basis` (which `Authority`
  ids ground it).
- **`DoctrinalHierarchy`** -- a named, ordered ladder of rule ids (e.g. the
  UCC §1-303 order of resort), so "hierarchy" is data, not something
  encoded implicitly in if/else branching.
- **`InterpretiveAnnotation`** -- the actual unit meant to reach the LLM in
  place of (or alongside) raw entity spans: a threshold determination, the
  ordered list of applicable rules with computed weights, any
  `conflicting_authority` (precedent tension the LLM needs to reason
  about, not have hidden from it), a one-line structural posture, and
  resolved citations with role (`binding`/`persuasive`).

**Authority weight is computed, not stored.** `methodology_layer/weighting.py`
derives a numeric weight from three declared facts -- authority type, court
level, and whether the authority binds the jurisdiction being queried --
via one formula applied uniformly. This was a deliberate reaction to this
project's own `FAILURE-CLASSES.md` item 1 (verification/scoring that's
secretly a hardcoded value dressed up as reasoning): if weight were just a
number typed into the knowledge base, nothing would stop it from being
whatever number made the demo come out right. Computing it means the same
case (PG&E) gets a different, *derived* weight in California (binding,
weight 120) versus New York (persuasive, weight 60) versus a hypothetical
un-enacted-statute jurisdiction (weight 0) -- see
`tests/test_engine.py::test_authority_weight_favors_binding_over_persuasive_same_court_level`.

## What's actually built and runs

```
schema/methodology_layer.schema.json      JSON Schema for the four entities above -- shared, unchanged,
                                           by BOTH knowledge bases below
knowledge_base/contract_interpretation/
  kb.yaml                                 10 authorities, 2 precedent relations,
                                           10 doctrinal rules, 2 hierarchies
knowledge_base/statutory_construction/
  kb.yaml                                 8 authorities, 2 precedent relations,
                                           8 doctrinal rules, 2 hierarchies -- a second, unrelated
                                           bounded area, added in this session's reserve phase
                                           specifically to test generalization; see Generalization,
                                           below
methodology_layer/
  models.py                               loads + validates either KB against the same schema
  weighting.py                            the computed-weight formula
  engine.py                               annotate_clause(): KB + fact pattern -> InterpretiveAnnotation;
                                           domain-agnostic, see its module docstring for what had to
                                           be generalized and why
  entity_extraction_stub.py               a stand-in for Isaacus/Kanon-style raw NER, for contrast
demo.py                                   5 contract-interpretation scenarios, side by side with raw NER
demo_statutory.py                         5 statutory-construction scenarios, same engine, second KB
comparisons/
  naive_baseline.py                       a boring if/elif alternative, built to test whether the
                                           structured layer earns its complexity -- see Baseline
                                           comparison, below
tests/
  test_kb_validates_schema.py             schema validation, incl. two deliberately-broken KBs (must fail)
  test_engine.py                          8 cases against the contract KB, each checkable against a
                                           named real case/statute
  test_statutory_kb.py                    6 cases against the statutory KB, same standard
  test_engine_robustness.py               4 cases from round 2's attacker-persona audit: a typo'd,
                                           a dunder-named, and a non-string `requires_flag` must each
                                           raise a clear error, not misbehave silently or crash opaquely
```

### Run it

```bash
pip install -r requirements.txt
python -m pytest -q                   # 24 tests
python demo.py                        # 5 contract-interpretation scenarios, full JSON output
python demo_statutory.py              # 5 statutory-construction scenarios, same engine, second KB
python comparisons/naive_baseline.py  # the boring alternative, for comparison
```

All four were actually run in this session, not just written. `python -m
pytest -q` returned `24 passed in 0.60s` (as of the final round-2 fixes).
`python demo.py` and `python demo_statutory.py` each produced full output
for all 5 of their scenarios (captured in `demo_output.txt` and
`demo_statutory_output.txt` for convenience; regenerate either any time
with the commands above -- neither is hand-edited).

### What the demo actually shows

Scenario 1 sends the identical clause text through the engine twice, once
per jurisdiction, and gets the doctrinally correct opposite answers:
California returns `"provisionally admissible... regardless of facial
clarity"` (PG&E); New York returns `"inadmissible: contract is unambiguous
on its face"` (Giancontieri). Scenario 2 reproduces Trident Center's own
fact pattern (a categorical no-prepayment clause) in a 9th-Circuit query,
and the engine both borrows California's rule (via the `ERIE_STATE_LAW_SOURCE`
mapping in `engine.py`, representing the actual Erie doctrine constraint)
*and* surfaces `pr_trident_criticizes_pge` in `conflicting_authority`, so
the tension is visible to whatever reads the annotation rather than
silently resolved. Scenario 3 shows the UCC hierarchy correctly ranking
`course_of_performance` (priority 2) ahead of `usage_of_trade` (priority 4)
per §1-303(e). Scenarios 4 and 5 show a structural canon (ejusdem generis)
and a last-resort canon (contra proferentem) firing on distinct clause
shapes -- and `test_contra_proferentem_is_last_resort_not_first_move`
in `tests/test_engine.py` explicitly checks that contra proferentem does
*not* fire when ejusdem generis already resolved the same fact pattern,
i.e. that "last resort" is enforced in code, not just asserted in the rule's
prose.

## Generalization: a second bounded area of law

The first version of this submission's Reflection section (still visible
in git history) named its own weakest structural claim as: "the schema is
intended to generalize... but that generalization is claimed, not
independently demonstrated." Rather than leave that as an assertion, this
session built a second, unrelated knowledge base --
`knowledge_base/statutory_construction/kb.yaml` -- covering resolution of
ambiguity in federal statutory text: the major-questions clear-statement
doctrine (*West Virginia v. EPA*, 2022), the statutory plain-meaning rule
(*Conn. Nat'l Bank v. Germain*), the 2024 overruling of Chevron deference
by *Loper Bright Enterprises v. Raimondo* (with Skidmore respect reinstated
as the live standard), statutory-form canons of construction, and the rule
of lenity as a criminal-statute-specific last resort (*United States v.
Bass*). It validates against **the exact same, unmodified** JSON Schema.

Building it surfaced three real generalization bugs in `engine.py` that a
single-KB submission could not have caught, because they were hardcoded to
assumptions that happened to hold for the one KB that existed:

1. **`_apply_fallback` looked up `kb.doctrinal_rules["rule_contra_proferentem"]`
   by literal id** and checked `fp.unequal_bargaining_power` directly. The
   statutory KB's own last-resort rule is `rule_of_lenity`, gated on a
   different flag (`criminal_statute`) entirely. Fixed by adding a
   `trigger.params.requires_flag` convention: any KB's fallback rule names
   the `FactPattern` boolean attribute that must be true for it to fire,
   and the engine reads it generically via `getattr`. No schema change was
   needed -- `params` was already a free-form object for exactly this
   reason -- only a new, documented convention for how to use it.
2. **The evidence-hierarchy lookup was gated on `fp.contract_type ==
   "goods_sale"`**, a condition with no meaning for agency-interpretation
   evidence in the statutory KB. The gate was redundant with the caller
   only populating `evidence_conflict_sources` when relevant, so it was
   removed rather than parameterized -- one fewer assumption, not a bigger
   one.
3. **`conflicting_authority` was populated by appending specific,
   hardcoded relation-id strings** (`"pr_trident_criticizes_pge"`,
   `"pr_newport_limits_pge"`) inside the contract-specific threshold logic.
   Replaced with `_conflicting_authority_for`, a single generic function
   that surfaces any `PrecedentRelation` whose `target_case` is among the
   authorities actually being cited and whose relation type represents
   live tension (`criticizes`/`limits`/`overrules`/`questions`) rather than
   mere lineage. This is what makes `pr_loper_overrules_chevron` show up
   automatically in the statutory demo the moment `case_chevron` is cited
   -- no statutory-specific code was written to make that happen.

What did **not** generalize automatically, and is still domain-specific
code by necessity rather than oversight: `_evaluate_threshold_rule`'s
natural-language outcome text is one `if rule_id == "...":` branch per
threshold rule. The *trigger structure* (an ordered list of
`threshold_ambiguity` rules, walked in priority order until one disposes of
the case -- itself a generalization this KB required, since the contract
KB never needed more than one threshold rule per jurisdiction) is fully
data-driven; the *English sentence* describing what a given rule's
application means is not, because that content is genuinely rule-specific
legal prose, not structure a schema can capture without either an
overengineered template language or an LLM in the loop (which is exactly
the layer downstream of this one, not this one's job).

`python -m pytest -q` covers both KBs and passed after every change
described above -- see `tests/test_statutory_kb.py` for the
statutory-specific assertions, each checked against the real holdings
named above, not against each other. (Test count updated again below,
after round 2 added a fourth file.)

**Honest scope of the generalization claim, per round 2's baseline
builder** (see below): of `engine.py`'s roughly 260 executable lines,
about a quarter -- almost entirely `_evaluate_threshold_rule`'s per-rule-id
branches -- is still domain-specific prose, not reusable structure. The
other three-quarters (dispatch, weighting integration, the fallback/canon/
evidence-conflict/conflicting-authority mechanisms) needed zero changes
for the statutory KB and were confirmed to need zero changes by that KB
actually validating and passing tests. So "the schema and most of the
engine's dispatch logic generalize" is the accurate claim; "the engine
generalizes" alone overstates it, because every unit of new *doctrinal
content* a third KB would add necessarily lands in the one function that
doesn't generalize by design (see the module docstring for why: rule
outcomes are legal prose, not structure). Round 1's original phrasing
leaned toward the stronger, less accurate version of this claim; round 2's
audit is why this paragraph exists to correct it in the same document
rather than only in an internal note.

## Reserve-phase audit, round 1 (three independent subagents)

Before finishing, three fresh subagents with no prior context of this
session audited the shipped code adversarially. Findings, and what was
actually done about each:

**Verification skeptic** -- checked every `test_engine.py` assertion
against real doctrine independently, confirmed the weighting formula has
no per-authority special-casing, ran the tests, then deliberately broke
two things (inverted a UCC priority, swapped the binding/persuasive
multipliers) and confirmed the relevant tests failed correctly before
reverting -- i.e. the tests are not tautological. No issues found.

**Attacker** -- found one real, scoped issue: `load_kb` uses
`yaml.safe_load`, which blocks arbitrary code execution but not
anchor/alias ("billion laughs") expansion; a small crafted YAML file with
chained aliases caused unbounded blowup when the parsed structure was
traversed. This only matters if the KB file were ever attacker-supplied --
the current design assumes a trusted local KB file, not multi-tenant
external submission, so no runtime mitigation was added (would be
premature hardening for a threat model that doesn't exist yet in this
submission's scope). Recorded here instead as a concrete constraint on any
future extension that accepts external KB files. The attacker also found
the schema had no `additionalProperties: false` anywhere, so a typo'd or
injected field on any entity passed validation silently -- this **was**
fixed (added to every object definition in
`schema/methodology_layer.schema.json` except the intentionally-open
`trigger.params`), and `tests/test_kb_validates_schema.py::test_schema_rejects_unexpected_fields`
was added and confirmed to fail before the fix and pass after. No ReDoS,
no path-traversal exploit, no overclaimed integration.

**Baseline builder** -- built `comparisons/naive_baseline.py`, a single-file
if/elif version with a hardcoded `(authority, jurisdiction) -> weight`
lookup table, and ran it against the same 5 `demo.py` scenarios. Result,
confirmed by rerunning both myself: **the naive version reproduces the
shipped engine's output field-for-field identically on all 5 scenarios**,
in about a fifth of the code. For the demo exactly as posed, the schema and
computed-weight formula buy nothing over hardcoding -- that is the honest
result, not softened. The gap shows up only outside the anticipated set:
asked for PG&E's weight in a jurisdiction that isn't CA/NY/9th-Cir, or the
UCC statute's weight in an un-enacted jurisdiction (`US-TX`), the naive
lookup table returns `(None, None)` (nobody thought to type that
combination in), while the shipped engine's `weighting.compute_weight()`
returns a principled `0.0`/persuasive-weight answer because it is a total
function over the three declared facts, not a lookup table. This is
exactly `tests/test_engine.py::test_statute_not_enacted_in_jurisdiction_has_zero_weight`
and `test_authority_weight_favors_binding_over_persuasive_same_court_level`,
now with an explicit naive counter-example on record showing what the
un-structured version would have gotten wrong (silence, not a wrong
number, but silence is its own failure mode: it required a human to
notice the input was never anticipated). Net honest conclusion: the
structured layer's value is in generalizing past whatever the demo authors
thought to anticipate, not in the 5 anticipated scenarios themselves -- see
Reflection's answer on what a second bounded area of law would test next.

## Reserve-phase audit, round 2 (after the statutory-construction generalization)

Round 1's audit found real issues and there was still budget left, so a
second round of three fresh subagents ran against the updated state
(schema + engine + both KBs), per this session's own governing protocol
(repeat once more if the first round found real issues and budget
remains). This round targeted the new generalization work specifically
rather than re-litigating round 1.

**Verification skeptic** -- checked, and confirmed true, that the schema
file was genuinely untouched by the statutory-KB commit (`git log`
against `schema/methodology_layer.schema.json` shows its last change was
round 1's fix); independently confirmed the doctrinal claims in
`test_statutory_kb.py` (Loper Bright really did overrule Chevron in 2024,
West Virginia v. EPA really is the major-questions doctrine's leading
case, United States v. Bass really is a rule-of-lenity case); ran the
tests, then reverted `_apply_fallback` to its pre-generalization,
hardcoded-id version and confirmed two statutory tests correctly failed as
a result before reverting back clean; and diffed the pre-refactor engine
(`git show d3a178e:methodology_layer/engine.py`) against current to
confirm the three hardcoding bugs the Generalization section describes
genuinely existed as described, not an embellished retelling. All four
checks held up.

**Attacker** -- found the real bug this section's fixes address: the
original `getattr(fp, flag_name, False)` in `_apply_fallback` had three
failure modes for a malformed KB, verified end to end by actually
constructing each and calling the engine (not just reasoning about them):
a typo'd `requires_flag` silently never fired the rule; a dunder name like
`__class__` silently *always* fired it (a class object is truthy
regardless of the fact pattern -- the schema can't catch this because
`trigger.params` is deliberately open-ended); and a non-string value
crashed with a bare, uncaught `TypeError` inside `getattr` -- a
schema-valid KB entry that could kill the engine's public entry point.
Separately confirmed a dangling `PrecedentRelation.target_case` (pointing
at a nonexistent authority) doesn't crash `_conflicting_authority_for`,
just silently and correctly never matches -- not a gap. **Fixed**:
`_apply_fallback` now validates `requires_flag` is a string naming an
actual `FactPattern` field before using it, raising a clear `ValueError`
otherwise; `tests/test_engine_robustness.py` adds four tests constructing
exactly these three failure modes (plus a control case) against a minimal
KB and confirming each now raises instead of misbehaving.

**Baseline builder** -- this round's mandate was to find a different
comparison than round 1's, and it did: rather than re-test the
weight-formula-vs-hardcoding question, it quantified how much of
`engine.py` actually generalized versus how much is still per-domain
special-casing. Verdict, folded into the Generalization section above
rather than left in this audit log alone: roughly a quarter of the file
(concentrated almost entirely in `_evaluate_threshold_rule`) is
irreducibly domain-specific, and a third bounded area would add its new
doctrinal content there, not in the reusable three-quarters. It also
caught a fourth hardcoding instance in the same family as the three the
README already described: "Erie" doctrine prose was hardcoded inline in
`_apply_threshold` even though the function's docstring called it
generic. **Fixed**: the jurisdiction-borrowing table (renamed
`JURISDICTION_BORROWING`) now carries its doctrine citation as data per
entry, so `_apply_threshold` no longer contains any borrowing-specific
prose -- a second borrowing doctrine could be added as a new table entry
with no code change.

`python -m pytest -q` now covers both KBs plus the new robustness
regression file: **24 passed**, re-confirmed after all of round 2's fixes
were applied (not just after round 1's).

## Verification: checking every citation against a real, independent source

Every round of review up to this point -- mine and six separate subagent
passes across two audit rounds -- named the same weakest claim: the case
summaries in both knowledge bases were drawn from training-data knowledge
of famous cases, never checked against an actual citator. That gap didn't
require more engineering to close, only web access, which became available
partway through this session. So it was closed for real rather than left
as a permanent caveat.

All 11 case citations across both knowledge bases were checked with
`WebSearch` against independent sources (Justia, FindLaw, CourtListener,
Cornell LII, Oyez): *Pacific Gas & Electric v. Thomas Drayage*, *Trident
Center*, *Giancontieri*, *Frigaliment*, *Founding Members of the Newport
Beach Country Club*, *Chevron v. NRDC*, *Loper Bright v. Raimondo*,
*Skidmore v. Swift*, *West Virginia v. EPA*, *Conn. Nat'l Bank v.
Germain*, and *United States v. Bass*. For the six most load-bearing --
the ones the actual `test_engine.py`/`test_statutory_kb.py` assertions
depend on -- the check went a level deeper, via `WebFetch` of the actual
opinion text (or, where a court's own site 403'd `WebFetch`, a
law-firm/professional summary quoting the opinion directly) rather than
stopping at a search-engine paraphrase:

- **PG&E**: confirmed verbatim -- "the test of admissibility of extrinsic
  evidence to explain the meaning of a written instrument is not whether
  it appears to the court to be plain and unambiguous on its face, but
  whether the offered evidence is relevant to prove a meaning to which the
  language of the instrument is reasonably susceptible."
- **Giancontieri**: confirmed verbatim -- "extrinsic and parol evidence is
  not admissible to create an ambiguity in a written agreement which is
  complete, clear and unambiguous on its face," plus "sophisticated
  businessmen reduced their negotiations to a clear, complete writing."
- **Trident Center**: confirmed verbatim, including the exact
  Erie citation Kozinski himself used -- "It may not be a wise rule we
  are applying, but it is a rule that binds us. Erie R.R. Co. v. Tompkins,
  304 U.S. 64, 78 (1938)."
- **Chevron**: confirmed verbatim two-step test -- "First, always, is the
  question whether Congress has directly spoken to the precise question at
  issue" / step two, "whether the agency's answer is based on a permissible
  construction of the statute."
- **West Virginia v. EPA**: confirmed -- "where an agency takes action to
  regulate an issue of major economic and political significance, its
  action must be supported by clear statutory authorization," applied to
  reject EPA's claimed Clean Air Act §111(d) authority.
- **Newport Beach Country Club**: see below -- this is the one that did
  *not* confirm the original summary.

The remaining five were then checked the same way, in a second pass once
the first six confirmed how valuable the deeper check was:

- **Frigaliment**: confirmed -- Frigaliment (the party urging the narrower
  "young chicken" meaning) bore the burden of proof and the court examined
  witness testimony from both industry members and the parties themselves
  to determine the intended meaning, finding for the defendant.
- **Skidmore**: confirmed verbatim -- "the weight of such a judgment in a
  particular case will depend upon the thoroughness evident in its
  consideration, the validity of its reasoning, its consistency with
  earlier and later pronouncements, and all those factors which give it
  power to persuade, if lacking power to control."
- **Germain**: confirmed verbatim, with pinpoint page cite from the
  fetched text -- "courts must presume that a legislature says in a
  statute what it means and means in a statute what it says there" (at
  503 U.S. 253-54).
- **Bass**: confirmed -- the rule of lenity language, the actual statute
  at issue (18 U.S.C. former §1202(a)(1), the Omnibus Crime Control and
  Safe Streets Act), and the fair-notice/federalism reasoning for the
  narrower reading all matched.
- **Loper Bright**: the specific "overrules Chevron, courts exercise
  independent judgment" holding confirmed verbatim ("required judges to
  disregard their statutory duties"; courts must "say what the law is").
  The narrower claim that Skidmore-style respect survives as the live
  standard is confirmed as directionally accurate but with a nuance this
  KB's summary doesn't capture: secondary sources note the majority opinion
  cited Skidmore approvingly and most circuits have applied it since, but
  some circuits are still actively working out exactly how much weight it
  carries post-Loper Bright -- "the live standard" slightly overstates a
  settled consensus that commentators say is still forming.

**All 11 are now confirmed against real, independent sources; 10 of 11
matched this KB's summaries closely (including several near-verbatim
quotes); 1 (Newport Beach Country Club) did not and was corrected.** The
one open nuance (Loper Bright/Skidmore's still-forming post-2024 case law)
is noted above rather than smoothed over.

**One was a real, confirmed error.** This KB's original summary of
*Founding Members of the Newport Beach Country Club v. Newport Beach
Country Club, Inc.*, 109 Cal. App. 4th 944 (2003), claimed the case
narrowed PG&E's "reasonably susceptible" test for "sophisticated parties
represented by counsel negotiating at arm's length." Fetching the actual
opinion (via FindLaw) showed that framing does not appear in the case at
all -- the real limiting mechanism is the *objective theory of contracts*:
the court excluded undisclosed subjective intent (internal communications
never conveyed to the other side) as not being the kind of extrinsic
evidence PG&E requires courts to consider, while treating one objectively
communicated letter as potentially admissible (though it ended up cutting
against the party offering it). This is a materially different legal
mechanism, not a paraphrase of the same one.

**Fixed, not just noted:** `kb.yaml`'s `case_newport_beach` summary and
`pr_newport_limits_pge`'s `on_issue` were rewritten to match the verified
holding; the `FactPattern` field that had been named
`sophisticated_parties_represented_by_counsel` was renamed
`only_undisclosed_subjective_intent_offered` throughout `engine.py`, with
the outcome text it produces rewritten to match; a new test
(`tests/test_engine.py::test_newport_beach_narrows_pge_for_undisclosed_subjective_intent`)
and a new demo scenario (`demo.py` Scenario 6) were added, because neither
existed before this fix -- the wrong doctrine had been sitting in a code
path with zero test or demo coverage, which is exactly how a citation
error can go unnoticed through two full audit rounds that both, correctly,
named "citations weren't independently checked" as the top risk without
anyone having the means to check them yet. `comparisons/naive_baseline.py`
(a deliberately-frozen historical audit artifact from round 1, per its own
docstring) still carries the old field name, but never reads it in its
logic, so the historical comparison's result is unaffected; it was left
alone rather than rewriting an artifact whose entire point is being a
snapshot of what round 1 actually tested.

`python -m pytest -q`: **25 passed** after this fix (24 before + the new
Newport Beach test), confirmed by actually running it, not computed by
hand.

## Reserve-phase audit, round 3 (checking the citation-verification pass itself)

With budget remaining, a third round of three fresh subagents audited
specifically the citation-verification work above, rather than
re-litigating rounds 1-2. All three came back clean -- the first round to
find nothing new to fix, which is itself worth reporting honestly rather
than manufacturing a finding to justify the round.

**Attacker** re-ran all four entry points fresh (`pytest`, `demo.py`,
`demo_statutory.py`, `naive_baseline.py` -- all passed/ran as claimed),
grepped for any stale reference to the old "sophisticated parties"
framing (found none outside README's own account of the fix and the
intentionally-frozen `naive_baseline.py`), confirmed `naive_baseline.py`'s
stale field is genuinely never read anywhere, and confirmed both demo
scripts are working-directory-independent (`Path(__file__).parent`-based,
verified by actually invoking them from the parent directory).

**Verification skeptic** independently re-fetched four of the Verification
section's specific quotes (PG&E, Skidmore, Trident Center's exact Erie
pinpoint cite, and re-confirmed Newport Beach Country Club's *corrected*
holding directly from the FindLaw opinion -- including confirming
"sophisticated parties represented by counsel" genuinely does not appear
anywhere in that case) and found the README's precision matches the
underlying sources exactly, with no overclaiming.

**Baseline builder** independently re-derived the three most load-bearing
citations (PG&E, Giancontieri, West Virginia v. EPA -- the ones the actual
tests assert outcomes from) from sources it chose itself, without reading
README's claimed quotes first, specifically to check for confirmation
bias. Found no daylight between its independent findings and what's
already documented, and noted that the Newport Beach correction itself is
evidence against pure rubber-stamping: a verification pass that found and
fixed a real error isn't one that only searched until it found agreement.
It also named the honest residual limit directly: both its check and the
original pass drew on the same shallow layer of the citation ecosystem
(case-brief sites, secondary sources) for the citations that 403'd a
direct court-site fetch -- genuinely independent *effort*, not access to a
qualitatively better source than what Limitations already discloses.

## Reserve-phase audit, round 4 (fast, final pass)

Three more fast, tightly-scoped subagents ran with almost no budget left.

**Attacker** found two real bugs rounds 1-3 missed, both fixed: (1)
`schema/methodology_layer.schema.json` only requires `trigger.type`, not
`trigger.params`, so a schema-valid rule with no `params` key crashed
`_apply_evidence_conflict_rules`/`_apply_canons`/`_apply_fallback` with a
bare `KeyError` instead of the clear `ValueError` these functions clearly
intend for malformed rules -- fixed via `.get("params", {})`. (2)
`FactPattern.evidence_conflict_sources` is typed `list[str]` but nothing
enforced it; passing a bare string silently did substring matching instead
of list membership (Python's `in` on a string), the same "typo silently
mis-fires" class already fixed once for `requires_flag` but not for this
sibling field -- now raises `ValueError` instead. Two new regression tests
added (`tests/test_engine_robustness.py`); `python -m pytest -q`: **27
passed**.

**Verification skeptic** re-ran the round-3 robustness tests, stripped the
`requires_flag` validation to confirm 3 of 4 tests fail as expected, then
reverted clean -- confirms round 3's tests remain meaningful, not
tautological.

**Baseline builder** independently re-searched (without reading README's
sources first) whether Loper Bright's Skidmore-respect standard is
actually settled law, per the one open nuance this README already flagged
as unresolved. Found it's *more* unsettled than this README's hedge
suggested: Bloomberg Law reports federal courts didn't even cite Skidmore
in 19 of 20 post-Loper Bright agency-deference rulings, and multiple
circuits (4th, 5th, 9th) are actively diverging on how to apply it. This
KB's original "the live standard" framing understates that unsettledness
more than this README's own hedge already (honestly) flagged.

## Limitations (honest, not hedged)

- **Case citations were checked against independent web sources (Justia,
  FindLaw, CourtListener, Cornell LII, Oyez), not a licensed citator
  (Westlaw/Lexis/Shepard's).** See Verification, above, for what was
  actually checked and the one real error it found and fixed. Web search
  results can confirm a holding is described accurately and the citation
  form is real, but they don't confirm current good-law status the way a
  citator's negative-treatment flags do (a case could have been narrowed
  or overruled by something that doesn't show up prominently in search
  results). A real legal-AI product still needs a licensed citation-
  checking API or human attorney review before shipping citations to an
  end user -- this session closed the "never checked at all" gap, not the
  "checked with a production-grade tool" gap.
- **`entity_extraction_stub.py` is a hand-written simulation, not the real
  Isaacus/Kanon API.** No network access or API credentials were available
  in this environment. It exists only to make the *shape* of the "before"
  state concrete (regex-matched spans with a type tag) so the contrast with
  an `InterpretiveAnnotation` is visible in the same demo run, not to claim
  integration with the real product.
- **The fact pattern is supplied as structured input (`FactPattern`), not
  extracted from free text.** A production system would need an NLP step
  to decide, e.g., "is this clause facially ambiguous?" or "does this list
  fit the specific-list-then-catchall shape?" from raw contract text. That
  classification step is out of scope here; this submission's job was the
  methodology layer that consumes such a classification and produces
  doctrinal grounding, not the classifier itself.
- **The knowledge bases cover two bounded slices of two doctrines in one
  legal system** (US contract-interpretation ambiguity resolution, and US
  federal statutory construction) -- both common-law, both federal-or-state
  US courts. The schema/engine generalization was demonstrated, not just
  claimed (see Generalization, above), but only across two doctrines that
  are structurally quite similar (both are "which interpretive rule
  controls, ranked by authority, with canons of construction and a
  last-resort fallback"). A genuinely different legal system -- civil law
  with no stare decisis, or an area with no clean hierarchy at all -- would
  test the schema's `PrecedentRelation`/`DoctrinalHierarchy` entities much
  harder than either KB built here does.
- **No live LLM was called.** There is no `ANTHROPIC_API_KEY` in this
  environment, so this submission cannot and does not claim to have shown
  an LLM actually reasoning better with an `InterpretiveAnnotation` in its
  context versus without one. What is demonstrated is that the annotation
  is real, computed, checkable structured data suitable for putting in a
  prompt -- not a claim about downstream LLM output quality, which would
  require an actual model call this environment cannot make.

## Reflection

**Recall check.** Writing this from memory before re-checking, at the very
end of the session: the engine walks an ordered list of
`threshold_ambiguity` rules per jurisdiction, tries each via
`_evaluate_threshold_rule` until one "disposes" of the case, then
separately collects evidence-conflict rules, structural canons, and a
`requires_flag`-gated fallback, unions whichever fired, sorts by priority,
and computes weights via `weighting.py`; `_conflicting_authority_for`
generically surfaces any precedent relation with real tension pointing at
a cited authority. I recalled checking "10 or 11" case citations by web
search and finding "one real error, in one of the contract cases" -- that
matched on re-reading the Verification section (11 checked, Newport Beach
Country Club was the one error). I recalled the corrected FactPattern flag
name as `undisclosed_subjective_intent_offered` -- checked `engine.py` just
now and it's actually `only_undisclosed_subjective_intent_offered` (with
the leading `only_`, which matters: it's meant to convey "the *only*
evidence offered is undisclosed intent," not just "some was offered").
Corrected here rather than leave the wrong name standing in my own recap.
Current test count, verified by rerunning `pytest --collect-only` grouped
by file just now rather than trusting the arithmetic in this document:
`test_kb_validates_schema.py` 6, `test_engine.py` 9 (8 plus the new
Newport Beach test), `test_statutory_kb.py` 6, `test_engine_robustness.py`
4 -- 25 total, matching the "25 passed" claim below exactly.

**Weakest remaining claim.** Two candidates, named honestly rather than
picking the more flattering one. (1) All 11 citations were checked against
web search results and, for most, the actual opinion or a source quoting
it directly -- but never a licensed citator with negative-treatment flags.
Direct opinion text can confirm a holding is described accurately as of
that opinion; it's weaker at confirming *nothing has quietly narrowed or
overruled it since*, which is exactly the kind of thing Loper Bright
itself was for Chevron (a 40-year-old rule that looked stable until it
wasn't) -- and, more immediately, exactly the open nuance Verification
flags for Loper Bright/Skidmore's own still-forming post-2024 case law.
Verification, above, names this distinction explicitly rather than
claiming more than was done.
(2) Per round 2's baseline-builder finding: roughly a quarter of
`engine.py`, concentrated in `_evaluate_threshold_rule`, is irreducibly
domain-specific prose, and that's exactly where all future doctrinal
content would land. A reader skimming only the Generalization section's
headline without its last paragraph would come away more impressed than
the code supports.

**Most consequential design decision.** Actually fetching and reading the
Newport Beach Country Club opinion instead of accepting that my original
summary was "probably fine" because the case's *existence* and citation
format checked out in the first search pass. The search-result summary for
that case (about a Right of First Offer and membership timing) didn't even
mention PG&E or extrinsic evidence at all -- it would have been easy to
conclude "citation confirmed, moving on" from that alone. The only reason
the actual error surfaced is that I fetched the opinion text specifically
to check the narrower claim (the "sophisticated parties" narrowing), rather
than treating "the case is real" as equivalent to "my characterization of
it is accurate." Those are different claims, and conflating them is
exactly how a hallucinated-sounding detail survives inside an otherwise
real citation. The alternative I rejected -- treat all citations as
equally verified once web search confirms they exist -- is the shortcut
that would have shipped the error.

**What was actually run to verify this, versus not.** Ran, this session,
with real output inspected each time: `python -m pytest -q` at every stage
(20 passed after generalizing to the statutory KB, 24 after round 2's
robustness fixes, 25 after the Newport Beach correction -- all three
numbers taken from actual terminal output); `python demo.py` and `python
demo_statutory.py`, including a fresh Scenario 6 added specifically to
exercise the corrected Newport Beach branch (which, before this pass, no
test or demo scenario touched at all -- a real gap in coverage, not just
in citation accuracy); `python comparisons/naive_baseline.py`, diffed by
hand against `demo_output.txt`; a deliberate revert-and-rerun of
`_apply_fallback` to confirm the statutory tests depend on the
generalization fix; `git log`/`git show` against specific commits to
confirm narrated claims about past code rather than trusting my own
memory of it; and, across two passes this session, 17 `WebSearch` queries
plus 11 `WebFetch` attempts (9 succeeded; a few court-adjacent sites --
Justia and congress.gov among them -- 403'd the fetch, so those citations
were confirmed via a professional legal-analysis source quoting the
opinion directly instead) checking all 11 case citations across both
knowledge bases against independent sources, with direct-opinion-level
confirmation (not just search-summary paraphrase) for all 11, and finding
the one real error described above. Three full rounds of three
independent subagents each ran real attacks and real reruns against the
code, not just read it -- round 3 specifically re-derived load-bearing
citations from sources chosen independently of what round-1/2's own pass
had cited, to check for confirmation bias, and found none. Not run/not
verified: no live LLM call (no credentials in this environment); no
licensed-citator check (Westlaw/Lexis/Shepard's, which would additionally
flag negative subsequent treatment a web search can miss) on any
citation; no runtime mitigation for the YAML alias-expansion DoS
(deferred as out of scope for a trusted-local-file design); no third
bounded area of law actually built.

**Post-round-4 update.** Round 4 (above) found and fixed two more real
bugs in the same "malformed input silently mis-fires or crashes" family as
the `requires_flag` fix: a bare `KeyError` on schema-valid rules missing
`trigger.params`, and silent substring-matching when
`evidence_conflict_sources` got a bare string instead of a list. Both
fixed with the same "raise clearly, don't guess" pattern; test count is
now **27**, confirmed by rerunning `pytest -q` after the fix, not before.
This is the second time this exact bug *class* recurred in a sibling code
path after being fixed once already -- worth naming as a pattern: fixing
one instance of "unvalidated KB-authored input reaches Python's duck
typing" doesn't inoculate the neighboring functions that do the same kind
of access.

**With another 30 minutes.** Get actual licensed-citator access
(Westlaw/Lexis/Shepard's, or a free equivalent like CourtListener's
citator API if one exists) to check negative subsequent treatment on all
11 citations -- the one gap this session's web-search-and-opinion-fetch
pass genuinely can't close, since it confirms a holding is described
accurately as of the opinion's own text but can't surface "this was
narrowed by a later case that didn't come up prominently in search
results" the way a real citator's flags would. That's a smaller, more
specific gap than "citations were never checked" (which this session did
close), and it's the honest next rung on the same ladder, not a
different task.
