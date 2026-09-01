"""A deterministic, fictional 6-week legal-research timeline spanning two
unrelated matters. This is authored once, by hand, before any query's
expected answer is written and before any system is run against it -- see
scenario/queries.py for the independently-authored ground truth, and
README.md for why that ordering matters.

Matter A (doe-v-roe): a contract dispute. Matter B (smith-estate): an
unrelated probate matter. Both use the predicate "hearing_date" on purpose,
to stress-test whether an architecture without a real compartment boundary
can keep them apart.
"""
from memory_lab.facts import Fact, FactStore
from memory_lab.episodic import EpisodicLog, Turn

DOE = "doe-v-roe"
SMITH = "smith-estate"


def build_timeline() -> tuple[FactStore, EpisodicLog]:
    facts = FactStore()
    episodic = EpisodicLog()

    # --- Matter A: doe-v-roe -------------------------------------------
    facts.add(Fact(
        fact_id="dr-hearing-1", matter_id=DOE, subject="hearing_date",
        predicate="is", object="2026-03-01",
        source="clerk email, week 1", valid_from="2026-01-05",
    ))
    facts.add(Fact(
        fact_id="dr-sol-1", matter_id=DOE, subject="statute_of_limitations",
        predicate="is", object="four years",
        source="research memo, week 1", valid_from="2026-01-05",
    ))
    facts.add(Fact(
        fact_id="dr-oc-1", matter_id=DOE, subject="opposing_counsel",
        predicate="is", object="Smith and Associates",
        source="notice of appearance, week 2", valid_from="2026-01-12",
    ))
    # Week 3: the clerk moves the hearing date. This must supersede, not
    # duplicate -- the whole point of the design is that "when is the
    # hearing" answered on 2026-02-15 must return the new date, while the
    # same question answered as of 2026-01-10 must still return the old one.
    facts.supersede(
        "dr-hearing-1",
        Fact(
            fact_id="dr-hearing-2", matter_id=DOE, subject="hearing_date",
            predicate="is", object="2026-03-15",
            source="clerk email, week 3", valid_from="2026-01-20",
        ),
        at_date="2026-01-20",
    )
    facts.add(Fact(
        fact_id="dr-witness-1", matter_id=DOE, subject="key_witness",
        predicate="is", object="J. Alvarez",
        source="deposition notice, week 4", valid_from="2026-01-27",
    ))
    facts.add(Fact(
        fact_id="dr-settle-1", matter_id=DOE, subject="settlement_offer",
        predicate="is", object="45000 dollars",
        source="mediation letter 1, week 5", valid_from="2026-02-03",
    ))
    facts.supersede(
        "dr-settle-1",
        Fact(
            fact_id="dr-settle-2", matter_id=DOE, subject="settlement_offer",
            predicate="is", object="60000 dollars",
            source="mediation letter 2, week 6", valid_from="2026-02-10",
        ),
        at_date="2026-02-10",
    )

    episodic.append(Turn(DOE, "s1", "2026-01-05", "client",
                          "We should track the contract dispute hearing and keep an eye on deadlines."))
    episodic.append(Turn(DOE, "s3", "2026-01-22", "client",
                          "I'm worried the deposition schedule will conflict with our family vacation planned for April."))
    episodic.append(Turn(DOE, "s5", "2026-02-05", "lawyer",
                          "Let's prepare a response to the mediation letter before the next settlement conversation."))

    # --- Matter B: smith-estate ------------------------------------------
    facts.add(Fact(
        fact_id="se-exec-1", matter_id=SMITH, subject="executor",
        predicate="is", object="Maria Smith",
        source="last will and testament, week 1", valid_from="2026-01-06",
    ))
    facts.add(Fact(
        fact_id="se-hearing-1", matter_id=SMITH, subject="hearing_date",
        predicate="is", object="2026-04-10",
        source="probate court notice, week 2", valid_from="2026-01-13",
    ))
    facts.add(Fact(
        fact_id="se-value-1", matter_id=SMITH, subject="estate_value",
        predicate="is", object="2300000 dollars",
        source="initial appraisal, week 3", valid_from="2026-01-20",
    ))
    facts.supersede(
        "se-value-1",
        Fact(
            fact_id="se-value-2", matter_id=SMITH, subject="estate_value",
            predicate="is", object="2150000 dollars",
            source="updated appraisal, week 4", valid_from="2026-01-27",
        ),
        at_date="2026-01-27",
    )

    episodic.append(Turn(SMITH, "s2", "2026-01-06", "client",
                          "Maria Smith is handling the estate as executor and wants a quick timeline."))
    episodic.append(Turn(SMITH, "s4", "2026-01-25", "client",
                          "Does the family cabin in Vermont count as part of the estate for probate purposes?"))

    return facts, episodic
