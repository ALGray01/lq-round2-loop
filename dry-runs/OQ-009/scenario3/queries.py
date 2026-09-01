"""Ground-truth queries for scenario3 -- authored the same way as
scenario/queries.py and scenario2/queries.py: read scenario3/timeline.py,
reason about what's actually true at each date, write the expected answer
down before running any system.
"""
from scenario.queries import Query  # reuse the same dataclass shape
from scenario3.timeline import CARTER, REYES

QUERIES = [
    Query(
        id="R3-Q1-supersession-current",
        matter_id=CARTER, as_of="2026-02-10",
        text="when's the custody hearing",
        expected_fact_id="cc-hearing-2",
        forbidden_matter=REYES,
        note="Hearing was continued in week 3; asked after, must return the new date.",
    ),
    Query(
        id="R3-Q2-supersession-historical",
        matter_id=CARTER, as_of="2026-01-10",
        text="when's the custody hearing",
        expected_fact_id="cc-hearing-1",
        forbidden_matter=REYES,
        note="Asked before the continuance was granted: the original date was still true then.",
    ),
    Query(
        id="R3-Q3-supersession-current-other-subject",
        matter_id=REYES, as_of="2026-02-10",
        text="what's the current back pay amount being claimed",
        expected_fact_id="re-backpay-2",
        forbidden_matter=CARTER,
        note="Back-pay estimate was revised up after a payroll audit in week 5; must return the revised figure.",
    ),
    Query(
        id="R3-Q4-leakage-same-predicate",
        matter_id=REYES, as_of="2026-02-10",
        text="when's the hearing",
        expected_fact_id="re-hearing-2",
        forbidden_matter=CARTER,
        note="Both matters have a hearing_date fact; the employment matter's own date must come back, not the custody case's.",
    ),
    Query(
        id="R3-Q5-no-cross-matter-fact",
        matter_id=CARTER, as_of="2026-02-10",
        text="what's the back pay claim amount",
        expected_fact_id=None,
        forbidden_matter=REYES,
        note="Back pay only exists in reyes-employment; carter-custody's memory has nothing responsive.",
    ),
    Query(
        id="R3-Q6-supersession-other-matter",
        matter_id=CARTER, as_of="2026-02-10",
        text="what's the current living arrangement for the kids",
        expected_fact_id="cc-residence-2",
        forbidden_matter=REYES,
        note="Custody arrangement changed to joint physical custody after week-5 mediation; must return the revised arrangement.",
    ),
    Query(
        id="R3-Q7-episodic-recall",
        matter_id=REYES, as_of="2026-01-30",
        text="did the client bring up any concerns about retaliation",
        expected_fact_id=None,
        forbidden_matter=CARTER,
        expected_keyword="retaliate",
        note="Pure episodic recall of a week-4 conversational turn about retaliation and whistleblower protection.",
    ),
    Query(
        id="R3-Q8-not-yet-known",
        matter_id=CARTER, as_of="2026-01-08",
        text="who is the guardian ad litem",
        expected_fact_id=None,
        forbidden_matter=REYES,
        note="Guardian ad litem isn't appointed until week 2 (valid_from 2026-01-12); asked in week 1, nothing should be returned yet.",
    ),
]
