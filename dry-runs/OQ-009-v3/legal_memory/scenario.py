"""Synthetic 12-session, 2-matter, 8-week legal-research history.

This is scripted ground truth, not real client data (see README
Limitations). It is built to contain the specific failure modes the eval
tests for: a superseded statute, an overturned precedent, a corrected party
name (a control case), and deliberate vocabulary collision between two
matters (to give a flat text-similarity search a genuine, non-contrived
chance of confusing them).

Two kinds of objects come out of this module:

- `build_sessions()`: raw session transcripts, one per research session,
  each carrying a `matter_id` tag EXCEPT one (session 6), which is left
  untagged to simulate a memo filed before a matter number existed in the
  system. This is what `VectorBaseline` indexes -- a flat store over raw
  text is exactly as good as its query-time tagging.
- `build_facts()`: hand-authored facts extracted from those sessions, each
  with a *required* `matter_id` (see `graph_store.Fact`) and, where
  relevant, a `supersedes` pointer to the fact it replaces. This is what
  `GraphMemoryStore` and `CompartmentMemoryStore` index. Extraction here is
  manual, not automated -- seeing the extraction step itself is out of
  scope for this repo (see README Limitations).
"""
from __future__ import annotations

from dataclasses import dataclass

MATTER_A = "matter-reyes-v-coastal"
MATTER_B = "matter-whitfield-trust"


def require_matter_id(matter_id: object, context: str) -> None:
    """Reject anything that isn't a real, non-blank, plain-`str` matter id.

    A prior version only checked `not matter_id`, which rejects `None`,
    `''`, `0`, and `False` but lets a whitespace-only string like `'   '`
    through -- found by adversarial audit. `matter_id` must be an actual
    `str` (so `0`/`False` are also rejected as the wrong type, not just as
    falsy) with non-whitespace content.

    `type(matter_id) is str`, not `isinstance(matter_id, str)`: a second
    adversarial audit found that `isinstance` accepts any `str` *subclass*,
    including one with `__eq__` overridden to always return `True`. Every
    query-time matter filter in this repo does a plain `==` comparison
    (`f.matter_id == matter_id`), so such an object made every fact in the
    store compare equal to it regardless of matter -- a real, silent
    isolation bypass, not a contrived one (a subclassed, tagged/traced
    string is a realistic thing an upstream system could hand this code).
    Rejecting anything that isn't exactly `str` closes this: with no
    subclass allowed through, `==` on both sides is always plain `str.__eq__`.
    """
    if type(matter_id) is not str or not matter_id.strip():
        raise ValueError(f"{context} requires a non-empty matter_id")


@dataclass(frozen=True)
class Session:
    session_id: str
    week: int
    matter_id: str | None  # None => untagged, realistic tagging gap
    transcript: str


@dataclass(frozen=True)
class Fact:
    fact_id: str
    matter_id: str
    text: str
    learned_week: int  # transaction time: when the agent learned this
    valid_from_week: int  # valid time: since when this has been true in the world
    supersedes: str | None = None  # fact_id this replaces, if any

    def __post_init__(self) -> None:
        require_matter_id(self.matter_id, context="Fact")


def validate_no_supersession_cycles(facts: list[Fact]) -> None:
    """Raise ValueError if any fact's `supersedes` chain cycles back on itself.

    Both `GraphMemoryStore` and `CompartmentMemoryStore` exclude a fact from
    results once something in the known set points at it via `supersedes`.
    If A supersedes B and B supersedes A (a data-corruption scenario an
    upstream extraction bug could produce), both facts would be silently
    excluded from every query -- total, untraced fact loss rather than a
    dated or misfiled fact. Call this at store construction so a corrupt
    chain is a loud error instead of quietly vanishing facts.
    """
    by_id = {f.fact_id: f for f in facts}
    for start in facts:
        seen = {start.fact_id}
        current = start
        while current.supersedes and current.supersedes in by_id:
            if current.supersedes in seen:
                raise ValueError(
                    f"Supersession cycle detected involving fact {start.fact_id!r}"
                )
            seen.add(current.supersedes)
            current = by_id[current.supersedes]


