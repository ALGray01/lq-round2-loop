from pathlib import Path

from methodology_layer.models import REPO_ROOT, load_kb

KB_PATH = REPO_ROOT / "knowledge_base" / "contract_interpretation" / "kb.yaml"


def test_kb_validates_against_schema():
    # load_kb(validate=True) raises ValueError on schema mismatch; a clean
    # load is the assertion.
    kb = load_kb(KB_PATH, validate=True)
    assert len(kb.authorities) > 0
    assert len(kb.doctrinal_rules) > 0


def test_schema_rejects_a_broken_kb(tmp_path):
    """A scorer that has never been shown a case it should fail proves
    nothing (FAILURE-CLASSES.md #4). Feed the validator a KB with a required
    field missing and confirm it actually raises."""
    broken = tmp_path / "broken.yaml"
    broken.write_text(
        """
authorities:
  - id: bad_authority
    type: statute
    # citation and home_jurisdiction deliberately omitted -- both required
precedent_relations: []
doctrinal_rules: []
hierarchies: []
""",
        encoding="utf-8",
    )
    try:
        load_kb(broken, validate=True)
        assert False, "expected schema validation to reject a KB missing required fields"
    except ValueError:
        pass


def test_every_rule_authority_basis_resolves():
    """Every DoctrinalRule.authority_basis id must point at a real Authority
    in the same KB -- otherwise the engine would silently look up a
    nonexistent citation."""
    kb = load_kb(KB_PATH, validate=True)
    for rule in kb.doctrinal_rules.values():
        for aid in rule["authority_basis"]:
            assert aid in kb.authorities, f"rule {rule['id']} cites unknown authority {aid}"


def test_every_hierarchy_rule_id_resolves():
    kb = load_kb(KB_PATH, validate=True)
    for hierarchy in kb.hierarchies.values():
        for rid in hierarchy["ordered_rule_ids"]:
            assert rid in kb.doctrinal_rules, f"hierarchy {hierarchy['id']} references unknown rule {rid}"


def test_every_precedent_relation_case_resolves():
    kb = load_kb(KB_PATH, validate=True)
    for rel in kb.precedent_relations.values():
        assert rel["source_case"] in kb.authorities
        assert rel["target_case"] in kb.authorities


def test_schema_rejects_unexpected_fields(tmp_path):
    """Raised by the attacker-persona audit (reserve phase): the schema
    originally had no `additionalProperties: false` anywhere, so a typo'd
    or injected field on an Authority (e.g. a stray key that isn't part of
    the schema) would pass validation silently instead of being caught.
    Confirms the fix actually closes that gap rather than just adding the
    keyword without checking it works."""
    kb_with_stray_field = tmp_path / "stray.yaml"
    kb_with_stray_field.write_text(
        """
authorities:
  - id: case_x
    type: case
    citation: "Some Case, 1 F.3d 1 (9th Cir. 1999)"
    home_jurisdiction: US-CA
    unexpected_injected_field: "this should not be allowed through"
precedent_relations: []
doctrinal_rules: []
hierarchies: []
""",
        encoding="utf-8",
    )
    try:
        load_kb(kb_with_stray_field, validate=True)
        assert False, "expected schema validation to reject an unexpected field on Authority"
    except ValueError:
        pass
