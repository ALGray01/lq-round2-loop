"""
Regression tests for three failure modes a round-2 attacker-persona audit
found in `_apply_fallback`'s original `getattr(fp, flag_name, False)`
mechanism: a typo'd `requires_flag` silently never fired, a dunder name
like `__class__` silently always fired (any class object is truthy), and a
non-string value crashed with an opaque TypeError. All three are
constructed here against a minimal in-repo KB (not the real
contract/statutory KBs, since the goal is testing the validation itself,
not real doctrine) and confirmed to now raise a clear ValueError instead of
misbehaving.
"""

from methodology_layer.engine import FactPattern, annotate_clause
from methodology_layer.models import KnowledgeBase

BASE_KB_DATA = {
    "authorities": [
        {"id": "case_x", "type": "case", "citation": "Some Case, 1 F.3d 1 (1st Cir. 1999)", "home_jurisdiction": "US-CA"}
    ],
    "precedent_relations": [],
    "hierarchies": [],
}


def _kb_with_fallback_rule(requires_flag):
    data = dict(BASE_KB_DATA)
    data["doctrinal_rules"] = [
        {
            "id": "rule_test_fallback",
            "name": "Test fallback rule",
            "statement": "irrelevant",
            "authority_basis": ["case_x"],
            "trigger": {"type": "fallback", "params": {"requires_flag": requires_flag}},
            "priority": 90,
        }
    ]
    return KnowledgeBase(data)


def test_typo_in_requires_flag_raises_instead_of_silently_never_firing():
    kb = _kb_with_fallback_rule("unequal_bargainin_power")  # typo, missing 'g'
    fp = FactPattern(unequal_bargaining_power=True)
    try:
        annotate_clause(kb, "c1", "US-CA", fp)
        assert False, "expected ValueError for a requires_flag that doesn't name a real FactPattern field"
    except ValueError as e:
        assert "not one of FactPattern's fields" in str(e)


def test_dunder_requires_flag_raises_instead_of_silently_always_firing():
    kb = _kb_with_fallback_rule("__class__")
    fp = FactPattern()  # no flags set at all
    try:
        annotate_clause(kb, "c2", "US-CA", fp)
        assert False, "expected ValueError for a dunder requires_flag, not an unconditional fire"
    except ValueError:
        pass


def test_non_string_requires_flag_raises_a_clear_error_not_a_bare_typeerror():
    kb = _kb_with_fallback_rule(123)
    fp = FactPattern()
    try:
        annotate_clause(kb, "c3", "US-CA", fp)
        assert False, "expected a clear ValueError, not a bare TypeError from getattr"
    except ValueError as e:
        assert "not one of FactPattern's fields" in str(e)
    except TypeError:
        assert False, "should not reach a bare TypeError -- requires_flag must be validated first"


def test_fallback_rule_with_no_params_key_raises_cleanly_not_keyerror():
    """Round-4 attacker finding: the schema only requires trigger.type, not
    trigger.params, so a schema-valid rule with no params key at all
    crashed _apply_fallback with a bare KeyError. Fixed via .get("params",
    {}); confirms it now reaches the same clear ValueError path as a
    missing requires_flag, not an uncaught KeyError."""
    kb = KnowledgeBase(
        {
            **BASE_KB_DATA,
            "doctrinal_rules": [
                {
                    "id": "rule_no_params",
                    "name": "No params rule",
                    "statement": "irrelevant",
                    "authority_basis": ["case_x"],
                    "trigger": {"type": "fallback"},
                    "priority": 90,
                }
            ],
        }
    )
    fp = FactPattern(unequal_bargaining_power=True)
    try:
        annotate_clause(kb, "c5", "US-CA", fp)
        assert False, "expected ValueError for a fallback rule with no trigger.params at all"
    except ValueError as e:
        assert "not one of FactPattern's fields" in str(e)
    except KeyError:
        assert False, "should not reach a bare KeyError -- missing params must be handled, not crash"


def test_evidence_conflict_sources_must_be_a_list_not_a_bare_string():
    """Round-4 attacker finding: passing a bare string instead of a list
    for evidence_conflict_sources didn't crash -- Python's `in` on a string
    does substring matching, so "express_terms" would silently "match"
    against a garbage string like "xexpress_termsy". Now raises instead."""
    from methodology_layer.models import REPO_ROOT, load_kb

    kb = load_kb(REPO_ROOT / "knowledge_base" / "contract_interpretation" / "kb.yaml")
    fp = FactPattern(contract_type="goods_sale", evidence_conflict_sources="xexpress_termsy")
    try:
        annotate_clause(kb, "c6", "US-CA", fp)
        assert False, "expected ValueError for a bare string instead of a list"
    except ValueError as e:
        assert "must be a list of strings" in str(e)


def test_valid_requires_flag_still_fires_normally():
    """Confirms the fix didn't break the normal case while closing the gap."""
    kb = _kb_with_fallback_rule("unequal_bargaining_power")
    fp = FactPattern(unequal_bargaining_power=True)
    result = annotate_clause(kb, "c4", "US-CA", fp)
    assert [r["rule_id"] for r in result["applicable_rules"]] == ["rule_test_fallback"]
