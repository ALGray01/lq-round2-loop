"""
Runs the naive extractor (harness/extract_latest.py) over every fixture in
corpus/, compares its output to the hand-authored ground truth in expected/,
and reports PASS/PARTIAL/FAIL per file plus a summary.

The grading itself is deliberately simple (normalized-text similarity via
difflib, no ML judge, nothing that could be "confidently wrong") precisely
so it stays auditable - see README's "Is the grader trustworthy?" section
for how this was checked against a case it should fail and a case it should
pass before being trusted.

Usage: python harness/run_eval.py [--verbose]
"""
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.extract_latest import extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
EXPECTED = ROOT / "expected"

PASS_THRESHOLD = 0.90
PARTIAL_THRESHOLD = 0.50


def normalize(text: str) -> str:
    # Deliberately does NOT strip a leading BOM (U+FEFF) - a stray BOM
    # character is exactly the failure 18_utf8_bom.eml is meant to surface,
    # and normalizing it away here would hide that failure from the report.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


TABLE_PASS_THRESHOLD = 0.98  # tables are binary-correct or not: a dropped row
# label (e.g. a rowspan association silently lost) only costs a few characters
# of edit distance but is a real, meaningful extraction failure. Plain
# character-similarity under-weights that, so table: fixtures get a much
# stricter bar than prose. This is a feature-tag rule (set from MANIFEST.csv,
# written independently at fixture-authoring time), not a per-file override.


def verdict(score: float, is_table: bool = False) -> str:
    pass_threshold = TABLE_PASS_THRESHOLD if is_table else PASS_THRESHOLD
    if score >= pass_threshold:
        return "PASS"
    if score >= PARTIAL_THRESHOLD:
        return "PARTIAL"
    return "FAIL"


def load_manifest():
    features = {}
    manifest_path = ROOT / "MANIFEST.csv"
    if manifest_path.exists():
        import csv
        with open(manifest_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                features[row["filename"]] = row["features"]
    return features


def run():
    subjects = json.loads((EXPECTED / "_subjects.json").read_text(encoding="utf-8"))
    features = load_manifest()

    files = sorted(list(CORPUS.glob("*.eml")) + list(CORPUS.glob("*.msg")))
    rows = []
    for path in files:
        expected_path = EXPECTED / (path.stem + ".txt")
        expected_text = expected_path.read_text(encoding="utf-8") if expected_path.exists() else ""
        result = extract(path)
        file_features = features.get(path.name, "")
        is_table = "table:" in file_features

        if result["error"]:
            score = 0.0
            v = "FAIL"
        else:
            score = similarity(result["latest_message"], expected_text)
            v = verdict(score, is_table=is_table)

        expected_subject = subjects.get(path.name, "")
        subject_ok = normalize(result.get("subject", "")) == normalize(expected_subject)

        rows.append({
            "file": path.name,
            "verdict": v,
            "score": score,
            "subject_ok": subject_ok,
            "error": result["error"],
            "expected": expected_text,
            "got": result["latest_message"],
            "expected_subject": expected_subject,
            "got_subject": result.get("subject", ""),
            "features": file_features,
        })
    return rows


def print_report(rows, verbose=False):
    n_pass = sum(1 for r in rows if r["verdict"] == "PASS")
    n_partial = sum(1 for r in rows if r["verdict"] == "PARTIAL")
    n_fail = sum(1 for r in rows if r["verdict"] == "FAIL")
    n_subject_fail = sum(1 for r in rows if not r["subject_ok"])

    print(f"{'FILE':45} {'VERDICT':8} {'SCORE':6} {'SUBJ':5}  FEATURES")
    print("-" * 130)
    for r in rows:
        subj_flag = "ok" if r["subject_ok"] else "FAIL"
        print(f"{r['file']:45} {r['verdict']:8} {r['score']:.2f}   {subj_flag:5}  {r['features']}")
        if verbose or r["verdict"] != "PASS" or not r["subject_ok"]:
            if r["error"]:
                print(f"    ERROR: {r['error']}")
            else:
                print(f"    expected: {r['expected'][:160]!r}")
                print(f"    got     : {r['got'][:160]!r}")
            if not r["subject_ok"]:
                print(f"    expected subject: {r['expected_subject']!r}")
                print(f"    got subject     : {r['got_subject']!r}")
    print("-" * 130)
    print(f"TOTAL: {len(rows)}   PASS: {n_pass}   PARTIAL: {n_partial}   FAIL: {n_fail}   "
          f"SUBJECT-MISMATCH: {n_subject_fail}")


def sanity_check(rows):
    """A scorer that always agrees with itself is worthless. Before trusting
    the numbers above, confirm the scorer actually discriminates: the
    positive control must pass, and at least one fixture designed to defeat
    the naive extractor must actually fail. If either check fails, the
    scorer (not the extractor) is the thing that's broken."""
    by_name = {r["file"]: r for r in rows}
    control = by_name.get("01_shallow_plain_control.eml")
    known_hard = by_name.get("08_html_table_merged_cells.eml")
    problems = []
    if control is None or control["verdict"] != "PASS":
        problems.append("Positive control (01_shallow_plain_control.eml) did not PASS - scorer or "
                         "extractor is broken even on the trivial case.")
    if known_hard is None or known_hard["verdict"] == "PASS":
        problems.append("Known-hard fixture (08_html_table_merged_cells.eml, HTML table with "
                         "merged cells) PASSED - the scorer is too lenient to be trustworthy, or "
                         "the naive extractor is stronger than assumed (worth investigating either way).")
    return problems


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv
    rows = run()
    print_report(rows, verbose=verbose)
    problems = sanity_check(rows)
    if problems:
        print("\nSCORER SANITY CHECK FAILED:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    else:
        print("\nScorer sanity check passed (control passes, at least one known-hard case fails).")
