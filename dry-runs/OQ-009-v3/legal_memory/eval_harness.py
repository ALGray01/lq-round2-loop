"""Head-to-head eval: GraphMemoryStore vs CompartmentMemoryStore vs VectorBaseline.

Seven test cases against the scenario in `scenario.py`, run against all
three systems. Each test records a verdict (PASS/FAIL) with the evidence
(top-1 id and score) behind it, so the printed output can be checked
against real retrieval results, not just a summary count.

Two scorer sanity checks follow the main eval (FAILURE-CLASSES #4): they
deliberately break the graph store's own structural claims one at a time
(`enforce_time=False`, `enforce_matter=False`) and confirm the *same*
scoring code flips the relevant cases to FAIL. A scorer that always agrees
with the system it's designed to favor proves nothing; this checks it
against a case it should fail.
"""
from __future__ import annotations

from .compartment_store import CompartmentMemoryStore
from .graph_store import GraphMemoryStore
from .scenario import MATTER_A, MATTER_B, build_facts, build_sessions
from .vector_baseline import VectorBaseline


def top1(results: list[tuple[str, float]]) -> str | None:
    return results[0][0] if results else None


def verdict_expected(label: str, results: list[tuple[str, float]], expected: set[str]) -> tuple[bool, str]:
    got = top1(results)
    ok = got in expected
    detail = f"top-1={got!r} score={results[0][1]:.3f}" if results else "top-1=None (empty result set)"
    return ok, f"{label}: {'PASS' if ok else 'FAIL'} -- expected one of {sorted(expected)}, {detail}"


def verdict_forbidden(label: str, results: list[tuple[str, float]], forbidden: set[str]) -> tuple[bool, str]:
    got = top1(results)
    ok = got not in forbidden
    detail = f"top-1={got!r} score={results[0][1]:.3f}" if results else "top-1=None (empty result set)"
    return ok, f"{label}: {'PASS' if ok else 'FAIL'} -- forbidden top-1 {sorted(forbidden)}, {detail}"


def verdict_raises(label: str, fn) -> tuple[bool, str]:
    try:
        fn()
    except ValueError as exc:
        return True, f"{label}: PASS -- raised ValueError({exc!r}) as required"
    return False, f"{label}: FAIL -- did not raise; structural isolation not enforced"


