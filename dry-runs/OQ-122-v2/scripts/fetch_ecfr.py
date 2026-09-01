#!/usr/bin/env python3
"""Fetch a slice of the eCFR (Electronic Code of Federal Regulations) via the
official public versioner API (https://www.ecfr.gov/api/versioner/v1/) and
save the raw structure + full text to data/raw/.

This is the *only* network-touching script in the project. Everything else
(the MCP server, the corpus builder) works off the cached JSON/XML this
script produces, so the server itself never depends on network access at
query time.

Retry policy: this environment's bash is broken (Cygwin DLL load failure),
so lib/retry.sh (the harness-provided retry helper) cannot be sourced here.
This reimplements the same retry-with-backoff contract in Python instead:
up to N attempts, exponential backoff between attempts.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
API_ROOT = "https://www.ecfr.gov/api/versioner/v1"


def retry(max_attempts: int, base_delay: float, fn, *args, **kwargs):
    attempt = 1
    delay = base_delay
    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, mirrors lib/retry.sh
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


def fetch_latest_issue_date(title: int) -> str:
    data = json.loads(retry(4, 2, http_get, f"{API_ROOT}/titles.json"))
    for t in data["titles"]:
        if t["number"] == title:
            return t["latest_issue_date"]
    raise RuntimeError(f"title {title} not found in titles.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--title", type=int, default=16)
    ap.add_argument("--part", type=int, default=312)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD; defaults to the title's latest issue date")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    date = args.date or fetch_latest_issue_date(args.title)
    print(f"Using title {args.title} as of {date}")

    structure_url = f"{API_ROOT}/structure/{date}/title-{args.title}.json"
    structure = retry(4, 2, http_get, structure_url)
    struct_path = RAW_DIR / f"structure_title{args.title}_{date}.json"
    struct_path.write_bytes(structure)
    print(f"saved {struct_path} ({len(structure)} bytes)")

    full_url = f"{API_ROOT}/full/{date}/title-{args.title}.xml?part={args.part}"
    full_xml = retry(4, 2, http_get, full_url)
    xml_path = RAW_DIR / f"title{args.title}_part{args.part}_{date}.xml"
    xml_path.write_bytes(full_xml)
    print(f"saved {xml_path} ({len(full_xml)} bytes)")

    manifest = {
        "title": args.title,
        "part": args.part,
        "date": date,
        "structure_file": struct_path.name,
        "xml_file": xml_path.name,
        "source_urls": {"structure": structure_url, "full_text": full_url},
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    manifest_path = RAW_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"saved {manifest_path}")


if __name__ == "__main__":
    main()
