"""
Character Error Rate (CER) scoring: edit_distance(candidate, ground_truth) / len(ground_truth).

Ground truth is a plain text file. Candidate can be plain text, or a JSON file produced
by our run_*.py scripts (a dict with a "lines" list of {"text": ...} entries) - in that
case all line texts are concatenated in order, space-joined, since line segmentation
(and therefore line order/count) differs per engine and isn't what we're scoring.

Stdlib only, no dependencies - so this can run even if pip installs are unavailable.
"""
import argparse
import json
import re
import sys


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


def normalize(s: str) -> str:
    s = s.replace("\r\n", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n+", " ", s)
    return s.strip()


def load_candidate(path: str, max_lines: int = None) -> str:
    if path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        lines = data.get("lines", [])
        if max_lines:
            lines = lines[:max_lines]
        return " ".join(l["text"] for l in lines)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ground_truth")
    ap.add_argument("candidate")
    ap.add_argument("--max-lines", type=int, default=None,
                     help="For JSON candidates: only use the first N detected line entries "
                          "(useful when ground truth only covers the top of a longer page)")
    args = ap.parse_args()

    with open(args.ground_truth, "r", encoding="utf-8") as f:
        gt = normalize(f.read())
    cand = normalize(load_candidate(args.candidate, args.max_lines))

    dist = levenshtein(cand, gt)
    cer = 100.0 * dist / max(len(gt), 1)
    print(f"{args.candidate}: CER = {cer:.1f}%  (edit_distance={dist}, gt_len={len(gt)}, cand_len={len(cand)})")


if __name__ == "__main__":
    main()
