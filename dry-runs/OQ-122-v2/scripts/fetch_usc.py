#!/usr/bin/env python3
"""Fetch the U.S. Code sections that 16 CFR Part 312 cites as its enabling
statute (15 U.S.C. 6501-6506, the Children's Online Privacy Protection
Act) via GovInfo's public citation-based link service
(https://www.govinfo.gov/link/uscode/{title}/{section}).

Unlike eCFR, there is no clean per-section XML/JSON REST API for the
U.S. Code that this project found (uscode.house.gov's bulk data is
organized by Congress/release-point ZIP files, not addressable by
citation). GovInfo's link service *is* addressable by citation, but each
request resolves to a rendered PDF of the printed statute page(s)
surrounding that section - the same "Page 2243/2244" scanned-book layout
as the physical U.S. Code volumes, including tail text from whatever
section precedes it on the same printed page. This script fetches the
raw PDFs; scripts/build_usc_corpus.py does the actual text extraction and
section-boundary cleanup.
"""
import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "usc"
LINK_ROOT = "https://www.govinfo.gov/link/uscode"

SECTIONS = ["6501", "6502", "6503", "6504", "6505", "6506"]


def retry(max_attempts: int, base_delay: float, fn, *args, **kwargs):
    attempt = 1
    delay = base_delay
    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - mirrors lib/retry.sh's contract
            if attempt >= max_attempts:
                print(f"retry: giving up after {attempt} attempts: {exc}", file=sys.stderr)
                raise
            print(f"retry: attempt {attempt} failed ({exc}), retrying in {delay}s", file=sys.stderr)
            time.sleep(delay)
            attempt += 1
            delay *= 2


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "OQ-122 statutes-mcp dry run (contact: redacted@example.com)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--title", type=int, default=15)
    ap.add_argument("--sections", nargs="+", default=SECTIONS)
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    for section in args.sections:
        url = f"{LINK_ROOT}/{args.title}/{section}"
        print(f"fetching {url}")
        pdf_bytes = retry(4, 2, http_get, url)
        out_path = RAW_DIR / f"usc{args.title}_{section}.pdf"
        out_path.write_bytes(pdf_bytes)
        print(f"  saved {out_path} ({len(pdf_bytes)} bytes)")


if __name__ == "__main__":
    main()
