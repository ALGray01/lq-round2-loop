"""Load and schema-validate the knowledge base. Single source of truth for
structure is schema/methodology_layer.schema.json; this module does not
duplicate it in a second, potentially-drifting model definition."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "methodology_layer.schema.json"


class KnowledgeBase:
    def __init__(self, data: dict):
        self.data = data
        self.authorities = {a["id"]: a for a in data["authorities"]}
        self.precedent_relations = {p["id"]: p for p in data["precedent_relations"]}
        self.doctrinal_rules = {r["id"]: r for r in data["doctrinal_rules"]}
        self.hierarchies = {h["id"]: h for h in data["hierarchies"]}

    def rules_by_jurisdiction(self, trigger_type: str, jurisdiction: str):
        out = []
        for r in self.doctrinal_rules.values():
            if r["trigger"]["type"] != trigger_type:
                continue
            scope = r.get("jurisdiction_scope") or []
            if scope and jurisdiction not in scope:
                continue
            out.append(r)
        return out

    def relations_involving(self, case_id: str):
        return [
            p
            for p in self.precedent_relations.values()
            if p["source_case"] == case_id or p["target_case"] == case_id
        ]


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_kb(path: str | Path, validate: bool = True) -> KnowledgeBase:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    if validate:
        schema = load_schema()
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
        if errors:
            messages = "\n".join(f"  - {'/'.join(str(p) for p in e.path)}: {e.message}" for e in errors)
            raise ValueError(f"Knowledge base at {path} failed schema validation:\n{messages}")

    return KnowledgeBase(data)