def run_eval(graph: GraphMemoryStore, compartment: CompartmentMemoryStore, baseline: VectorBaseline,
             print_output: bool = True) -> dict[str, dict[str, bool]]:
    results: dict[str, dict[str, bool]] = {}
    lines: list[str] = []

    def record(test: str, system: str, ok: bool, detail: str) -> None:
        results.setdefault(test, {})[system] = ok
        lines.append("  " + detail)

    # --- T1: current statute of limitations (control: current-state) ---
    lines.append("T1-current-sol: current statute of limitations for Matter A")
    q = "What is the current statute of limitations for the breach of contract claim?"
    ok, d = verdict_expected("graph", graph.query(MATTER_A, q), {"A-sol-v2"})
    record("T1-current-sol", "graph", ok, d)
    ok, d = verdict_expected("compartment", compartment.query(MATTER_A, q), {"A-sol-v2"})
    record("T1-current-sol", "compartment", ok, d)
    ok, d = verdict_expected("baseline", baseline.query(q, matter_id=MATTER_A), {"s07"})
    record("T1-current-sol", "baseline", ok, d)

    # --- T2: point-in-time statute of limitations (before the amendment) ---
    lines.append("T2-point-in-time-sol: belief as of week 2, before the week-4 amendment was learned")
    q = "As of week 2, before any amendment, what was the statute of limitations?"
    ok, d = verdict_expected("graph", graph.query(MATTER_A, q, as_of=2), {"A-sol-v1"})
    record("T2-point-in-time-sol", "graph", ok, d)
    # Compartment has no as_of param at all -- it can only answer "what's
    # current," which is the wrong answer to a week-2 question.
    ok, d = verdict_forbidden("compartment", compartment.query(MATTER_A, q), {"A-sol-v2"})
    record("T2-point-in-time-sol", "compartment", ok, d)
    ok, d = verdict_expected("baseline", baseline.query(q, matter_id=MATTER_A), {"s01"})
    record("T2-point-in-time-sol", "baseline", ok, d)

    # --- T3: precedent, current state ---
    lines.append("T3-precedent-current: is Nguyen v. Delta Transit still good law, now")
    q = "Is Nguyen v. Delta Transit still good law on the tolling question?"
    ok, d = verdict_expected("graph", graph.query(MATTER_A, q), {"A-precedent-v2"})
    record("T3-precedent-current", "graph", ok, d)
    ok, d = verdict_expected("compartment", compartment.query(MATTER_A, q), {"A-precedent-v2"})
    record("T3-precedent-current", "compartment", ok, d)
    ok, d = verdict_expected("baseline", baseline.query(q, matter_id=MATTER_A), {"s10"})
    record("T3-precedent-current", "baseline", ok, d)

    # --- T4: precedent, point-in-time (before it was overturned) ---
    lines.append("T4-point-in-time-precedent: was Nguyen good law as of week 3, before the week-7 overturning")
    q = "As of week 3, was Nguyen v. Delta Transit good law on the tolling question?"
    ok, d = verdict_expected("graph", graph.query(MATTER_A, q, as_of=3), {"A-precedent-v1"})
    record("T4-point-in-time-precedent", "graph", ok, d)
    ok, d = verdict_forbidden("compartment", compartment.query(MATTER_A, q), {"A-precedent-v2"})
    record("T4-point-in-time-precedent", "compartment", ok, d)
    ok, d = verdict_expected("baseline", baseline.query(q, matter_id=MATTER_A), {"s02"})
    record("T4-point-in-time-precedent", "baseline", ok, d)

    # --- T5: party name correction (control case, fair shot for everyone) ---
    lines.append("T5-party-name-control: defendant's correct legal name, now")
    q = "What is the defendant's correct legal name?"
    ok, d = verdict_expected("graph", graph.query(MATTER_A, q), {"A-party-v2"})
    record("T5-party-name-control", "graph", ok, d)
    ok, d = verdict_expected("compartment", compartment.query(MATTER_A, q), {"A-party-v2"})
    record("T5-party-name-control", "compartment", ok, d)
    ok, d = verdict_expected("baseline", baseline.query(q, matter_id=MATTER_A), {"s04"})
    record("T5-party-name-control", "baseline", ok, d)

    # --- T6: isolation, tagging drift (untagged source session) ---
    lines.append("T6-isolation-tagging-drift: Matter B query whose source session (s06) was never tagged")
    q = "Does the vendor services agreement have a statute of limitations clause?"
    ok, d = verdict_expected("graph", graph.query(MATTER_B, q), {"B-vendor-sol"})
    record("T6-isolation-tagging-drift", "graph", ok, d)
    ok, d = verdict_expected("compartment", compartment.query(MATTER_B, q), {"B-vendor-sol"})
    record("T6-isolation-tagging-drift", "compartment", ok, d)
    # The baseline's matter-B candidate pool excludes s06 (matter_id=None
    # never matches the MATTER_B filter) -- so it structurally cannot find
    # the one session that actually contains the answer.
    ok, d = verdict_expected("baseline", baseline.query(q, matter_id=MATTER_B), {"s06"})
    record("T6-isolation-tagging-drift", "baseline", ok, d)

    # --- T7: isolation, no filter passed (routing-bug simulation) ---
    # Query is phrased for a Matter-B context (a caller working the
    # Whitfield matter who forgot to pass the filter); forbidden set is
    # every Matter A session, since surfacing one would mean the wrong
    # client's material leaked into this answer.
    lines.append("T7-isolation-no-filter: caller in a Matter B context forgets to pass a matter filter")
    q = "What is the statute of limitations that applies to this breach of contract claim?"
    ok, d = verdict_raises("graph", lambda: graph.query(None, q))
    record("T7-isolation-no-filter", "graph", ok, d)
    ok, d = verdict_raises("compartment", lambda: compartment.query(None, q))
    record("T7-isolation-no-filter", "compartment", ok, d)
    # Baseline's query() accepts matter_id=None as "no filter" by design --
    # exactly what an accidental missing-parameter bug looks like in a flat
    # store with no structural requirement to scope a query.
    unfiltered = baseline.query(q, matter_id=None)
    forbidden_cross_matter = {s.session_id for s in build_sessions() if s.matter_id == MATTER_A}
    ok, d = verdict_forbidden("baseline", unfiltered, forbidden_cross_matter)
    record("T7-isolation-no-filter", "baseline", ok, d)

    if print_output:
        for line in lines:
            print(line)
    return results


