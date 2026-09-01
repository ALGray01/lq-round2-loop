#!/usr/bin/env python3
"""
Minimal extraction eval harness for OQ-112.

TASK: "pull the latest message from each chain" - given a native .eml or
.msg file that may be a multi-hop reply/forward chain, extract just the
newest message's text, with quoted history and signatures/disclaimers
stripped. (.msg files in this corpus are single messages, not chains -
"latest message" there just means "the message body".)

PIPELINE UNDER TEST (deliberately representative of common pipeline code,
not tuned to this corpus):
  1. `extract_body()` - stdlib `email` MIME walk: prefer text/plain, decode
     using the part's declared charset/Content-Transfer-Encoding, fall back
     to text/html with a quick regex tag-strip if no text/plain part
     exists. Does NOT recurse into message/rfc822 attachments (top-level
     body only - a common real-world shortcut).
  2. `email_reply_parser.EmailReplyParser.parse_reply()` - a real,
     independently-authored third-party library (github.com/zapier's port
     of GitHub's email_reply_parser, pip package `email_reply_parser`) run
     on the decoded body text to strip quoted history/signatures. This is
     NOT code written for this corpus - it is an off-the-shelf library, so
     its failures are genuine, not self-graded (see FAILURE-CLASSES.md #7:
     a mock harness testing only itself proves nothing).
  (.msg files use extract_body_msg() instead of step 1: the real,
  independent `extract-msg` library's PR_BODY/RTF-de-encapsulation
  properties, still followed by the same step-2 reply-parser + grader.)

GRADING (generic, applied identically to every file - no per-file
branches): normalize whitespace on both the expected and extracted text,
check the expected text is a substring of the extracted text (recall), then
check what's left over in the extraction after removing that match. Small
leftover (signature/disclaimer noise) = PASS with a warning. Large leftover
that still contains quote-signal tokens (">", "wrote:", "original
message") = FAIL: quoted history leaked through. Missing expected content
entirely = FAIL: content lost.

Usage: `python harness.py` (writes results/harness_output.json and prints
a summary table).
"""
import glob
import html
import json
import os
import re
import sys
import traceback
from email import message_from_bytes
from email.message import Message

from email_reply_parser import EmailReplyParser
import extract_msg

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "corpus")
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "corpus", "manifest.json")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
QUOTE_SIGNAL_RE = re.compile(
    r"(^>|-----Original Message-----|On .{0,60}wrote:|wrote:$)", re.IGNORECASE | re.MULTILINE
)


