"""A second, independently-authored scenario -- different matter types,
different vocabulary, and queries phrased with mild paraphrase rather than
lifting the fact's own wording verbatim. Built specifically to check whether
the retrieval-confidence rule in memory_lab/retrieval.py (tuned against
scenario/timeline.py's vocabulary) and the hybrid architecture's win margin
generalize, rather than being an artifact of one hand-picked corpus. See
README "Generalization check".
"""
from memory_lab.facts import Fact, FactStore
from memory_lab.episodic import EpisodicLog, Turn

ACME = "acme-v-globex"
BRIGGS = "briggs-injury"


def build_timeline() -> tuple[FactStore, EpisodicLog]:
    facts = FactStore()
    episodic = EpisodicLog()

    # --- Matter A: acme-v-globex (patent licensing dispute) -------------
    facts.add(Fact(
        fact_id="ag-trial-1", matter_id=ACME, subject="trial_date",
        predicate="is", object="2026-05-01",
        source="court scheduling order, week 1", valid_from="2026-01-05",
    ))
    facts.add(Fact(
        fact_id="ag-royalty-1", matter_id=ACME, subject="licensing_royalty_rate",
        predicate="is", object="three percent",
        source="license agreement draft, week 1", valid_from="2026-01-05",
    ))
    facts.add(Fact(
        fact_id="ag-expert-1", matter_id=ACME, subject="lead_expert",
        predicate="is", object="Dr. Priya Rao",
        source="expert retention letter, week 2", valid_from="2026-01-12",
    ))
    # Week 3: the court grants a continuance -- must supersede.
    facts.supersede(
        "ag-trial-1",
        Fact(
            fact_id="ag-trial-2", matter_id=ACME, subject="trial_date",
            predicate="is", object="2026-05-20",
            source="order granting continuance, week 3", valid_from="2026-01-19",
        ),
        at_date="2026-01-19",
    )
    facts.add(Fact(
        fact_id="ag-damages-1", matter_id=ACME, subject="damages_estimate",
        predicate="is", object="1200000 dollars",
        source="damages expert report, week 4", valid_from="2026-01-26",
    ))
    # Week 5: arbitration revises the royalty rate -- must supersede.
    facts.supersede(
        "ag-royalty-1",
        Fact(
            fact_id="ag-royalty-2", matter_id=ACME, subject="licensing_royalty_rate",
            predicate="is", object="four point five percent",
            source="arbitration ruling, week 5", valid_from="2026-02-02",
        ),
        at_date="2026-02-02",
    )

    episodic.append(Turn(ACME, "s1", "2026-01-05", "client",
                          "We want to keep a close eye on the trial schedule and the license terms."))
    episodic.append(Turn(ACME, "s3", "2026-01-19", "client",
                          "Does the continuance change our timeline for the licensing negotiation with Globex?"))
    episodic.append(Turn(ACME, "s5", "2026-02-02", "lawyer",
                          "The arbitrator's royalty ruling should be reflected in the next licensing draft."))

    # --- Matter B: briggs-injury (personal injury claim) -----------------
    # Deliberately reuses the "trial_date" predicate, like scenario 1's
    # hearing_date collision, to re-test compartment leakage in a different
    # vocabulary and domain.
    facts.add(Fact(
        fact_id="bi-trial-1", matter_id=BRIGGS, subject="trial_date",
        predicate="is", object="2026-06-01",
        source="civil docket notice, week 1", valid_from="2026-01-06",
    ))
    facts.add(Fact(
        fact_id="bi-carrier-1", matter_id=BRIGGS, subject="insurance_carrier",
        predicate="is", object="Acme Mutual",
        source="claim intake form, week 1", valid_from="2026-01-06",
    ))
    facts.add(Fact(
        fact_id="bi-specialist-1", matter_id=BRIGGS, subject="medical_specialist",
        predicate="is", object="Dr. Nia Chen",
        source="referral letter, week 3", valid_from="2026-01-20",
    ))
    facts.add(Fact(
        fact_id="bi-demand-1", matter_id=BRIGGS, subject="settlement_demand",
        predicate="is", object="80000 dollars",
        source="demand letter 1, week 2", valid_from="2026-01-13",
    ))
    # Week 5: demand is revised up after the specialist's report comes in.
    facts.supersede(
        "bi-demand-1",
        Fact(
            fact_id="bi-demand-2", matter_id=BRIGGS, subject="settlement_demand",
            predicate="is", object="110000 dollars",
            source="demand letter 2, week 5", valid_from="2026-02-02",
        ),
        at_date="2026-02-02",
    )

    episodic.append(Turn(BRIGGS, "s2", "2026-01-06", "client",
                          "The insurance carrier already assigned an adjuster to my case."))
    episodic.append(Turn(BRIGGS, "s4", "2026-01-27", "client",
                          "I'm still having a lot of back pain and think I might need more physical therapy sessions."))

    return facts, episodic
