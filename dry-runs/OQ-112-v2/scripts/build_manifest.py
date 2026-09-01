"""Merges the .eml and .msg per-fixture manifests written by the two
generator scripts into MANIFEST.csv at the repo root."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

rows = []
for fn in ["_eml_manifest.json", "_msg_manifest.json"]:
    p = ROOT / "scripts" / fn
    if p.exists():
        rows.extend(json.loads(p.read_text(encoding="utf-8")))

rows.sort(key=lambda r: r["filename"])

with open(ROOT / "MANIFEST.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["filename", "format", "features", "description", "expected_note"])
    w.writeheader()
    for r in rows:
        w.writerow(r)

print(f"Wrote MANIFEST.csv with {len(rows)} entries.")
