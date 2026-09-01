"""
Runs the same naive extractor (harness/extract_latest.py) against real,
independently-sourced .eml samples (real_world_spotcheck/, from talon's own
test fixtures - see NOTICE.md) instead of the synthetic corpus. There is no
hand-authored ground truth here (that would require re-litigating what
"the real reply" is for someone else's captured email); this is a
qualitative spot check, not a scored eval, printing what the extractor
returns for manual read-through.

Run: python scripts/run_real_world_spotcheck.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.extract_latest import extract  # noqa: E402

DIR = ROOT / "real_world_spotcheck"

lines = []
for path in sorted(DIR.glob("*.eml")):
    result = extract(path)
    lines.append(f"=== {path.name} ===")
    if result["error"]:
        lines.append(f"ERROR: {result['error']}")
    else:
        lines.append(f"subject: {result['subject']!r}")
        lines.append(f"latest_message:\n{result['latest_message']}")
    lines.append("")

report = "\n".join(lines)
print(report)
(DIR / "spotcheck_report.txt").write_text(report, encoding="utf-8")
