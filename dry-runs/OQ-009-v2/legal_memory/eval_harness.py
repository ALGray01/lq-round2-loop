"""Head-to-head test: three memory architectures on the same 7 test cases.

  - GraphMemoryStore     the proposed design (bi-temporal + matter-partitioned)
  - CompartmentMemoryStore  stands in for Honcho/Cognee-style layered
                        compartments: matter-partitioned like the graph, but
                        keeps only the current layer -- no as_of parameter
                        exists in its API at all.
  - VectorBaseline       flat TF-IDF RAG over raw transcripts -- no
                        partitioning guarantee, no temporal axis.

Seven test cases probe three properties a weeks-long legal-research memory
needs:
  1-2. Current-vs-superseded fact retrieval (statute amendment)
  3-4. Point-in-time reconstruction (precedent later overturned)
  5.   Plain supersession (party name correction) -- a control case where the
       baselines are given a fair chance to win, so the eval isn't rigged to
       make them fail everywhere.
  6.   Matter isolation under realistic tagging drift (an untagged intake
       session).
  7.   Matter isolation when a filter is skipped outright (a routing bug).

Run: python -m legal_memory.eval_harness
"""
from __future__ import annotations

from dataclasses import dataclass

from legal_memory.scenario import build_facts, build_sessions
from legal_memory.graph_store import GraphMemoryStore
from legal_memory.compartment_store import CompartmentMemoryStore
from legal_memory.vector_baseline import VectorBaseline


@dataclass
class TestCase:
    tid: str
    description: str
    matter_id: str
    query_text: str
    # graph params
    as_of_transaction_session: int | None
    as_of_valid_time: int | None
    expected_fact_ids: set[str]
    forbidden_fact_ids: set[str]
    # baseline params
    baseline_matter_filter: str | None
    baseline_variant: str  # "query" or "recency"
    baseline_as_of_session: int | None
    expected_session_ids: set[int]
    forbidden_session_ids: set[int]


def build_test_cases() -> list[TestCase]:
    return [
        TestCase(
            tid="T1-current-sol",
            description="Current statute of limitations after the amendment",
            matter_id="doe_v_acme",
            query_text="What is the current statute of limitations for Doe's breach of contract claim against Acme?",
            as_of_transaction_session=None, as_of_valid_time=None,
            expected_fact_ids={"A-sol-v2"}, forbidden_fact_ids={"A-sol-v1"},
            baseline_matter_filter="doe_v_acme", baseline_variant="query", baseline_as_of_session=None,
            expected_session_ids={7}, forbidden_session_ids=set(),
        ),
        TestCase(
            tid="T2-point-in-time-sol",
            description="What we believed the SOL was before the amendment was learned (as of session 4)",
            matter_id="doe_v_acme",
            query_text="As of this point in the matter, what do we believe the statute of limitations is for Doe's claim?",
            as_of_transaction_session=4, as_of_valid_time=None,
            expected_fact_ids={"A-sol-v1"}, forbidden_fact_ids={"A-sol-v2"},
            baseline_matter_filter="doe_v_acme", baseline_variant="query", baseline_as_of_session=4,
            expected_session_ids={1}, forbidden_session_ids={7},
        ),
        TestCase(
            tid="T3-precedent-current",
            description="Whether Smith v. Jones is still good law, now (after it was overturned)",
            matter_id="doe_v_acme",
            query_text="Is Smith v. Jones still good law for the demand-letter tolling argument?",
            as_of_transaction_session=None, as_of_valid_time=None,
            expected_fact_ids={"A-precedent-v2"}, forbidden_fact_ids={"A-precedent-v1", "A-precedent-v1-capped"},
            baseline_matter_filter="doe_v_acme", baseline_variant="query", baseline_as_of_session=None,
            expected_session_ids={10}, forbidden_session_ids=set(),
        ),
        TestCase(
            tid="T4-point-in-time-precedent",
            description="Whether Smith was considered good law as of week 3 / session 6, before the overturning was learned",
            matter_id="doe_v_acme",
            query_text="As of this point in the matter, is Smith v. Jones considered good law for tolling?",
            as_of_transaction_session=6, as_of_valid_time=None,
            expected_fact_ids={"A-precedent-v1"}, forbidden_fact_ids={"A-precedent-v2"},
            baseline_matter_filter="doe_v_acme", baseline_variant="recency", baseline_as_of_session=6,
            expected_session_ids={2}, forbidden_session_ids={10},
        ),
        TestCase(
            tid="T5-party-name-control",
            description="Party name correction -- control case, baseline is given a fair shot",
            matter_id="doe_v_acme",
            query_text="What is the defendant's correct legal name?",
            as_of_transaction_session=None, as_of_valid_time=None,
            expected_fact_ids={"A-party-v2"}, forbidden_fact_ids={"A-party-v1"},
            baseline_matter_filter="doe_v_acme", baseline_variant="query", baseline_as_of_session=None,
            expected_session_ids={4}, forbidden_session_ids=set(),
        ),
        TestCase(
            tid="T6-isolation-tagging-drift",
            description="Matter-scoped query hitting a source session that was never tagged with a matter_id",
            matter_id="estate_wu",
            query_text="What is the applicable statute of limitations discussed in this matter?",
            as_of_transaction_session=None, as_of_valid_time=None,
            expected_fact_ids={"B-vendor-sol"}, forbidden_fact_ids={"A-sol-v1", "A-sol-v2"},
            baseline_matter_filter="estate_wu", baseline_variant="query", baseline_as_of_session=None,
            expected_session_ids={3}, forbidden_session_ids={1, 7},
        ),
        TestCase(
            tid="T7-isolation-no-filter",
            description="What a skipped/forgotten matter filter exposes (routing bug), scoped as Matter A",
            matter_id="doe_v_acme",
            query_text="statute of limitations Acme 3 years breach of contract",
            as_of_transaction_session=None, as_of_valid_time=None,
            expected_fact_ids={"A-sol-v2"}, forbidden_fact_ids={"B-vendor-sol"},
            baseline_matter_filter=None, baseline_variant="query", baseline_as_of_session=None,
            expected_session_ids={7}, forbidden_session_ids={3},
        ),
    ]


