"""Ground-truth queries for scenario2 -- authored the same way as
scenario/queries.py: read scenario2/timeline.py, reason about what's
actually true at each date, write the expected answer down before running
any system. Phrasing here deliberately paraphrases the underlying fact text
more than scenario 1 did (e.g. "when is the trial scheduled" against a fact
literally keyed as `trial_date`), to stress-test whether the tuned
retrieval-confidence rule in memory_lab/retrieval.py still finds the right
fact under looser wording.
"""
from dataclasses import dataclass
from typing import Optional

from scenario.queries import Query  # reuse the same dataclass shape
from scenario2.timeline import ACME, BRIGGS

QUERIES = [
    Query(
        id="R2-Q1-supersession-current",
        matter_id=ACME, as_of="2026-02-10",
        text="when is the trial scheduled",
        expected_fact_id="ag-trial-2",
        forbidden_matter=BRIGGS,
        note="Trial date moved after a continuance in week 3; asked after, must return the new date.",
    ),
    Query(
        id="R2-Q2-supersession-historical",
        matter_id=ACME, as_of="2026-01-10",
        text="when is the trial scheduled",
        expected_fact_id="ag-trial-1",
        forbidden_matter=BRIGGS,
        note="Asked before the continuance was granted: the original date was still true then.",
    ),
    Query(
        id="R2-Q3-royalty-current",
        matter_id=ACME, as_of="2026-02-10",
        text="what's the royalty rate under the license",
        expected_fact_id="ag-royalty-2",
        forbidden_matter=BRIGGS,
        note="Royalty rate was revised by arbitration in week 5; must return the revised rate.",
    ),
    Query(
        id="R2-Q4-leakage-same-predicate",
        matter_id=BRIGGS, as_of="2026-02-10",
        text="when is the trial scheduled",
        expected_fact_id="bi-trial-1",
        forbidden_matter=ACME,
        note="Both matters have a trial_date fact; the injury matter's own date must come back, not the patent case's.",
    ),
    Query(
        id="R2-Q5-no-cross-matter-fact",
        matter_id=ACME, as_of="2026-02-10",
        text="what is the settlement demand amount",
        expected_fact_id=None,
        forbidden_matter=BRIGGS,
        note="Settlement demand only exists in briggs-injury; acme-v-globex's memory has nothing responsive.",
    ),
    Query(
        id="R2-Q6-supersession-other-matter",
        matter_id=BRIGGS, as_of="2026-02-10",
        text="what is the current settlement demand",
        expected_fact_id="bi-demand-2",
        forbidden_matter=ACME,
        note="Demand was revised up in week 5 after the specialist's report; must return the revised figure.",
    ),
    Query(
        id="R2-Q7-episodic-recall",
        matter_id=BRIGGS, as_of="2026-01-30",
        text="did the client mention anything about physical therapy",
        expected_fact_id=None,
        forbidden_matter=ACME,
        expected_keyword="therapy",
        note="Pure episodic recall of a week-4 conversational turn about back pain and physical therapy.",
    ),
    Query(
        id="R2-Q8-not-yet-known",
        matter_id=ACME, as_of="2026-01-08",
        text="who is the lead expert",
        expected_fact_id=None,
        forbidden_matter=BRIGGS,
        note="Expert isn't retained until week 2 (valid_from 2026-01-12); asked in week 1, nothing should be returned yet.",
    ),
]