def build_sessions() -> list[Session]:
    return [
        Session(
            "s01", 1, MATTER_A,
            "Intake call on Reyes v. Coastal Freight. Client alleges Coastal "
            "Freight LLC breached the shipping contract. Researched Fictional "
            "State Commercial Code section 12-101: the statute of limitations "
            "for breach of commercial contract claims is 4 years from breach.",
        ),
        Session(
            "s02", 1, MATTER_A,
            "Found Nguyen v. Delta Transit, a controlling appellate decision "
            "holding that a written demand letter tolls the limitations period "
            "for commercial carriage disputes. This helps our timing position "
            "against Coastal Freight LLC.",
        ),
        Session(
            "s03", 2, MATTER_B,
            "Intake on the Whitfield trust matter. The trust's maintenance "
            "vendor is Coastal Cleaning Group. Reviewing the vendor services "
            "agreement for relevant terms; nothing conclusive yet.",
        ),
        Session(
            "s04", 2, MATTER_A,
            "Corrected complaint filed. Defendant's correct legal name is "
            "Coastal Freight & Logistics LLC, not Coastal Freight LLC as "
            "originally pleaded. Amending caption accordingly.",
        ),
        Session(
            "s05", 3, MATTER_B,
            "Reviewed trust accounting. Trustee's counsel disputes whether "
            "Coastal Cleaning Group's invoices were properly authorized. This "
            "is a breach of fiduciary duty question, separate from the vendor "
            "contract's 3-year limitations clause.",
        ),
        Session(
            "s06", 3, None,  # untagged: filed before a matter number existed
            "Quick memo, no file opened yet: confirmed the Coastal Cleaning "
            "Group vendor services agreement for the Whitfield trust matter "
            "contains a 3-year statute of limitations clause for breach of "
            "contract claims against the vendor. Need to open a matter file.",
        ),
        Session(
            "s07", 4, MATTER_A,
            "Legislature amended Fictional State Commercial Code section "
            "12-101, effective this session's date. The limitations period "
            "for breach of commercial contract claims is now 3 years for any "
            "claim not already time-barred under the prior 4-year rule.",
        ),
        Session(
            "s08", 5, MATTER_A,
            "Drafted motion in limine relying on the current 3-year "
            "limitations period and the Nguyen tolling rule for the demand "
            "letter sent to Coastal Freight & Logistics LLC.",
        ),
        Session(
            "s09", 6, MATTER_B,
            "Drafted response on the fiduciary duty question. Client also "
            "asked again whether the 3-year vendor contract limitations "
            "clause has run; confirmed it has not.",
        ),
        Session(
            "s10", 7, MATTER_A,
            "Appellate court decided Park v. Summit Carriers, expressly "
            "overturning Nguyen v. Delta Transit. A demand letter no longer "
            "tolls the limitations period for commercial carriage disputes as "
            "of this decision.",
        ),
        Session(
            "s11", 7, MATTER_B,
            "Settlement conference on the Whitfield trust matter scheduled. "
            "No new legal research this session; administrative update only.",
        ),
        Session(
            "s12", 8, MATTER_A,
            "Revised the motion in limine to drop reliance on Nguyen given "
            "Park v. Summit Carriers, and to rely on the current 3-year "
            "limitations period against Coastal Freight & Logistics LLC "
            "directly without a tolling argument.",
        ),
    ]


def build_facts() -> list[Fact]:
    return [
        Fact("A-sol-v1", MATTER_A,
             "Under Fictional State Commercial Code section 12-101, the "
             "statute of limitations for breach of commercial contract "
             "claims is 4 years.",
             learned_week=1, valid_from_week=0),
        Fact("A-party-v1", MATTER_A,
             "Defendant is Coastal Freight LLC.",
             learned_week=1, valid_from_week=0),
        Fact("A-precedent-v1", MATTER_A,
             "Nguyen v. Delta Transit holds that a written demand letter "
             "tolls the limitations period for commercial carriage disputes.",
             learned_week=1, valid_from_week=0),
        Fact("A-party-v2", MATTER_A,
             "Defendant's correct legal name is Coastal Freight & Logistics "
             "LLC, per the corrected complaint.",
             learned_week=2, valid_from_week=2, supersedes="A-party-v1"),
        Fact("A-sol-v2", MATTER_A,
             "Fictional State Commercial Code section 12-101 was amended; "
             "the statute of limitations for breach of commercial contract "
             "claims is now 3 years.",
             learned_week=4, valid_from_week=4, supersedes="A-sol-v1"),
        Fact("A-precedent-v2", MATTER_A,
             "Park v. Summit Carriers overturned Nguyen v. Delta Transit; a "
             "demand letter no longer tolls the limitations period for "
             "commercial carriage disputes.",
             learned_week=7, valid_from_week=7, supersedes="A-precedent-v1"),
        Fact("B-vendor-sol", MATTER_B,
             "Coastal Cleaning Group's vendor services agreement has a "
             "3-year statute of limitations clause for breach of contract "
             "claims against the vendor.",
             learned_week=3, valid_from_week=0),
        Fact("B-fiduciary", MATTER_B,
             "Whether Coastal Cleaning Group's invoices were properly "
             "authorized is a breach of fiduciary duty question against the "
             "trustee, separate from the vendor contract's limitations "
             "clause.",
             learned_week=3, valid_from_week=3),
    ]