@dataclass
class CaseResult:
    tid: str
    system: str
    passed: bool
    reason: str
    top_results: list[str]


def score_graph(tc: TestCase, store: GraphMemoryStore) -> CaseResult:
    results = store.query(
        tc.matter_id, tc.query_text,
        as_of_transaction_session=tc.as_of_transaction_session,
        as_of_valid_time=tc.as_of_valid_time,
        top_k=3,
    )
    ids = [f.fact_id for f in results]
    forbidden_hit = tc.forbidden_fact_ids & set(ids)
    top1_ok = bool(ids) and ids[0] in tc.expected_fact_ids
    if forbidden_hit:
        return CaseResult(tc.tid, "graph", False,
                           f"forbidden fact(s) surfaced: {sorted(forbidden_hit)}", ids)
    if not top1_ok:
        return CaseResult(tc.tid, "graph", False,
                           f"top-1 was {ids[0] if ids else 'EMPTY'}, expected one of {sorted(tc.expected_fact_ids)}", ids)
    return CaseResult(tc.tid, "graph", True, "top-1 matched, no forbidden facts", ids)


def score_compartment(tc: TestCase, store: CompartmentMemoryStore) -> CaseResult:
    """CompartmentMemoryStore.query() has no as_of parameter at all -- a
    point-in-time test case (T2, T4) is scored by calling the API it
    actually offers (current-layer only) and checking whether that
    structurally-forced "now" answer happens to satisfy a question that
    asked about the past. It should not, by design."""
    results = store.query(tc.matter_id, tc.query_text, top_k=3)
    ids = [f.fact_id for f in results]
    forbidden_hit = tc.forbidden_fact_ids & set(ids)
    top1_ok = bool(ids) and ids[0] in tc.expected_fact_ids
    if forbidden_hit:
        return CaseResult(tc.tid, "compartment", False,
                           f"forbidden fact(s) surfaced: {sorted(forbidden_hit)}", ids)
    if not top1_ok:
        return CaseResult(tc.tid, "compartment", False,
                           f"top-1 was {ids[0] if ids else 'EMPTY'}, expected one of {sorted(tc.expected_fact_ids)}", ids)
    return CaseResult(tc.tid, "compartment", True, "top-1 matched, no forbidden facts", ids)


def score_baseline(tc: TestCase, store: VectorBaseline) -> CaseResult:
    if tc.baseline_variant == "recency":
        results = store.query_recency_biased(
            tc.query_text, matter_filter=tc.baseline_matter_filter,
            as_of_session=tc.baseline_as_of_session, top_k=3)
    else:
        results = store.query(tc.query_text, matter_filter=tc.baseline_matter_filter, top_k=3)
    ids = [s.session_id for s in results]
    forbidden_hit = tc.forbidden_session_ids & set(ids)
    if forbidden_hit:
        return CaseResult(tc.tid, "baseline", False,
                           f"forbidden session(s) surfaced: {sorted(forbidden_hit)}", [str(i) for i in ids])
    if not ids:
        return CaseResult(tc.tid, "baseline", False, "no results returned", [])
    top1_ok = ids[0] in tc.expected_session_ids
    if not top1_ok:
        return CaseResult(tc.tid, "baseline", False,
                           f"top-1 was session {ids[0]}, expected one of {sorted(tc.expected_session_ids)}",
                           [str(i) for i in ids])
    return CaseResult(tc.tid, "baseline", True, "top-1 matched, no forbidden sessions", [str(i) for i in ids])


