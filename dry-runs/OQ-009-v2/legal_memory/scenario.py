"""Synthetic multi-week legal-research history used for the head-to-head test.

This is scripted ground truth, not a real client matter: it exists to give
both memory architectures the *same* raw material and the *same* set of
questions, so their answers can be compared against a known-correct answer.
See README.md "Limitations" for what this can and cannot prove.

Two matters run in parallel over seven weeks (12 sessions), deliberately
sharing vocabulary ("breach of contract", "Acme", "statute of limitations",
"3 years") so a naive similarity search has a real chance of confusing them
-- this is a steelman trap, not a strawman: the overlap is the kind of
coincidence that happens constantly in a real practice (common defendant
names, common causes of action).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Fact:
    fact_id: str
    matter_id: str          # required, non-nullable -- see README on structural isolation
    text: str
    recorded_at: int         # transaction time: session index this was learned
    source_session: int
    invalidated_at: int | None = None   # transaction time: session this was superseded
    valid_from: int | None = None       # valid time: real-world legal-effect start
    valid_until: int | None = None      # valid time: real-world legal-effect end
    supersedes: str | None = None       # fact_id this replaces, for provenance display

    def __post_init__(self) -> None:
        if not self.matter_id:
            raise ValueError(f"Fact {self.fact_id} created without a matter_id")


@dataclass
class Session:
    session_id: int
    week: int
    matter_id: str | None    # None simulates a real-world tagging lapse (session 3)
    text: str


def build_facts() -> list[Fact]:
    facts: list[Fact] = []

    # --- Matter A: Doe v. Acme (contract dispute) ---
    facts.append(Fact(
        fact_id="A-sol-v1",
        matter_id="doe_v_acme",
        text=("Under State Commercial Code section 2-725, the statute of limitations "
              "for Doe's breach of contract claim against Acme is 4 years from the "
              "date of breach."),
        recorded_at=1, source_session=1,
        valid_from=10, valid_until=None,
        invalidated_at=7,  # superseded once the amendment is learned at session 7
    ))
    facts.append(Fact(
        fact_id="A-party-v1",
        matter_id="doe_v_acme",
        text="The defendant named in the complaint is Acme Corp.",
        recorded_at=1, source_session=1,
        invalidated_at=4,
    ))
    facts.append(Fact(
        fact_id="A-party-v2",
        matter_id="doe_v_acme",
        text=("The defendant's correct legal name is Acme Corporation Inc., "
              "per the corrected complaint filed this week."),
        recorded_at=4, source_session=4,
        supersedes="A-party-v1",
    ))
    facts.append(Fact(
        fact_id="A-precedent-v1",
        matter_id="doe_v_acme",
        text=("Smith v. Jones held that sending a demand letter tolls the statute "
              "of limitations for breach of contract claims."),
        recorded_at=2, source_session=2,
        valid_from=15, valid_until=None,
        invalidated_at=10,  # superseded once the overturning is learned at session 10
    ))
    facts.append(Fact(
        fact_id="A-sol-v2",
        matter_id="doe_v_acme",
        text=("Section 2-725 was amended, shortening the statute of limitations for "
              "breach of contract claims formed after the amendment to 3 years. "
              "Doe's contract with Acme was formed after the amendment, so the "
              "applicable statute of limitations for this claim is 3 years."),
        recorded_at=7, source_session=7,
        valid_from=24, valid_until=None,
        supersedes="A-sol-v1",
    ))
    facts.append(Fact(
        fact_id="A-precedent-v2",
        matter_id="doe_v_acme",
        text=("Smith v. Jones was overturned by Roe v. Big Co.; the demand-letter "
              "tolling rule from Smith is no longer good law as of the Roe decision."),
        recorded_at=10, source_session=10,
        valid_from=26, valid_until=None,
        supersedes="A-precedent-v1",
    ))
    # Retroactive bi-temporal edit: cap Smith's real-world validity window now that
    # we know it was overturned, without touching when we *learned* that (recorded_at).
    facts.append(Fact(
        fact_id="A-precedent-v1-capped",
        matter_id="doe_v_acme",
        text=("Smith v. Jones held that sending a demand letter tolls the statute "
              "of limitations for breach of contract claims. [validity window "
              "capped upon learning of Roe v. Big Co.]"),
        recorded_at=2, source_session=2,       # still "learned" at session 2
        valid_from=15, valid_until=26,          # but now known to have ended at t=26
        invalidated_at=10,
        supersedes="A-precedent-v1",
    ))

    # --- Matter B: Estate of Wu (probate/trust dispute) ---
    # Deliberately shares "Acme", "breach of contract", "statute of limitations",
    # "3 years" vocabulary with Matter A's post-amendment fact (A-sol-v2).
    facts.append(Fact(
        fact_id="B-vendor-sol",
        matter_id="estate_wu",
        text=("In the Estate of Wu matter, the trustee is investigating a separate "
              "vendor contract with Acme Cleaning Services; the applicable statute "
              "of limitations for that breach of contract claim is 3 years under "
              "the general commercial statute."),
        recorded_at=3, source_session=3,
        valid_from=20, valid_until=None,
    ))
    facts.append(Fact(
        fact_id="B-trust-issue",
        matter_id="estate_wu",
        text=("The trust instrument's spendthrift clause governs distributions to "
              "the beneficiary; no breach of the trust itself has been identified."),
        recorded_at=5, source_session=5,
        valid_from=20, valid_until=None,
    ))

    return facts


def build_sessions() -> list[Session]:
    return [
        Session(1, 1, "doe_v_acme",
                "Intake call: Doe wants to sue Acme Corp for breach of contract. "
                "Researched section 2-725: 4-year statute of limitations applies."),
        Session(2, 1, "doe_v_acme",
                "Researched supporting precedent. Smith v. Jones: demand letter "
                "tolls the statute of limitations."),
        # Session 3 is deliberately left untagged (matter_id=None): an intake memo
        # filed before the Estate of Wu matter number existed in the system --
        # the kind of real-world tagging lapse that a flat store has no defense
        # against and a required-field graph store cannot represent at all.
        Session(3, 2, None,
                "New client intake: Estate of Wu, trustee dispute. Vendor Acme "
                "Cleaning Services may have breached its contract; 3-year statute "
                "of limitations under the general commercial statute."),
        Session(4, 2, "doe_v_acme",
                "Corrected complaint received: defendant's correct legal name is "
                "Acme Corporation Inc., not Acme Corp."),
        Session(5, 3, "estate_wu",
                "Reviewed trust instrument. Spendthrift clause governs "
                "distributions; no breach of the trust itself identified."),
        Session(6, 3, "doe_v_acme",
                "Client check-in, no new facts. Reconfirmed 4-year SOL timeline "
                "with client for planning purposes."),
        Session(7, 4, "doe_v_acme",
                "Statute research update: section 2-725 was amended, shortening "
                "the limitations period to 3 years for contracts formed after the "
                "amendment. Doe's contract with Acme falls after that date, so 3 "
                "years now applies, not 4."),
        Session(8, 4, "estate_wu",
                "Trustee status update, no new legal research this session."),
        Session(9, 5, "doe_v_acme",
                "Drafting motion; cited Smith v. Jones for the tolling argument."),
        Session(10, 6, "doe_v_acme",
                "Opposing counsel's brief flags that Smith v. Jones was overturned "
                "by Roe v. Big Co. Confirmed: Smith is no longer good law for the "
                "tolling argument."),
        Session(11, 6, "estate_wu",
                "No updates this week."),
        Session(12, 7, "doe_v_acme",
                "Revised motion to drop the Smith v. Jones tolling argument and "
                "rely on the 3-year statute of limitations directly."),
    ]