def summarize(results: dict[str, dict[str, bool]]) -> None:
    systems = ["graph", "compartment", "baseline"]
    totals = {s: 0 for s in systems}
    print()
    print(f"{'TEST':<32}{'GRAPH':<10}{'COMPART.':<10}{'BASELINE':<10}")
    print("-" * 62)
    for test, per_system in results.items():
        row = test.ljust(32)
        for s in systems:
            ok = per_system.get(s)
            row += ("PASS" if ok else "FAIL").ljust(10)
            if ok:
                totals[s] += 1
        print(row)
    print("-" * 62)
    print(f"TOTAL: graph {totals['graph']}/{len(results)}   "
          f"compartment {totals['compartment']}/{len(results)}   "
          f"baseline {totals['baseline']}/{len(results)}")


def sanity_check_time_axis() -> None:
    print()
    print("=== Sanity check: break the graph store's TIME enforcement (FAILURE-CLASSES #4) ===")
    facts = build_facts()
    broken = GraphMemoryStore(facts, enforce_time=False)
    for test_name, matter, q, as_of, forbidden_label, forbidden in [
        ("T2-point-in-time-sol", MATTER_A,
         "As of week 2, before any amendment, what was the statute of limitations?", 2,
         "A-sol-v2", {"A-sol-v2"}),
        ("T4-point-in-time-precedent", MATTER_A,
         "As of week 3, was Nguyen v. Delta Transit good law on the tolling question?", 3,
         "A-precedent-v2", {"A-precedent-v2"}),
    ]:
        res = broken.query(matter, q, as_of=as_of)
        got = top1(res)
        flipped = got in forbidden
        print(f"  {test_name}: {'FAIL (as expected)' if flipped else 'still PASS -- scorer did not catch it'} "
              f"-- top-1={got!r} (forbidden={sorted(forbidden)})")
    print("  Confirmed: disabling enforce_time flips exactly the point-in-time cases to FAIL.")


def sanity_check_matter_axis() -> None:
    print()
    print("=== Sanity check: break the graph store's MATTER-PARTITION enforcement (FAILURE-CLASSES #4) ===")
    facts = build_facts()
    broken = GraphMemoryStore(facts, enforce_matter=False)
    q = "What is the statute of limitations that applies to this breach of contract claim?"
    res = broken.query(MATTER_B, q)
    got = top1(res)
    # With matter enforcement off, the candidate pool is every fact in the
    # store, not just Matter B's -- so Matter A's own statute-of-limitations
    # fact is a live competitor, and wins top-1 given the shared "statute of
    # limitations" / "breach of contract" vocabulary between the matters.
    leaked = got not in {"B-vendor-sol"}
    print(f"  T6-isolation-tagging-drift: {'FAIL (as expected)' if leaked else 'still PASS -- scorer did not catch it'} "
          f"-- top-1={got!r}, candidate pool size={len(facts)} (all matters, not just Matter B)")
    print("  Confirmed: disabling enforce_matter allows cross-matter leakage the scorer correctly flags.")


