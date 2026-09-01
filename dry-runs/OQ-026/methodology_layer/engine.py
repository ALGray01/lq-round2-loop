"""
The methodology-layer engine.

Takes (a) a knowledge base of authorities/rules/hierarchies for one bounded
area of law and (b) a structured description of a clause + fact pattern, and
produces an InterpretiveAnnotation: the doctrinal grounding a competent
lawyer would bring to the text *before* reasoning about what it means. This
is the object that should be handed to an LLM in place of, or alongside,
raw entity-extraction spans (party names, dates, defined terms) -- see
entity_extraction_stub.py for what that raw layer looks like on its own,
and demo.py for them side by side.

Nothing here decides what the text *means*. It decides what doctrinal
apparatus applies and why, and surfaces authority tension the LLM (or a
human lawyer) needs to reason about that meaning correctly.

Generalization note: this module was originally written against only the
contract-interpretation knowledge base, and several pieces of it turned out
to be hardcoded to that KB's specific rule ids and fact-pattern shape (a
`kb.doctrinal_rules["rule_contra_proferentem"]` lookup by literal id, a
`fp.contract_type == "goods_sale"` gate, and hardcoded precedent-relation-id
strings for "surface this conflict"). Building a second knowledge base
(knowledge_base/statutory_construction/kb.yaml) exposed each of these, and
each was rewritten to be driven by data (trigger.params, the
`requires_flag` convention, generic precedent-relation lookups) rather than
by a hardcoded id. A round-2 audit then found the same pattern one layer
deeper -- the "borrowed under Erie" explanatory text was itself hardcoded
prose inside `_apply_threshold` even though the function claimed to be
generic -- and a fourth: `getattr(fp, flag_name, False)` had no validation,
so a typo'd `requires_flag` silently never fired, a dunder name like
`__class__` silently always fired (truthy regardless of the fact pattern),
and a non-string value crashed with an uncaught TypeError. Both are fixed
below (`JURISDICTION_BORROWING` is now a data table with its own doctrine
citation per entry; `_apply_fallback` validates `requires_flag` against
`FactPattern`'s actual field names and raises rather than guessing). See
README.md's Generalization section for the full account, including what
still does NOT generalize: the natural-language *outcome text* for each
threshold rule is still a per-rule-id branch in `_evaluate_threshold_rule`
(about a quarter of this file), because the content of "what does this
rule's outcome mean in English" is genuinely rule-specific legal prose, not
structure a schema can capture.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from . import weighting
from .models import KnowledgeBase

# Jurisdiction-borrowing table: some jurisdictions have no interpretive
# rules of their own in a given KB and instead apply another jurisdiction's
# rule under some doctrine that requires it. The only current entry is
# Erie (a federal court sitting in diversity applies the substantive law of
# the forum state, whether or not the panel agrees with it -- Trident
# Center is the demo's worked example), but the doctrine citation lives in
# the data, not in a hardcoded string inside the function that uses it, so
# a second borrowing doctrine (e.g. certified-question practice, or a
# federal-question statute incorporating state law) could be added as a
# new entry without touching _apply_threshold's code.
JURISDICTION_BORROWING = {
    "US-federal-9th-cir": {
        "borrows_from": "US-CA",
        "doctrine_note": (
            "Erie R.R. Co. v. Tompkins, 304 U.S. 64 (1938): a federal court sitting in diversity "
            "applies the substantive law of the state whose law governs, whether or not the panel agrees with it"
        ),
    },
}

# Precedent-relation types that represent live tension the LLM should see
# alongside a citation, as opposed to a relation that's just descriptive
# lineage (e.g. "follows").
TENSION_RELATIONS = {"criticizes", "limits", "overrules", "questions"}


@dataclass
class FactPattern:
    contract_type: str = "services"  # goods_sale | real_property | services | insurance
    facially_ambiguous: bool = False
    extrinsic_evidence_offered: bool = False
    structural_pattern: str | None = None  # matches DoctrinalRule.trigger.params.pattern
    evidence_conflict_sources: list[str] = field(default_factory=list)
    unequal_bargaining_power: bool = False
    # Named for what Founding Members of the Newport Beach Country Club v.
    # Newport Beach Country Club, Inc., 109 Cal. App. 4th 944 (2003)
    # actually holds (verified against the opinion via web search -- an
    # earlier draft of this KB mischaracterized the holding as a
    # "sophisticated parties represented by counsel" carve-out, which does
    # not appear in the case; the real limitation is the objective theory
    # of contracts: undisclosed subjective intent isn't the kind of
    # extrinsic evidence PG&E requires courts to consider, only evidence
    # objectively communicated between the parties is).
    only_undisclosed_subjective_intent_offered: bool = False
    # Statutory-construction-specific flags. Living on the same shared
    # FactPattern (rather than a per-domain subclass) is deliberate: it is
    # what let rule_of_lenity's `requires_flag: criminal_statute` and
    # rule_contra_proferentem's `requires_flag: unequal_bargaining_power`
    # be handled by the *same* generic engine code (see _apply_fallback)
    # instead of one bespoke branch per domain.
    criminal_statute: bool = False
    major_questions_raised: bool = False


def _threshold_rules_for(kb: KnowledgeBase, jurisdiction: str):
    borrowing = JURISDICTION_BORROWING.get(jurisdiction)
    lookup_jurisdiction = borrowing["borrows_from"] if borrowing else jurisdiction
    candidates = kb.rules_by_jurisdiction("threshold_ambiguity", lookup_jurisdiction)
    candidates.sort(key=lambda r: r["priority"])
    return candidates, lookup_jurisdiction


def _evaluate_threshold_rule(rule: dict, fp: FactPattern) -> tuple[str, bool]:
    """Return (outcome_text, disposes). disposes=True means this rule's
    answer controls and no lower-priority threshold rule needs to be
    checked; disposes=False means this rule didn't apply to the fact
    pattern and the next threshold rule in priority order should be tried.
    """
    rule_id = rule["id"]

    if rule_id == "rule_pmr_four_corners":
        if fp.facially_ambiguous:
            return "ambiguity appears on the face of the document; extrinsic evidence is admissible to resolve it", True
        if fp.extrinsic_evidence_offered:
            return (
                "inadmissible: contract is unambiguous on its face, and the four-corners rule "
                "bars extrinsic evidence regardless of what is offered"
            ), True
        return "not reached: no extrinsic evidence offered and no facial ambiguity alleged", True

    if rule_id == "rule_contextualism_pge":
        if fp.extrinsic_evidence_offered or fp.facially_ambiguous:
            outcome = (
                "provisionally admissible: extrinsic evidence must be considered to test whether the "
                "language is reasonably susceptible to the meaning urged, regardless of facial clarity"
            )
        else:
            outcome = "not reached: no extrinsic evidence offered and no facial ambiguity alleged"
        if fp.only_undisclosed_subjective_intent_offered:
            outcome += (
                "; narrowed here (Newport Beach Country Club) -- the evidence offered is undisclosed "
                "subjective intent never objectively communicated between the parties, which is not the "
                "kind of extrinsic evidence the reasonably-susceptible test requires courts to consider"
            )
        return outcome, True

    if rule_id == "rule_major_questions_doctrine":
        if fp.major_questions_raised:
            return (
                "clear congressional authorization required and absent: the interpretation urged would grant "
                "the agency authority of vast economic/political significance, so it is rejected regardless of "
                "what the bare statutory text could otherwise support (major questions doctrine)"
            ), True
        return "not reached: fact pattern does not implicate a question of vast economic/political significance", False

    if rule_id == "rule_statutory_plain_meaning":
        if fp.facially_ambiguous:
            return "ambiguity appears on the face of the statutory text; further tools of construction are needed", True
        if fp.extrinsic_evidence_offered:
            return (
                "statutory text is unambiguous and controls; legislative history/agency interpretation offered "
                "as an aid does not override plain text absent an absurd result"
            ), True
        return "not reached: no extrinsic aid offered and no facial ambiguity alleged", True

    return "rule matched but engine has no interpretive logic wired for this rule id", True


def _apply_threshold(kb: KnowledgeBase, jurisdiction: str, fp: FactPattern):
    candidates, lookup_jurisdiction = _threshold_rules_for(kb, jurisdiction)
    borrowing = JURISDICTION_BORROWING.get(jurisdiction)

    if not candidates:
        return {
            "test_applied": None,
            "outcome": "no codified threshold rule in this knowledge base for this jurisdiction",
            "authority": None,
        }

    rule, outcome = candidates[0], None
    for candidate in candidates:
        outcome, disposes = _evaluate_threshold_rule(candidate, fp)
        rule = candidate
        if disposes:
            break

    if borrowing:
        outcome += f" [borrowed from {lookup_jurisdiction} law: {borrowing['doctrine_note']}]"

    return {
        "test_applied": rule["name"],
        "outcome": outcome,
        "authority": rule["authority_basis"][0],
    }


def _apply_evidence_conflict_rules(kb: KnowledgeBase, fp: FactPattern):
    """Generic over any hierarchy: any DoctrinalRule triggered by
    evidence_conflict whose params.source is in the fact pattern's
    evidence_conflict_sources is a match, ordered by priority (which the KB
    fixes per its own governing hierarchy -- UCC 1-303(e) for contracts,
    e.g.). Originally gated on `fp.contract_type == "goods_sale"`, which was
    contract-KB-specific and had no analogue for the statutory KB's
    agency-interpretation source; the gate is unnecessary because callers
    only populate evidence_conflict_sources when it's actually relevant.

    A round-4 attacker audit found two bugs here, both fixed below: (1)
    `rule["trigger"]["params"]` was accessed with a bare `[...]`, so a
    schema-valid rule of this trigger type with no `params` key (the
    schema only requires `trigger.type`, not `trigger.params`) crashed with
    an uncaught KeyError instead of a clear error; now `.get("params", {})`.
    (2) `fp.evidence_conflict_sources` is typed `list[str]`, but nothing
    enforced that -- passing a bare string (an easy caller typo) didn't
    crash, it silently did substring matching instead of list membership
    (Python's `in` on a string checks substrings), so e.g. source
    "express_terms" would "match" against the string "xexpress_termsy".
    Same failure class this project already fixed once for
    `requires_flag`; fixed the same way here, by validating and raising
    rather than silently guessing."""
    if not fp.evidence_conflict_sources:
        return []
    if not isinstance(fp.evidence_conflict_sources, (list, tuple, set)):
        raise ValueError(
            f"FactPattern.evidence_conflict_sources must be a list of strings, got "
            f"{type(fp.evidence_conflict_sources).__name__!r} -- refusing to silently "
            "fall back to substring matching"
        )
    matched = [
        rule
        for rule in kb.doctrinal_rules.values()
        if rule["trigger"]["type"] == "evidence_conflict"
        and rule["trigger"].get("params", {}).get("source") in fp.evidence_conflict_sources
    ]
    return sorted(matched, key=lambda r: r["priority"])


def _apply_canons(kb: KnowledgeBase, fp: FactPattern):
    if not fp.structural_pattern:
        return []
    return [
        rule
        for rule in kb.doctrinal_rules.values()
        if rule["trigger"]["type"] == "structural_pattern"
        and rule["trigger"].get("params", {}).get("pattern") == fp.structural_pattern
    ]


_FACT_PATTERN_FIELDS = {f.name for f in dataclasses.fields(FactPattern)}


def _apply_fallback(kb: KnowledgeBase, fp: FactPattern, resolved_so_far: bool):
    """Generic over any KB's last-resort canon(s): a rule with trigger.type
    == fallback fires only if the FactPattern attribute named in
    trigger.params.requires_flag is truthy. This replaced a version that
    looked up "rule_contra_proferentem" by hardcoded id and checked
    fp.unequal_bargaining_power directly -- which broke the moment a second
    KB's fallback rule (rule_of_lenity, gated on fp.criminal_statute) needed
    the same code path.

    A round-2 audit found the naive `getattr(fp, flag_name, False)` this
    was first written with had three failure modes for a malformed KB: a
    typo'd flag name silently never fired (getattr's default swallowed the
    KeyError-shaped mistake), a dunder name like `__class__` silently
    *always* fired (the class object is truthy regardless of the fact
    pattern), and a non-string value crashed inside getattr with an opaque
    TypeError. `requires_flag` isn't (and can't cheaply be) constrained by
    the JSON Schema, since `trigger.params` is deliberately open-ended
    across rule types -- so this function now validates it directly and
    raises immediately with a clear message rather than guessing, matching
    this project's own standard (FAILURE-CLASSES.md item 4) that a
    validator which has never been shown a case it should reject proves
    nothing."""
    if resolved_so_far:
        return []
    fired = []
    for rule in kb.doctrinal_rules.values():
        if rule["trigger"]["type"] != "fallback":
            continue
        flag_name = rule["trigger"].get("params", {}).get("requires_flag")
        if not isinstance(flag_name, str) or flag_name not in _FACT_PATTERN_FIELDS:
            raise ValueError(
                f"doctrinal rule {rule['id']!r} has trigger.params.requires_flag={flag_name!r}, "
                f"which is not one of FactPattern's fields ({sorted(_FACT_PATTERN_FIELDS)}); "
                "refusing to silently never-fire (typo) or always-fire (e.g. a dunder name)"
            )
        if getattr(fp, flag_name):
            fired.append(rule)
    return fired


def _conflicting_authority_for(kb: KnowledgeBase, cited_authority_ids: set[str]):
    """Generic over any KB: surface every PrecedentRelation whose
    target_case is among the authorities actually being cited, where the
    relation represents live tension (criticizes/limits/overrules/
    questions) rather than mere lineage (follows/extends). Replaces two
    hardcoded relation-id strings ("pr_trident_criticizes_pge",
    "pr_newport_limits_pge") that were appended by name in specific
    branches; this version finds them -- and the statutory KB's
    pr_loper_overrules_chevron -- the same way, from data, with no
    per-relation code."""
    out = [
        rel["id"]
        for rel in kb.precedent_relations.values()
        if rel["target_case"] in cited_authority_ids and rel["relation"] in TENSION_RELATIONS
    ]
    return sorted(out)


def annotate_clause(kb: KnowledgeBase, clause_id: str, jurisdiction: str, fp: FactPattern) -> dict:
    threshold = _apply_threshold(kb, jurisdiction, fp)

    evidence_rules = _apply_evidence_conflict_rules(kb, fp)
    canon_rules = _apply_canons(kb, fp)
    fallback_rules = _apply_fallback(kb, fp, resolved_so_far=bool(evidence_rules or canon_rules))

    all_rules_sorted = sorted(evidence_rules + canon_rules + fallback_rules, key=lambda r: r["priority"])

    applicable_rules = []
    authority_ids: set[str] = set()
    if threshold.get("authority"):
        authority_ids.add(threshold["authority"])
    for rule in all_rules_sorted:
        primary_authority = rule["authority_basis"][0]
        weight = weighting.compute_weight(kb.authorities[primary_authority], jurisdiction)
        applicable_rules.append({"rule_id": rule["id"], "priority": rule["priority"], "weight": weight})
        authority_ids.update(rule["authority_basis"])

    citations = []
    for aid in sorted(authority_ids):
        authority = kb.authorities[aid]
        citations.append(
            {
                "authority_id": aid,
                "weight": weighting.compute_weight(authority, jurisdiction),
                "role": weighting.role_of(authority, jurisdiction),
            }
        )
    citations.sort(key=lambda c: -c["weight"])

    conflicting = _conflicting_authority_for(kb, authority_ids)

    if all_rules_sorted:
        lead = all_rules_sorted[0]
        posture = (
            f"Threshold: {threshold['outcome']}. "
            f"Controlling interpretive rule: {lead['name']} (priority {lead['priority']} of {len(all_rules_sorted)} triggered)."
        )
    else:
        posture = f"Threshold: {threshold['outcome']}. No downstream interpretive rule triggered by this fact pattern."

    return {
        "clause_id": clause_id,
        "jurisdiction": jurisdiction,
        "threshold_determination": threshold,
        "applicable_rules": applicable_rules,
        "conflicting_authority": conflicting,
        "recommended_interpretive_posture": posture,
        "citations": citations,
    }
