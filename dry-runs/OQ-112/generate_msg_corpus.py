#!/usr/bin/env python3
"""
Generates the native .msg (OLE/CFB, [MS-OXMSG]) fixtures into corpus/msg/,
using msg_writer.py (a from-scratch minimal writer - no Python package for
writing .msg exists; see msg_writer.py's docstring). Appends their entries
to corpus/manifest.json alongside the .eml entries from generate_corpus.py.

Run generate_corpus.py first (or these entries will be the whole manifest).
"""
import json
import os
from datetime import datetime, timezone

from msg_writer import save_msg

OUT_DIR = os.path.join(os.path.dirname(__file__), "corpus", "msg")
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "corpus", "manifest.json")
os.makedirs(OUT_DIR, exist_ok=True)

NEW_ENTRIES = []


def register(fid, filename, features, scenario, expected_latest, notes=""):
    NEW_ENTRIES.append({
        "id": fid,
        "file": "msg/" + filename,
        "features": features,
        "scenario": scenario,
        "expected_latest_message": expected_latest,
        "notes": notes,
    })


def gen_25():
    body = (
        "Confirming the wire went out this morning for the escrow release - "
        "$480,000 to the account on file. Let me know once your side "
        "reconciles."
    )
    fn = "25_native_msg_basic.msg"
    save_msg(
        os.path.join(OUT_DIR, fn),
        subject="Wire confirmation - escrow release",
        body_text=body,
        sender_name="Sarah Chen", sender_email="sarah.chen@meridiancole-law.example",
        to_name="David Osei", to_email="d.osei@harrowgate-partners.example",
        sent_dt=datetime(2026, 7, 22, 10, 5, tzinfo=timezone.utc),
    )
    register("25", fn, ["F21"],
              "Plain native .msg (OLE/CFB binary container, MS-OXMSG "
              "property streams) - no MIME headers or boundaries exist "
              "anywhere in the file, unlike every .eml in this corpus.",
              body,
              notes="Hand-built with cfb_writer.py/msg_writer.py (no pip "
                    "package for writing .msg exists); structural "
                    "correctness verified by round-tripping through the "
                    "independent extract-msg library, not just self-parsed.")


def gen_26():
    rtf = (
        r"{\rtf1\ansi\ansicpg1252\deff0"
        r"{\fonttbl{\f0\fswiss Calibri;}}"
        r"{\colortbl;\red255\green0\blue0;}"
        r"\deflang1033\pard\f0\fs22 "
        r"Please see amended clause in red below - liquidated "
        r"damages capped at \cf1\b 10%\cf0\b0  of contract value, down "
        r"from the original 15%.\par"
        r"}"
    )
    plain_fallback = (
        "Please see amended clause in red below - liquidated damages "
        "capped at 10% of contract value, down from the original 15%."
    )
    fn = "26_native_msg_rtf_only_body.msg"
    save_msg(
        os.path.join(OUT_DIR, fn),
        subject="Clause 8.2 amended (RTF redline)",
        body_text="",
        sender_name="Mike Torres", sender_email="mike.torres@meridiancole-law.example",
        to_name="David Osei", to_email="d.osei@harrowgate-partners.example",
        sent_dt=datetime(2026, 7, 22, 11, 40, tzinfo=timezone.utc),
        rtf_body=rtf,
    )
    register("26", fn, ["F21", "F22", "F9"],
              "Native .msg with NO PR_BODY plain-text property set at all "
              "(empty string) - the only body representation is "
              "PR_RTF_COMPRESSED, the historic Outlook default. A "
              "plain/HTML-only body reader gets nothing; extracting the "
              "text (and the red/bold tracked-change markup) requires RTF "
              "decompression + de-escaping.",
              plain_fallback,
              notes="RTF uses the uncompressed 'MELA' variant of the "
                    "[MS-OXRTFCP] compressed-RTF container (real LZFu "
                    "compression not implemented) - still a spec-valid "
                    "CompressedRTFStream, verified readable via extract-msg.")


def gen_27():
    body = (
        "Anbei die unterschriebene Vollmacht als Anhang - bitte bis Freitag "
        "bestätigen."
    )
    fn = "27_native_msg_with_attachment.msg"
    save_msg(
        os.path.join(OUT_DIR, fn),
        subject="Vollmacht - unterschrieben",
        body_text=body,
        sender_name="Priya Patel", sender_email="priya.patel@blackstoneridge.example",
        to_name="Sarah Chen", to_email="sarah.chen@meridiancole-law.example",
        sent_dt=datetime(2026, 7, 23, 8, 15, tzinfo=timezone.utc),
        attachments=[("Vollmacht_unterschrieben.pdf", b"%PDF-1.4 fake bytes " + b"y" * 64)],
    )
    register("27", fn, ["F21"],
              "Native .msg with a real binary attachment stored as an "
              "OLE sub-storage (__attach_version1.0_#00000000) rather "
              "than a MIME part - attachment discovery code written only "
              "for multipart MIME walking finds nothing here.",
              body)


def main():
    for gen in [gen_25, gen_26, gen_27]:
        gen()
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    existing_ids = {e["id"] for e in manifest}
    manifest.extend(e for e in NEW_ENTRIES if e["id"] not in existing_ids)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"Added {len(NEW_ENTRIES)} .msg entries -> {MANIFEST_PATH} (total {len(manifest)})")


if __name__ == "__main__":
    main()