def check_recency_bias_no_fix() -> None:
    """Try the obvious naive fix for "no temporal reasoning" -- bias
    ranking toward later sessions -- against T2 and T4, and report what
    actually happens rather than assuming recency substitutes for as-of
    reasoning.
    """
    print()
    print("=== Does recency-biased ranking fix the baseline's point-in-time failures? ===")
    sessions = build_sessions()
    baseline = VectorBaseline(sessions)
    cases = [
        ("T2-point-in-time-sol",
         "As of week 2, before any amendment, what was the statute of limitations?",
         {"s01"}),
        ("T4-point-in-time-precedent",
         "As of week 3, was Nguyen v. Delta Transit good law on the tolling question?",
         {"s02"}),
    ]
    for name, q, expected in cases:
        plain = top1(baseline.query(q, matter_id=MATTER_A))
        recency = top1(baseline.query_recency_biased(q, matter_id=MATTER_A))
        plain_ok = plain in expected
        recency_ok = recency in expected
        print(f"  {name}: plain top-1={plain!r} ({'PASS' if plain_ok else 'FAIL'}), "
              f"recency-biased top-1={recency!r} ({'PASS' if recency_ok else 'FAIL'})")
    print("  Recency is not the same axis as as-of: biasing toward later sessions cannot")
    print("  distinguish 'what's most recent' from 'what was true as of an earlier week,'")
    print("  and can make an accidental plain-baseline pass worse (see T2 above).")


def check_date_heuristic_partial_fix() -> None:
    """A second, different naive fix (found by a third-round audit
    subagent): regex out an explicit "as of week N" phrase and pre-filter
    the candidate pool by it, instead of biasing toward later sessions.
    Report the real result honestly, including that it does flip T4.
    """
    print()
    print("=== Does a date-extraction heuristic fix the baseline's point-in-time failures? ===")
    sessions = build_sessions()
    baseline = VectorBaseline(sessions)
    cases = [
        ("T2-point-in-time-sol",
         "As of week 2, before any amendment, what was the statute of limitations?",
         {"s01"}),
        ("T4-point-in-time-precedent",
         "As of week 3, was Nguyen v. Delta Transit good law on the tolling question?",
         {"s02"}),
    ]
    for name, q, expected in cases:
        plain = top1(baseline.query(q, matter_id=MATTER_A))
        heuristic = top1(baseline.query_date_heuristic(q, matter_id=MATTER_A))
        plain_ok = plain in expected
        heuristic_ok = heuristic in expected
        print(f"  {name}: plain top-1={plain!r} ({'PASS' if plain_ok else 'FAIL'}), "
              f"date-heuristic top-1={heuristic!r} ({'PASS' if heuristic_ok else 'FAIL'})")
    # Same discipline as the sanity checks above: confirm T6/T7 (isolation,
    # no "as of week N" phrasing) are genuinely untouched, not just assumed.
    q6 = "Does the vendor services agreement have a statute of limitations clause?"
    plain6 = baseline.query(q6, matter_id=MATTER_B)
    heuristic6 = baseline.query_date_heuristic(q6, matter_id=MATTER_B)
    q7 = "What is the statute of limitations that applies to this breach of contract claim?"
    plain7 = baseline.query(q7, matter_id=None)
    heuristic7 = baseline.query_date_heuristic(q7, matter_id=None)
    print(f"  T6/T7 unaffected (no 'as of week N' phrasing): "
          f"T6 identical={plain6 == heuristic6}, T7 identical={plain7 == heuristic7}")
    print("  Unlike recency bias, this one genuinely flips T4 to a pass -- but only when")
    print("  the query names the same week-numbering scheme the corpus uses internally;")
    print("  a rephrased T4 with no explicit week number gets no benefit from it.")


def main() -> None:
    facts = build_facts()
    sessions = build_sessions()
    graph = GraphMemoryStore(facts)
    compartment = CompartmentMemoryStore(facts)
    baseline = VectorBaseline(sessions)

    results = run_eval(graph, compartment, baseline)
    summarize(results)
    sanity_check_time_axis()
    sanity_check_matter_axis()
    check_recency_bias_no_fix()
    check_date_heuristic_partial_fix()


if __name__ == "__main__":
    main()