def run(enforce_time: bool = True, enforce_matter: bool = True
        ) -> tuple[list[CaseResult], list[CaseResult], list[CaseResult]]:
    facts = build_facts()
    sessions = build_sessions()
    graph = GraphMemoryStore(facts, enforce_time=enforce_time, enforce_matter=enforce_matter)
    compartment = CompartmentMemoryStore(facts)
    baseline = VectorBaseline(sessions)

    graph_results = []
    compartment_results = []
    baseline_results = []
    for tc in build_test_cases():
        graph_results.append(score_graph(tc, graph))
        compartment_results.append(score_compartment(tc, compartment))
        baseline_results.append(score_baseline(tc, baseline))
    return graph_results, compartment_results, baseline_results


def format_report(graph_results: list[CaseResult], compartment_results: list[CaseResult],
                   baseline_results: list[CaseResult]) -> str:
    lines = []
    cases = {tc.tid: tc for tc in build_test_cases()}
    lines.append(f"{'TEST':<28}{'GRAPH':<8}{'COMPART.':<10}{'BASELINE':<10}NOTES")
    lines.append("-" * 110)
    for g, c, b in zip(graph_results, compartment_results, baseline_results):
        tc = cases[g.tid]
        lines.append(f"{g.tid:<28}{'PASS' if g.passed else 'FAIL':<8}"
                      f"{'PASS' if c.passed else 'FAIL':<10}{'PASS' if b.passed else 'FAIL':<10}{tc.description}")
        lines.append(f"    graph:       {g.reason}  (top-k: {g.top_results})")
        lines.append(f"    compartment: {c.reason}  (top-k: {c.top_results})")
        lines.append(f"    baseline:    {b.reason}  (top-k: {b.top_results})")
    g_pass = sum(r.passed for r in graph_results)
    c_pass = sum(r.passed for r in compartment_results)
    b_pass = sum(r.passed for r in baseline_results)
    lines.append("-" * 110)
    lines.append(f"TOTAL: graph {g_pass}/{len(graph_results)}   "
                 f"compartment {c_pass}/{len(compartment_results)}   "
                 f"baseline {b_pass}/{len(baseline_results)}")
    return "\n".join(lines)


def _sanity_check(label: str, *, enforce_time: bool, enforce_matter: bool,
                   originally_passing: set[str]) -> None:
    """FAILURE-CLASSES #4: a scorer that never fails anything proves nothing.
    Re-run with one structural axis deliberately disabled and confirm the
    SAME scorer flips the cases that axis is responsible for back to FAIL."""
    print(f"\n=== Sanity check: {label} ===\n")
    broken_results, _, _ = run(enforce_time=enforce_time, enforce_matter=enforce_matter)
    now_failing = {r.tid for r in broken_results if r.tid in originally_passing and not r.passed}
    for r in broken_results:
        if r.tid in originally_passing:
            status = "PASS" if r.passed else "FAIL"
            print(f"  {r.tid}: {status} -- {r.reason}")
    if now_failing == originally_passing:
        print("  Confirmed: scorer correctly flags every previously-passing case in this "
              "axis as failing once that axis's enforcement is removed.")
    elif now_failing:
        print(f"  Partially confirmed: {sorted(now_failing)} now fail, but "
              f"{sorted(originally_passing - now_failing)} still pass unexpectedly -- investigate.")
    else:
        print("  WARNING: scorer did not detect the induced break -- investigate the scorer.")


if __name__ == "__main__":
    print("=== Head-to-head: bi-temporal graph vs. layered-compartment store vs. flat vector RAG ===\n")
    graph_results, compartment_results, baseline_results = run()
    print(format_report(graph_results, compartment_results, baseline_results))

    _sanity_check(
        "break the graph store's TIME enforcement (FAILURE-CLASSES #4)",
        enforce_time=False, enforce_matter=True,
        originally_passing={"T2-point-in-time-sol", "T4-point-in-time-precedent"},
    )
    _sanity_check(
        "break the graph store's MATTER-PARTITION enforcement (FAILURE-CLASSES #4)",
        enforce_time=True, enforce_matter=False,
        originally_passing={"T2-point-in-time-sol", "T6-isolation-tagging-drift", "T7-isolation-no-filter"},
    )
