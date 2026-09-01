"""
A deliberately realistic "naive" extractor: the kind of code a team writes
in an afternoon to pull the newest reply out of an email chain. It is NOT a
strawman built to fail - it uses two genuine, independently-maintained
libraries doing the two hard parts:

  - Python's stdlib `email` package (compat32 policy - the classic
    `email.message_from_bytes` call, exactly what most quick scripts use)
    for MIME structure and Content-Transfer-Encoding decoding.
  - `email_reply_parser` (PyPI, a Python port of GitHub's original
    email_reply_parser gem) for stripping quoted history off the body text.

The specific choices below are the realistic mistakes a naive implementation
makes, called out inline. This is the ONE thing under test; everything else
(the corpus, the manifest) exists to find where it breaks.
"""
import email
import email.header
import html as html_lib
import re
from pathlib import Path

import extract_msg
from email_reply_parser import EmailReplyParser


def html_to_text_naive(raw_html: str) -> str:
    """A 'tried a little, not a real HTML parser' tag-stripper: attempts to
    preserve line breaks at block-level tags, then strips everything else
    with a single regex. This is a common middle ground - not maximally
    careless, but not a real DOM/tree-based HTML-to-text converter either."""
    text = re.sub(r"(?i)<br\s*/?>", "\n", raw_html)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"(?i)</tr>", "\n", text)
    text = re.sub(r"(?i)</t[dh]>", " ", text)
    text = re.sub(r"(?i)<script.*?</script>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*\n+", "\n", text)
    return text.strip()


def naive_body_from_eml(raw_bytes: bytes):
    """Returns (body_text, raw_subject). Mistakes baked in, on purpose:

    1. Uses email.message_from_bytes (compat32) - headers are NOT
       automatically RFC 2047-decoded, so an encoded-word Subject comes back
       as literal '=?UTF-8?B?...?=' text unless the caller remembers to run
       email.header.decode_header explicitly (this extractor doesn't).
    2. Prefers the first text/plain part over text/html, unconditionally -
       even when the plain part is a content-free client placeholder and the
       real content only exists in the HTML part.
    3. Falls back to a crude regex tag-strip of text/html only when there is
       no text/plain part at all.
    4. Correctly reverses Content-Transfer-Encoding via get_payload(decode=True)
       (the one part of this that IS done right - forgetting this kwarg is
       an even more common bug, but testing it wouldn't teach us anything
       past 'remember the kwarg').
    5. Hardcodes UTF-8 for character decoding, ignoring whatever charset the
       part actually declares. This is the single most common naive-decoder
       bug in the wild.
    """
    msg = email.message_from_bytes(raw_bytes)
    raw_subject = msg.get("Subject", "") or ""

    plain_part = None
    html_part = None
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == "text/plain" and plain_part is None:
            plain_part = part
        elif ctype == "text/html" and html_part is None:
            html_part = part

    if plain_part is not None:
        payload = plain_part.get_payload(decode=True) or b""
        text = payload.decode("utf-8", errors="replace")
        return text, raw_subject

    if html_part is not None:
        payload = html_part.get_payload(decode=True) or b""
        raw_html = payload.decode("utf-8", errors="replace")
        return html_to_text_naive(raw_html), raw_subject

    return "", raw_subject


def naive_body_from_msg(path: str):
    """Same 'prefer plain, fall back to crude HTML strip' policy, via
    extract-msg (PyPI) - the standard third-party library for reading .msg
    files without Outlook installed. Subject comes back correctly decoded
    because .msg stores it as a native Unicode property (PidTagSubject),
    not a transport-encoded header - so the RFC 2047 failure mode is
    specific to .eml and won't reproduce here."""
    m = extract_msg.Message(path)
    try:
        subject = m.subject or ""
        if m.body:
            return m.body, subject
        if m.htmlBody:
            raw_html = m.htmlBody.decode("utf-8", errors="replace") if isinstance(m.htmlBody, bytes) else m.htmlBody
            return html_to_text_naive(raw_html), subject
        return "", subject
    finally:
        m.close()


def extract(path: Path):
    """Runs the full naive pipeline for one fixture. Returns a dict with the
    extracted latest-message text, the raw/decoded subject pair, and any
    exception the naive pipeline raised (crash is itself a result worth
    reporting, not something to catch-and-hide)."""
    result = {"file": path.name, "error": None, "latest_message": "", "subject": ""}
    try:
        if path.suffix.lower() == ".msg":
            body_text, subject = naive_body_from_msg(str(path))
        else:
            raw_bytes = path.read_bytes()
            # NB: subject is deliberately NOT run through email.header.decode_header
            # here - that omission is exactly the failure mode f17 exercises.
            body_text, subject = naive_body_from_eml(raw_bytes)
        result["subject"] = subject
        result["latest_message"] = EmailReplyParser.parse_reply(body_text).strip()
    except Exception as exc:  # a crash is a real, reportable failure mode
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result
