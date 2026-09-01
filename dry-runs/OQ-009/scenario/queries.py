"""Ground-truth test queries, authored by reading scenario/timeline.py and
reasoning about what the *correct* answer is at each date -- written before
running any system against them. This is what keeps the head-to-head test
from being circular (FAILURE-CLASSES.md item 2/3): the expected values below
are facts about the fictional timeline, not outputs copied from a program.

Each query also records `forbidden_matter`: a matter whose facts must NEVER
appear in the answer to this query. That is the compartment-leakage check.
"""
from dataclasses import dataclass
from typing import Optional

from scenario.timeline import DOE, SMITH


@dataclass
class Query:
    id: str
    matter_id: str
    as_of: str
    text: str
    expected_fact_id: Optional[str]  # None means "no confident fact should be surfaced"
    forbidden_matter: Optional[str]  # a matter_id that must not be touched
    note: str
    expected_keyword: Optional[str] = None  # for episodic-recall queries: a word the correct snippet must contain


QUERIES = [
    Query(
        id="Q1-supersession-current",
        matter_id=DOE, as_of="2026-02-15",
        text="when is the hearing date",
        expected_fact_id="dr-hearing-2",
        forbidden_matter=SMITH,
        note="Hearing date was corrected in week 3; asked in week 6, must return the corrected date, not the original.",
    ),
    Query(
        id="Q2-supersession-historical",
        matter_id=DOE, as_of="2026-01-10",
        text="when is the hearing date",
        expected_fact_id="dr-hearing-1",
        forbidden_matter=SMITH,
        note="Asked before the week-3 correction happened: the historically-true answer is the original date, not the future correction.",
    ),
    Query(
        id="Q3-settlement-current",
        matter_id=DOE, as_of="2026-02-15",
        text="what is the settlement offer amount",
        expected_fact_id="dr-settle-2",
        forbidden_matter=SMITH,
        note="Settlement offer was revised upward in week 6; must return the revised figure.",
    ),
    Query(
        id="Q4-leakage-same-predicate",
        matter_id=SMITH, as_of="2026-02-15",
        text="what is the hearing date",
        expected_fact_id="se-hearing-1",
        forbidden_matter=DOE,
        note="Both matters have a hearing_date fact; the estate matter's own date must come back, not the contract matter's.",
    ),
    Query(
        id="Q5-no-cross-matter-fact",
        matter_id=DOE, as_of="2026-02-15",
        text="what is the estate value",
        expected_fact_id=None,
        forbidden_matter=SMITH,
        note="Estate value belongs only to the smith-estate matter; doe-v-roe's own memory has nothing responsive and must not reach into smith-estate to answer.",
    ),
    Query(
        id="Q6-supersession-other-matter",
        matter_id=SMITH, as_of="2026-02-15",
        text="what is the current estate value",
        expected_fact_id="se-value-2",
        forbidden_matter=DOE,
        note="Estate value was revised down in week 4; must return the revised appraisal.",
    ),
    Query(
        id="Q7-episodic-recall",
        matter_id=DOE, as_of="2026-02-01",
        text="what did the client say about a vacation conflict",
        expected_fact_id=None,
        forbidden_matter=SMITH,
        expected_keyword="vacation",
        note="Not a structured fact at all -- pure episodic recall of a week-3 conversational turn about April/vacation.",
    ),
    Query(
        id="Q8-not-yet-known",
        matter_id=DOE, as_of="2026-01-15",
        text="who is the key witness",
        expected_fact_id=None,
        forbidden_matter=SMITH,
        note="The witness fact isn't recorded until week 4 (valid_from 2026-01-27); asked in week 2, nothing should be returned yet, not a future fact leaking backward.",
    ),
]