def naive_html_to_text(html_body):
    """Deliberately simple: no table/structure awareness (this is the
    behaviour we want to catch failing on F8-tagged files)."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html_body)
    text = re.sub(r"(?i)<(br|/p|/div|/tr)\s*/?>", "\n", text)
    text = TAG_RE.sub("", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*\n+", "\n\n", text)
    return text.strip()


def decode_part(part: Message):
    payload = part.get_payload(decode=True)
    if payload is None:
        return None, "no-payload"
    charset = part.get_content_charset() or "us-ascii"
    try:
        return payload.decode(charset), None
    except (LookupError, UnicodeDecodeError) as e:
        try:
            return payload.decode(charset, errors="replace"), f"decode-error:{e.__class__.__name__} (used errors=replace)"
        except Exception as e2:
            return None, f"decode-fatal:{e2.__class__.__name__}"


def extract_body(raw_bytes):
    """Returns (text, diagnostics dict). Never raises - records failures."""
    diag = {"defects": [], "content_path": None, "notes": []}
    try:
        msg = message_from_bytes(raw_bytes)
    except Exception as e:
        diag["notes"].append(f"parse-fatal:{e.__class__.__name__}: {e}")
        return "", diag

    defects = list(getattr(msg, "defects", []))
    if defects:
        diag["defects"] = [type(d).__name__ for d in defects]

    plain_part = None
    html_part = None
    for part in msg.walk():
        ctype = part.get_content_type()
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_filename():
            continue  # treat as attachment, not body candidate
        if ctype == "text/plain" and plain_part is None:
            plain_part = part
        elif ctype == "text/html" and html_part is None:
            html_part = part

    if plain_part is not None:
        text, err = decode_part(plain_part)
        diag["content_path"] = "text/plain"
        if err:
            diag["notes"].append(err)
        if text is None:
            diag["notes"].append("plain part present but undecodable")
            text = ""
        return text, diag

    if html_part is not None:
        raw_html, err = decode_part(html_part)
        diag["content_path"] = "text/html (naive tag-strip fallback)"
        if err:
            diag["notes"].append(err)
        if raw_html is None:
            diag["notes"].append("html part present but undecodable")
            return "", diag
        return naive_html_to_text(raw_html), diag

    # No usable text part found at the top level.
    if not msg.is_multipart():
        text, err = decode_part(msg)
        if text is not None:
            diag["content_path"] = f"single-part fallback ({msg.get_content_type()})"
            if err:
                diag["notes"].append(err)
            return text, diag

    diag["notes"].append("no text/plain or text/html part found")
    return "", diag


def extract_body_msg(path):
    """.msg counterpart of extract_body(): uses extract-msg (a real,
    independent third-party .msg reader) rather than any code written for
    this corpus. Tries the plain-text body property first, then falls back
    to RTF de-encapsulation - which only works for Outlook's "encapsulated
    HTML/plain" RTF convention, not arbitrary formatted RTF (a genuine,
    documented limitation of the library, not a bug introduced here; see
    README.md)."""
    diag = {"defects": [], "content_path": None, "notes": []}
    msg = None
    try:
        msg = extract_msg.Message(path)
        if msg.body:
            diag["content_path"] = "PR_BODY (plain)"
            return msg.body, diag
        try:
            plain = msg.deencapsulateBody(msg.rtfBody, extract_msg.enums.DeencapType.PLAIN) if msg.rtfBody else None
        except Exception as e:
            plain = None
            diag["notes"].append(f"rtf-deencapsulate-failed:{e.__class__.__name__}: {e}")
        if plain:
            diag["content_path"] = "PR_RTF_COMPRESSED (de-encapsulated plain)"
            return plain, diag
        if msg.rtfBody:
            diag["notes"].append(
                "PR_BODY empty and RTF body present but not in Outlook's "
                "encapsulated-HTML/plain convention - extract-msg/RTFDE "
                "cannot recover text from genuinely-formatted RTF"
            )
        else:
            diag["notes"].append("no PR_BODY and no RTF body found")
        return "", diag
    except Exception:
        diag["notes"].append("extract_msg raised: " + traceback.format_exc(limit=2))
        return "", diag
    finally:
        if msg is not None:
            msg.close()


def normalize(text):
    return WS_RE.sub(" ", text).strip()


def grade(expected, extracted, diag):
    exp_n = normalize(expected)
    ext_n = normalize(extracted)

    if not ext_n:
        return "FAIL", "empty extraction", ext_n

    idx = ext_n.find(exp_n)
    if idx == -1:
        # NOTE: earlier draft of this grader fell back to matching only the
        # first 40 chars of `expected` when the full string wasn't found.
        # That produced a false PASS on file 06 (04_alt_html_plain_mismatch's
        # sibling case): the plain-text stub "Revised closing schedule
        # attached below - view in HTML." shares its opening clause with the
        # real HTML sentence, so a short prefix probe matched a wrong
        # extraction. Removed - require the FULL expected string verbatim
        # (after whitespace normalization) as a substring. No partial-credit
        # fallback, so this grader cannot be gamed by a shared opening
        # phrase the way the prefix probe was.
        return "FAIL", "expected content not found in extraction", ext_n

    leftover = (ext_n[:idx] + ext_n[idx + len(exp_n):]).strip()

    # NOTE: an earlier version of this function checked `len(leftover) <= 60`
    # BEFORE the quote-signal regex, so a leftover under the threshold
    # returned PASS unconditionally without the regex ever running - e.g.
    # `grade(exp, exp + " > see above wrote:", {})` (18-char leftover
    # containing '>' and 'wrote:') scored PASS. Caught by an adversarial
    # audit. Fixed: the quote-signal check now always runs first, so any
    # leaked quote marker fails regardless of how short the leftover is.
    if QUOTE_SIGNAL_RE.search(leftover):
        return "FAIL", f"quoted history leaked through ({len(leftover)} extra chars incl. quote markers)", ext_n

    if len(leftover) <= 60:
        status = "PASS"
        reason = "clean" if not leftover else f"PASS with minor trailing noise ({len(leftover)} chars)"
        return status, reason, ext_n

    return "PASS", f"PASS with {len(leftover)} chars of extra trailing content (signature/disclaimer)", ext_n


def main():
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = []
    corpus_root = os.path.realpath(CORPUS_DIR)
    for entry in manifest:
        rel = entry["file"] if "/" in entry["file"] else f"eml/{entry['file']}"
        path = os.path.realpath(os.path.join(CORPUS_DIR, rel))
        # Manifest `file` values must resolve to a path inside corpus/ -
        # an adversarial audit demonstrated that an absolute path or a
        # `../` traversal in this field (e.g. "C:/Windows/win.ini") reached
        # open() unmodified and had its contents graded/written into
        # results/harness_output.json. os.path.join() silently discards
        # its first argument when the second is an absolute path on
        # Windows, so a startswith() check on the *input* string is not
        # sufficient - must check the resolved, real path.
        if os.path.commonpath([corpus_root, path]) != corpus_root:
            raise ValueError(f"manifest entry {entry.get('id')!r} file path escapes corpus/: {entry['file']!r}")
        is_msg = entry["file"].endswith(".msg")

        diag = {}
        if is_msg:
            try:
                body_text, diag = extract_body_msg(path)
            except Exception:
                body_text = ""
                diag = {"notes": ["extract_body_msg raised: " + traceback.format_exc(limit=2)]}
        else:
            with open(path, "rb") as f:
                raw = f.read()
            try:
                body_text, diag = extract_body(raw)
            except Exception:
                body_text = ""
                diag = {"notes": ["extract_body raised: " + traceback.format_exc(limit=2)]}

        try:
            reply_text = EmailReplyParser.parse_reply(body_text)
        except Exception:
            reply_text = body_text
            diag.setdefault("notes", []).append(
                "email_reply_parser raised: " + traceback.format_exc(limit=2)
            )

        status, reason, ext_n = grade(entry["expected_latest_message"], reply_text, diag)
        results.append({
            "id": entry["id"],
            "file": entry["file"],
            "features": entry["features"],
            "status": status,
            "reason": reason,
            "content_path": diag.get("content_path"),
            "defects": diag.get("defects", []),
            "notes": diag.get("notes", []),
            "extracted_preview": ext_n[:160],
        })

    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_fail = sum(1 for r in results if r["status"] == "FAIL")

    print(f"{'ID':<4} {'STATUS':<6} {'FEATURES':<20} FILE")
    print("-" * 90)
    for r in results:
        feats = ",".join(r["features"])
        print(f"{r['id']:<4} {r['status']:<6} {feats:<20} {r['file']}")
        if r["status"] == "FAIL" or r["notes"] or r["defects"]:
            detail = r["reason"]
            if r["notes"]:
                detail += " | notes: " + "; ".join(n.splitlines()[0] for n in r["notes"])
            if r["defects"]:
                detail += " | defects: " + ",".join(r["defects"])
            print(f"     -> {detail}")

    print("-" * 90)
    print(f"TOTAL: {len(results)}  PASS: {n_pass}  FAIL: {n_fail}")

    out = {
        "summary": {"total": len(results), "pass": n_pass, "fail": n_fail},
        "results": results,
    }
    out_path = os.path.join(RESULTS_DIR, "harness_output.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nFull results -> {out_path}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
