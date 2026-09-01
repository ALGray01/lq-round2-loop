"""A third, independently-authored scenario -- family law and employment
law, different vocabulary again from scenario/ and scenario2/. Built
specifically to stress-test the REL_MARGIN=1.3 confidence window that
README.md's Reflection named as still only checked against two corpora
(safe window measured as (1.11, 1.41]). See README "Generalization check,
round 2".
"""
from memory_lab.facts import Fact, FactStore
from memory_lab.episodic import EpisodicLog, Turn

CARTER = "carter-custody"
REYES = "reyes-employment"


def build_timeline() -> tuple[FactStore, EpisodicLog]:
    facts = FactStore()
    episodic = EpisodicLog()

    # --- Matter A: carter-custody (child custody dispute) ----------------
    facts.add(Fact(
        fact_id="cc-hearing-1", matter_id=CARTER, subject="hearing_date",
        predicate="is", object="2026-04-01",
        source="family court notice, week 1", valid_from="2026-01-05",
    ))
    facts.add(Fact(
        fact_id="cc-residence-1", matter_id=CARTER, subject="primary_residence",
        predicate="is", object="with the mother, alternating weekends with the father",
        source="temporary custody order, week 1", valid_from="2026-01-05",
    ))
    facts.add(Fact(
        fact_id="cc-gal-1", matter_id=CARTER, subject="guardian_ad_litem",
        predicate="is", object="Thomas Kim",
        source="court appointment order, week 2", valid_from="2026-01-12",
    ))
    # Week 3: hearing continued.
    facts.supersede(
        "cc-hearing-1",
        Fact(
            fact_id="cc-hearing-2", matter_id=CARTER, subject="hearing_date",
            predicate="is", object="2026-04-22",
            source="order granting continuance, week 3", valid_from="2026-01-19",
        ),
        at_date="2026-01-19",
    )
    facts.add(Fact(
        fact_id="cc-support-1", matter_id=CARTER, subject="child_support_amount",
        predicate="is", object="1200 dollars monthly",
        source="child support guideline calculation, week 4", valid_from="2026-01-26",
    ))
    # Week 5: mediation changes the custody arrangement.
    facts.supersede(
        "cc-residence-1",
        Fact(
            fact_id="cc-residence-2", matter_id=CARTER, subject="primary_residence",
            predicate="is", object="joint physical custody, alternating weeks",
            source="mediated custody agreement, week 5", valid_from="2026-02-02",
        ),
        at_date="2026-02-02",
    )

    episodic.append(Turn(CARTER, "s1", "2026-01-05", "client",
                          "We need to keep track of the custody hearing and any changes to the parenting schedule."))
    episodic.append(Turn(CARTER, "s3", "2026-01-19", "client",
                          "Would the new hearing date overlap with the kids' spring break trip we already booked?"))
    episodic.append(Turn(CARTER, "s5", "2026-02-02", "lawyer",
                          "The mediated agreement should be reflected in the next custody filing."))

    # --- Matter B: reyes-employment (employment discrimination claim) ----
    # Deliberately reuses "hearing_date" again, like scenario 1 and 2, to
    # re-test compartment leakage with a third vocabulary.
    facts.add(Fact(
        fact_id="re-hearing-1", matter_id=REYES, subject="hearing_date",
        predicate="is", object="2026-03-10",
        source="EEOC mediation notice, week 1", valid_from="2026-01-06",
    ))
    facts.add(Fact(
        fact_id="re-party-1", matter_id=REYES, subject="opposing_party",
        predicate="is", object="Global Foods Inc.",
        source="charge of discrimination, week 1", valid_from="2026-01-06",
    ))
    facts.add(Fact(
        fact_id="re-backpay-1", matter_id=REYES, subject="back_pay_claim",
        predicate="is", object="35000 dollars",
        source="initial demand letter, week 2", valid_from="2026-01-13",
    ))
    # Week 3: mediation date is rescheduled.
    facts.supersede(
        "re-hearing-1",
        Fact(
            fact_id="re-hearing-2", matter_id=REYES, subject="hearing_date",
            predicate="is", object="2026-03-24",
            source="rescheduling notice, week 3", valid_from="2026-01-20",
        ),
        at_date="2026-01-20",
    )
    facts.add(Fact(
        fact_id="re-investigator-1", matter_id=REYES, subject="lead_investigator",
        predicate="is", object="EEOC investigator R. Patel",
        source="investigator assignment letter, week 4", valid_from="2026-01-27",
    ))
    # Week 5: new payroll records raise the back-pay estimate.
    facts.supersede(
        "re-backpay-1",
        Fact(
            fact_id="re-backpay-2", matter_id=REYES, subject="back_pay_claim",
            predicate="is", object="52000 dollars",
            source="revised demand letter after payroll audit, week 5", valid_from="2026-02-03",
        ),
        at_date="2026-02-03",
    )

    episodic.append(Turn(REYES, "s2", "2026-01-06", "client",
                          "I filed the charge with the EEOC and I'm waiting to hear about next steps."))
    episodic.append(Turn(REYES, "s4", "2026-01-28", "client",
                          "I'm worried my employer might retaliate against me for filing, is that something we can raise as whistleblower protection?"))

    return facts, episodic
