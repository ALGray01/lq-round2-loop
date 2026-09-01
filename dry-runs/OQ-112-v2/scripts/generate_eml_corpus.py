"""
Generates the .eml half of the corpus. Each fixture is either built as raw
RFC 5322 bytes (when the messiness IS the wire format: folded headers, wrong
charset, missing blank line before a quote marker, mixed line endings) or via
Python's email.message.EmailMessage (when the messiness is in the content,
not the transport encoding, and hand-rolling MIME boundaries would just be a
worse version of what the stdlib already does correctly).

Run: python scripts/generate_eml_corpus.py
Writes into corpus/ and expected/ (ground truth "latest message" text).
Also writes MANIFEST.csv describing every fixture (both .eml and .msg).
"""
import base64
import csv
import email.utils
import os
import quopri
import zipfile
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
EXPECTED = ROOT / "expected"
CORPUS.mkdir(exist_ok=True)
EXPECTED.mkdir(exist_ok=True)

MANIFEST = []
SUBJECTS = {}


def record(filename, fmt, features, description, expected_note=""):
    MANIFEST.append({
        "filename": filename,
        "format": fmt,
        "features": features,
        "description": description,
        "expected_note": expected_note,
    })


def write_raw(name, raw_bytes):
    (CORPUS / name).write_bytes(raw_bytes)
    # Ground truth for the "correct subject" secondary check: decode RFC 2047
    # encoded-words properly, regardless of how the fixture encoded them.
    import email as _email
    import email.header as _eheader
    parsed = _email.message_from_bytes(raw_bytes)
    raw_subject = parsed.get("Subject", "")
    try:
        SUBJECTS[name] = str(_eheader.make_header(_eheader.decode_header(raw_subject)))
    except Exception:
        SUBJECTS[name] = raw_subject


def write_expected(name, text):
    (EXPECTED / (Path(name).stem + ".txt")).write_text(text, encoding="utf-8")


def std_headers(msg_id_suffix, subject, frm="alice@example.com", to="bob@example.com", extra=""):
    return (
        f"From: {frm}\r\n"
        f"To: {to}\r\n"
        f"Subject: {subject}\r\n"
        f"Date: Mon, 12 Feb 2024 09:00:00 -0500\r\n"
        f"Message-ID: <{msg_id_suffix}@example.com>\r\n"
        f"MIME-Version: 1.0\r\n"
        f"{extra}"
    )


# ---------------------------------------------------------------------------
# 1. Shallow, single message, plain text. Positive control.
# ---------------------------------------------------------------------------
def f01():
    name = "01_shallow_plain_control.eml"
    body = "Hi Bob,\r\n\r\nThe filing is ready for your review. No changes since draft 3.\r\n\r\nAlice\r\n"
    raw = (
        std_headers("f01", "Filing ready for review", extra="Content-Type: text/plain; charset=utf-8\r\n")
        + "\r\n" + body
    ).encode()
    write_raw(name, raw)
    write_expected(name, "Hi Bob,\n\nThe filing is ready for your review. No changes since draft 3.\n\nAlice")
    record(name, "eml", "chain-depth:shallow (control)",
           "Single message, no history, no quoting. Baseline the parser must pass trivially.")


# ---------------------------------------------------------------------------
# 2. Classic '>' quoting, medium chain, plus a folded Content-Type header.
# ---------------------------------------------------------------------------
def f02():
    name = "02_classic_gt_quote_chain.eml"
    body = (
        "Agreed on the revised timeline, let's lock it in.\r\n"
        "\r\n"
        "> On Feb 10, 2024, Carol wrote:\r\n"
        "> Can we push the closing date by a week?\r\n"
        ">\r\n"
        "> > On Feb 9, 2024, Alice wrote:\r\n"
        "> > Draft 2 attached, please review the closing schedule.\r\n"
    )
    # Folded Content-Type header: RFC 5322 allows continuation lines starting
    # with whitespace. A regex header parser that assumes "one header, one
    # line" truncates this to just "multipart/mixed;" and loses the boundary.
    headers = (
        "From: bob@example.com\r\n"
        "To: alice@example.com, carol@example.com\r\n"
        "Subject: Re: Closing schedule\r\n"
        "Date: Mon, 12 Feb 2024 10:00:00 -0500\r\n"
        "Message-ID: <f02@example.com>\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/plain;\r\n"
        "  charset=utf-8\r\n"
    )
    raw = (headers + "\r\n" + body).encode()
    write_raw(name, raw)
    write_expected(name, "Agreed on the revised timeline, let's lock it in.")
    record(name, "eml", "quoting:classic-gt; header:folded-content-type",
           "Standard '>'-prefixed nested quoting (the one style naive strippers handle), "
           "combined with a Content-Type header folded across two lines.")


# ---------------------------------------------------------------------------
# 3. Outlook "-----Original Message-----" block, no blank line before it,
#    plus stacked Fwd/RE subject prefixes.
# ---------------------------------------------------------------------------
def f03():
    name = "03_outlook_original_message_fwd_stack.eml"
    body = (
        "Please see amendment below and confirm you're OK to proceed.\r\n"
        "-----Original Message-----\r\n"
        "From: Legal Team <legal@example.com>\r\n"
        "Sent: Thursday, February 8, 2024 3:14 PM\r\n"
        "To: Bob Jones\r\n"
        "Subject: FW: RE: Fwd: Indemnification clause\r\n"
        "\r\n"
        "Forwarding for visibility. See thread below.\r\n"
        "-----Original Message-----\r\n"
        "From: Carol Smith\r\n"
        "Sent: Wednesday, February 7, 2024 11:02 AM\r\n"
        "To: Legal Team\r\n"
        "Subject: RE: Fwd: Indemnification clause\r\n"
        "\r\n"
        "Client pushed back on section 4.2, see attached redline.\r\n"
    )
    headers = std_headers(
        "f03", "Re: FW: RE: Fwd: Indemnification clause",
        frm="bob@example.com", to="legal@example.com",
        extra="Content-Type: text/plain; charset=utf-8\r\n",
    )
    raw = (headers + "\r\n" + body).encode()
    write_raw(name, raw)
    write_expected(name, "Please see amendment below and confirm you're OK to proceed.")
    record(name, "eml", "quoting:outlook-original-message (no leading blank line); chain:fwd-subject-stacking",
           "Outlook-style '-----Original Message-----' quoting with no '>' characters, doubled "
           "(forward-of-a-forward), and no blank line separating new text from the marker on the "
           "outermost hop. Subject line stacks FW:/RE:/Fwd: from repeated forwarding.")


# ---------------------------------------------------------------------------
# 4. Gmail-style HTML blockquote, text/plain part is a placeholder only.
# ---------------------------------------------------------------------------
def f04():
    name = "04_gmail_html_blockquote_no_plain.eml"
    html = (
        "<div>Works for me, let's schedule the call for Thursday.</div>"
        "<div><br></div>"
        '<div class="gmail_quote">On Mon, Feb 12, 2024 at 8:00 AM Carol Smith '
        "&lt;carol@example.com&gt; wrote:<br>"
        '<blockquote class="gmail_quote" style="margin:0 0 0 .8ex;border-left:1px solid #ccc;padding-left:1ex">'
        "<div>Can we schedule a call to discuss the redline?</div>"
        "</blockquote></div>"
    )
    plain_placeholder = "This message is best viewed in an HTML-capable email client."
    msg = EmailMessage()
    msg["From"] = "bob@example.com"
    msg["To"] = "carol@example.com"
    msg["Subject"] = "Re: Redline call"
    msg["Date"] = "Mon, 12 Feb 2024 11:00:00 -0500"
    msg["Message-ID"] = "<f04@example.com>"
    msg.set_content(plain_placeholder)
    msg.add_alternative(html, subtype="html")
    write_raw(name, msg.as_bytes())
    write_expected(name, "Works for me, let's schedule the call for Thursday.")
    record(name, "eml", "quoting:gmail-html-blockquote; html-only-content",
           "multipart/alternative where the text/plain part is a content-free placeholder and the "
           "real new content + quote boundary only exist in the text/html part's <blockquote>.")


# ---------------------------------------------------------------------------
# 5. Deep chain (8 hops), mixed quote characters from different clients.
# ---------------------------------------------------------------------------
def f05():
    name = "05_deep_chain_mixed_quote_chars.eml"
    body = (
        "Final version approved, sending to the client today.\r\n"
        "\r\n"
        "> One more typo on page 2, otherwise good.\r\n"
        ">> Fixed the typo, see v4 attached.\r\n"
        "> | Should we also update the appendix reference?\r\n"
        "| Yes, appendix B needs the new numbering.\r\n"
        ">> > Numbering looks off in section 3.\r\n"
        "> >> Draft 3 attached for review.\r\n"
        ">>> Draft 2 comments incorporated.\r\n"
        "| >> Please see draft 2 for the updated schedule.\r\n"
    )
    headers = std_headers("f05", "Re: Re: Fwd: Re: Contract v4",
                           frm="alice@example.com", to="bob@example.com",
                           extra="Content-Type: text/plain; charset=utf-8\r\n")
    raw = (headers + "\r\n" + body).encode()
    write_raw(name, raw)
    write_expected(name, "Final version approved, sending to the client today.")
    record(name, "eml", "chain-depth:deep(8-hop); quoting:mixed-chars(>,>>,|)",
           "Eight quoting hops using three different quote-character conventions ('>', '>>', '|') "
           "as the thread round-tripped through different mail clients. A stripper tuned to one "
           "quote character stops matching partway through.")


# ---------------------------------------------------------------------------
# 6. Interleaved reply using colour, not textual quote markers (HTML).
# ---------------------------------------------------------------------------
def f06():
    name = "06_interleaved_reply_color_coded.eml"
    html = (
        "<p>See my responses inline below, marked in blue.</p>"
        "<p>Can we move the deposition to next Friday?</p>"
        '<p style="color:blue">Yes, Friday works for our side.</p>'
        "<p>Also, will the expert report be ready by then?</p>"
        '<p style="color:blue">The expert report will be ready Wednesday.</p>'
    )
    msg = EmailMessage()
    msg["From"] = "opposing.counsel@example.com"
    msg["To"] = "alice@example.com"
    msg["Subject"] = "Re: Deposition scheduling"
    msg["Date"] = "Mon, 12 Feb 2024 12:00:00 -0500"
    msg["Message-ID"] = "<f06@example.com>"
    msg.set_content(html, subtype="html")  # HTML-only, no text/plain part at all
    write_raw(name, msg.as_bytes())
    write_expected(
        name,
        "See my responses inline below, marked in blue.\n"
        "Yes, Friday works for our side.\n"
        "The expert report will be ready Wednesday.",
    )
    record(name, "eml", "quoting:interleaved-reply(no textual quote marker); html-only-content",
           "HTML-only message (no text/plain part), reply interleaved paragraph-by-paragraph with "
           "the (unquoted) original, distinguished only by colour rather than '>' or a blockquote. "
           "There is no textual quote marker at all, so line-prefix-based stripping cannot separate "
           "old from new content even after HTML-to-text conversion; the 'latest message' is "
           "scattered across multiple non-contiguous paragraphs with no structural signal to find them.")


# ---------------------------------------------------------------------------
# 7. Fork/merge chain: two reply branches pasted into one message,
#    out of chronological order.
# ---------------------------------------------------------------------------
def f07():
    name = "07_fork_merge_chain.eml"
    body = (
        "Consolidating both threads below before the call at 3pm.\r\n"
        "\r\n"
        "> Branch A (from Carol, replying to the 9am draft):\r\n"
        "> Fine by me, just fix the date in section 1.\r\n"
        ">\r\n"
        "> Branch B (from David, replying to the same 9am draft):\r\n"
        "> I'd rather we keep the original date and note the exception in section 1.\r\n"
        ">\r\n"
        "> Original 9am draft:\r\n"
        "> Proposing to shift the effective date to March 1.\r\n"
    )
    headers = std_headers("f07", "Re: Effective date (consolidated)",
                           frm="alice@example.com", to="carol@example.com, david@example.com",
                           extra="Content-Type: text/plain; charset=utf-8\r\n")
    raw = (headers + "\r\n" + body).encode()
    write_raw(name, raw)
    write_expected(name, "Consolidating both threads below before the call at 3pm.")
    record(name, "eml", "chain-structure:fork-merge(non-linear)",
           "Two independent reply branches to the same original message are pasted into one email, "
           "out of chronological order. Tests whether 'latest = top of file' still holds when the "
           "chain isn't linear (it does here only because the consolidator put the new text first; "
           "the quoted section itself is not chronologically ordered).")


# ---------------------------------------------------------------------------
# 8. HTML table with merged cells (colspan/rowspan).
# ---------------------------------------------------------------------------
def f08():
    name = "08_html_table_merged_cells.eml"
    html = (
        "<p>Updated fee schedule below, please confirm.</p>"
        "<table border=1 cellspacing=0 cellpadding=4>"
        "<tr><th colspan=2>Phase</th><th>Fee</th></tr>"
        "<tr><td rowspan=2>Discovery</td><td>Document review</td><td>$12,000</td></tr>"
        "<tr><td>Depositions</td><td>$18,500</td></tr>"
        "<tr><td colspan=2>Trial prep (flat fee)</td><td>$25,000</td></tr>"
        "</table>"
    )
    msg = EmailMessage()
    msg["From"] = "billing@example.com"
    msg["To"] = "client@example.com"
    msg["Subject"] = "Updated fee schedule"
    msg["Date"] = "Mon, 12 Feb 2024 13:00:00 -0500"
    msg["Message-ID"] = "<f08@example.com>"
    msg.set_content(html, subtype="html")  # HTML-only, forces the tag-strip fallback
    write_raw(name, msg.as_bytes())
    write_expected(name, "Updated fee schedule below, please confirm.\nPhase / Fee\nDiscovery - Document review $12,000\nDiscovery - Depositions $18,500\nTrial prep (flat fee) $25,000")
    record(name, "eml", "table:html-merged-cells(colspan/rowspan); html-only-content",
           "HTML-only table using colspan/rowspan, no text/plain alternative. A regex tag-stripper "
           "collapses this into a run-on string with no column boundaries because merged cells break "
           "the 'one column per closed <td>' assumption.")


# ---------------------------------------------------------------------------
# 9. Nested table (table inside a table cell) - pasted Excel + signature.
# ---------------------------------------------------------------------------
def f09():
    name = "09_nested_table_excel_paste.eml"
    html = (
        "<p>Damages calculation pasted from Excel below.</p>"
        "<table border=1><tr><td>"
        "<table border=1 cellpadding=3>"
        "<tr><td>Category</td><td>Amount</td></tr>"
        "<tr><td>Lost wages</td><td>$42,000</td></tr>"
        "<tr><td>Medical</td><td>$15,750</td></tr>"
        "</table>"
        "</td></tr>"
        "<tr><td>"
        "<hr>"
        "<table><tr><td><b>Jane Roe</b><br>Associate<br>Example LLP</td></tr></table>"
        "</td></tr>"
        "</table>"
    )
    msg = EmailMessage()
    msg["From"] = "jroe@example.com"
    msg["To"] = "opposing.counsel@example.com"
    msg["Subject"] = "Damages calculation"
    msg["Date"] = "Mon, 12 Feb 2024 14:00:00 -0500"
    msg["Message-ID"] = "<f09@example.com>"
    msg.set_content(html, subtype="html")  # HTML-only, forces the tag-strip fallback
    write_raw(name, msg.as_bytes())
    write_expected(name, "Damages calculation pasted from Excel below.\nCategory / Amount\nLost wages $42,000\nMedical $15,750\n--\nJane Roe, Associate, Example LLP")
    record(name, "eml", "table:nested(table-in-table); signature-block-table; html-only-content",
           "HTML-only. A data table nested inside an outer layout table cell, with a second nested "
           "table used for the signature block. A tag-stripping (non-tree-aware) HTML-to-text "
           "approach cannot tell which row boundaries belong to which table and concatenates across them.")


# ---------------------------------------------------------------------------
# 10. Plain-text ASCII table, space-aligned under a proportional font.
# ---------------------------------------------------------------------------
def f10():
    name = "10_ascii_table_proportional_spacing.eml"
    body = (
        "See comparison below (aligned in my email client, may not be aligned here):\r\n"
        "\r\n"
        "Item                 Draft 1      Draft 2\r\n"
        "Indemnification cap  $1,000,000   $2,500,000\r\n"
        "Term                 3 years      5 years\r\n"
        "Termination notice   30 days      60 days\r\n"
    )
    headers = std_headers("f10", "Contract comparison", frm="carol@example.com", to="alice@example.com",
                           extra="Content-Type: text/plain; charset=utf-8\r\n")
    raw = (headers + "\r\n" + body).encode()
    write_raw(name, raw)
    write_expected(
        name,
        "See comparison below (aligned in my email client, may not be aligned here):\n\n"
        "Item                 Draft 1      Draft 2\n"
        "Indemnification cap  $1,000,000   $2,500,000\n"
        "Term                 3 years      5 years\n"
        "Termination notice   30 days      60 days",
    )
    record(name, "eml", "table:ascii-space-aligned(proportional-font)",
           "Table built with spaces under the assumption of a monospace font. Looks aligned in the "
           "composing client; a 'split on runs of 2+ spaces' column extractor mis-detects boundaries "
           "because column widths were tuned for a proportional font, not character count.")


# ---------------------------------------------------------------------------
# 11. Inline colour-coded redline ("see amended in red below") inside quote.
# ---------------------------------------------------------------------------
def f11():
    name = "11_redline_inline_color.eml"
    html = (
        "<p>See amended term in red below, please confirm you accept the change.</p>"
        "<p>-----Original Message-----<br>"
        "From: Carol Smith<br>Sent: Feb 8, 2024<br>To: Alice<br>Subject: RE: Term sheet</p>"
        "<p>Section 4.2 shall read: the term of this agreement shall be "
        '<span style="color:red">five (5) years</span> '
        "from the Effective Date.</p>"
        "<p>(previously: three (3) years)</p>"
    )
    msg = EmailMessage()
    msg["From"] = "alice@example.com"
    msg["To"] = "carol@example.com"
    msg["Subject"] = "RE: Term sheet"
    msg["Date"] = "Mon, 12 Feb 2024 15:00:00 -0500"
    msg["Message-ID"] = "<f11@example.com>"
    msg.set_content(html, subtype="html")  # HTML-only, forces the tag-strip fallback
    write_raw(name, msg.as_bytes())
    write_expected(
        name,
        "See amended term in red below, please confirm you accept the change.\n"
        "Section 4.2 shall read: the term of this agreement shall be five (5) years from the Effective Date.",
    )
    record(name, "eml", "redline:inline-color-in-quoted-block; html-only-content",
           "HTML-only. The one substantive change (five years, was three) is expressed as coloured "
           "text nested inside what otherwise reads as quoted history following a "
           "'-----Original Message-----' marker. A parser that discards everything after that marker "
           "throws away the only new content in the message.")


# ---------------------------------------------------------------------------
# 12. Strikethrough + insertion redline pairs (manual, not Word track-changes).
# ---------------------------------------------------------------------------
def f12():
    name = "12_strikethrough_redline.eml"
    html = (
        "<p>Proposed edits below:</p>"
        "<p>Landlord shall provide <s>thirty (30)</s> <b>sixty (60)</b> days written notice "
        "prior to <s>termination</s> <b>non-renewal</b> of this lease.</p>"
    )
    msg = EmailMessage()
    msg["From"] = "landlord.counsel@example.com"
    msg["To"] = "tenant.counsel@example.com"
    msg["Subject"] = "Lease notice period redline"
    msg["Date"] = "Mon, 12 Feb 2024 16:00:00 -0500"
    msg["Message-ID"] = "<f12@example.com>"
    msg.set_content(html, subtype="html")  # HTML-only, forces the tag-strip fallback
    write_raw(name, msg.as_bytes())
    write_expected(
        name,
        "Proposed edits below:\n"
        "Landlord shall provide sixty (60) days written notice prior to non-renewal of this lease.",
    )
    record(name, "eml", "redline:manual-strikethrough-insertion(not-word-trackchanges); html-only-content",
           "HTML-only. Manual redlining using <s>/<b> tags rather than Word's real track-changes XML. "
           "A naive tag-stripper keeps both the struck-through old text and the new text side by "
           "side, producing a contradictory/duplicated sentence instead of the actual final language.")


# ---------------------------------------------------------------------------
# 13. Quoted-printable body with soft line breaks splitting words/entities.
# ---------------------------------------------------------------------------
def f13():
    name = "13_quoted_printable_soft_break.eml"
    # Deliberately construct quoted-printable with '=' soft breaks landing
    # mid-word and mid-entity, the way real mail clients wrap long lines.
    body_text = (
        "The parties acknowledge that the confidentiality obligations set forth herein "
        "shall survive termination of this agreement, and that a breach thereof would "
        "cause irreparable harm entitling the non‑breaching party to injunctive relief "
        "in addition to any other remedies available at law or in equity."
    )
    qp_body = quopri.encodestring(body_text.encode("utf-8")).decode("ascii")
    headers = std_headers("f13", "Confidentiality clause", frm="alice@example.com", to="bob@example.com",
                           extra="Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: quoted-printable\r\n")
    raw = (headers + "\r\n" + qp_body.replace("\n", "\r\n")).encode("ascii")
    write_raw(name, raw)
    write_expected(name, body_text)
    record(name, "eml", "encoding:quoted-printable-soft-linebreak",
           "Body is quoted-printable encoded with soft line breaks ('=\\r\\n') that split multi-byte "
           "UTF-8 characters and long words across lines. A parser that reads the body as raw text "
           "without decoding Content-Transfer-Encoding first gets literal '=E2=80=91' sequences and "
           "words broken at arbitrary column positions.")


# ---------------------------------------------------------------------------
# 14. Base64-encoded plain text body.
# ---------------------------------------------------------------------------
def f14():
    name = "14_base64_body.eml"
    body_text = "Confirming receipt of the executed signature pages. We will file with the court tomorrow morning.\r\n"
    b64 = base64.encodebytes(body_text.encode("utf-8")).decode("ascii")
    headers = std_headers("f14", "Signature pages received", frm="paralegal@example.com", to="alice@example.com",
                           extra="Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n")
    raw = (headers + "\r\n" + b64).encode("ascii")
    write_raw(name, raw)
    write_expected(name, body_text.replace("\r\n", "\n").strip())
    record(name, "eml", "encoding:base64-body",
           "Entire text/plain body is base64-encoded. Confirms the parser honors "
           "Content-Transfer-Encoding rather than assuming 7-bit/8-bit text; reading raw produces "
           "unreadable base64 noise instead of the message.")


# ---------------------------------------------------------------------------
# 15. Declared us-ascii but actually windows-1252 (smart quotes, em-dash).
# ---------------------------------------------------------------------------
def f15():
    name = "15_wrong_charset_windows1252.eml"
    body_text = "Client’s counsel confirmed — no objection to the extension – please proceed.\r\n"
    body_bytes = body_text.encode("windows-1252")
    headers = std_headers("f15", "Extension confirmed", frm="alice@example.com", to="bob@example.com",
                           extra="Content-Type: text/plain; charset=us-ascii\r\n")
    raw = headers.encode("ascii") + b"\r\n" + body_bytes
    write_raw(name, raw)
    write_expected(name, "Client’s counsel confirmed — no objection to the extension – please proceed.")
    record(name, "eml", "encoding:mislabeled-charset(declared us-ascii, actual windows-1252)",
           "Header declares us-ascii but the body bytes are windows-1252 (curly quotes, em/en dash). "
           "A parser that trusts the declared charset over sniffing raises UnicodeDecodeError or "
           "silently mojibakes the punctuation.")


# ---------------------------------------------------------------------------
# 16. Legacy Shift_JIS body forwarded into an otherwise-English thread.
# ---------------------------------------------------------------------------
def f16():
    name = "16_legacy_shiftjis_forward.eml"
    jp_text = "契約書の習正を確認しました。問題ありません。"  # "Confirmed the contract amendments. No issues."
    en_text = "Forwarding the note from our Tokyo office below (Shift_JIS encoded in the original).\r\n\r\n---------- Forwarded message ----------\r\n"
    body_bytes = en_text.encode("ascii") + jp_text.encode("shift_jis")
    headers = std_headers("f16", "Fwd: Tokyo office confirmation", frm="alice@example.com", to="bob@example.com",
                           extra="Content-Type: text/plain; charset=shift_jis\r\n")
    raw = headers.encode("ascii") + b"\r\n" + body_bytes
    write_raw(name, raw)
    write_expected(name, "Forwarding the note from our Tokyo office below (Shift_JIS encoded in the original).\n\n---------- Forwarded message ----------\n" + jp_text)
    record(name, "eml", "encoding:legacy-multibyte(shift_jis)",
           "Body declared and encoded as Shift_JIS, forwarded into an otherwise English-language "
           "thread. Confirms the parser isn't hardcoded to UTF-8/Latin-1 charset assumptions common "
           "in quick regex-based decoders.")


# ---------------------------------------------------------------------------
# 17. RFC 2047 encoded-word subject, split across two encoded words.
# ---------------------------------------------------------------------------
def f17():
    name = "17_rfc2047_encoded_subject.eml"
    subject_text = "Résumé of amendments — confidential ⚠ do not forward"
    # Split into two encoded-words joined by CRLF+space (legal per RFC 2047,
    # a naive raw-header reader that doesn't decode encoded-words at all
    # just sees literal '=?UTF-8?B?...?=' text).
    part1 = subject_text[:14].encode("utf-8")
    part2 = subject_text[14:].encode("utf-8")
    enc1 = base64.b64encode(part1).decode("ascii")
    enc2 = base64.b64encode(part2).decode("ascii")
    subject_header = f"=?UTF-8?B?{enc1}?=\r\n =?UTF-8?B?{enc2}?="
    body = "Please treat the attached amendments as confidential until execution.\r\n"
    headers = (
        "From: alice@example.com\r\n"
        "To: bob@example.com\r\n"
        f"Subject: {subject_header}\r\n"
        "Date: Mon, 12 Feb 2024 17:00:00 -0500\r\n"
        "Message-ID: <f17@example.com>\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
    )
    raw = (headers + "\r\n" + body).encode("utf-8")
    write_raw(name, raw)
    write_expected(name, "Please treat the attached amendments as confidential until execution.")
    record(name, "eml", "encoding:rfc2047-encoded-subject(split-across-two-words)",
           "Subject header uses RFC 2047 encoded-words, split into two adjacent encoded-words joined "
           "by folding whitespace. A header reader that treats headers as raw strings without "
           "running email.header.decode_header gets literal '=?UTF-8?B?...?=' noise in the subject.")


# ---------------------------------------------------------------------------
# 18. UTF-8 BOM at the start of the text/plain part.
# ---------------------------------------------------------------------------
def f18():
    name = "18_utf8_bom.eml"
    body_text = "Motion filed. Hearing set for March 3rd.\r\n"
    body_bytes = b"\xef\xbb\xbf" + body_text.encode("utf-8")
    headers = std_headers("f18", "Motion filed", frm="paralegal@example.com", to="alice@example.com",
                           extra="Content-Type: text/plain; charset=utf-8\r\n")
    raw = headers.encode("ascii") + b"\r\n" + body_bytes
    write_raw(name, raw)
    write_expected(name, "Motion filed. Hearing set for March 3rd.")
    record(name, "eml", "encoding:utf8-bom-prefix",
           "text/plain body is prefixed with a UTF-8 byte-order mark. A naive str.decode('utf-8') "
           "succeeds but leaves a stray U+FEFF character glued to the first word, breaking any "
           "exact-match / startswith comparison downstream.")


# ---------------------------------------------------------------------------
# 19. Multiple real attachment types: PDF, DOCX (with track changes), XLSX.
# ---------------------------------------------------------------------------
def f19():
    name = "19_multi_attachment_types.eml"
    from reportlab.pdfgen import canvas
    import docx
    import openpyxl
    import io

    tmp = ROOT / "scripts" / "_tmp"
    tmp.mkdir(exist_ok=True)

    pdf_path = tmp / "exhibit_a.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(100, 750, "Exhibit A - Executed Signature Page")
    c.save()

    docx_path = tmp / "redline.docx"
    d = docx.Document()
    d.add_paragraph("Section 4.2 term redline (see tracked changes).")
    d.save(str(docx_path))
    _inject_trackchanges(docx_path)

    xlsx_path = tmp / "fee_schedule.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Phase", "Fee"])
    ws.append(["Discovery", 12000])
    ws.append(["Trial", 25000])
    wb.save(str(xlsx_path))

    plain = "Please see the three attachments: executed signature page (PDF), redlined term sheet (DOCX, tracked changes), and fee schedule (XLSX).\r\n"
    msg = EmailMessage()
    msg["From"] = "paralegal@example.com"
    msg["To"] = "alice@example.com"
    msg["Subject"] = "Attachments: signature page, redline, fee schedule"
    msg["Date"] = "Mon, 12 Feb 2024 18:00:00 -0500"
    msg["Message-ID"] = "<f19@example.com>"
    msg.set_content(plain)
    msg.add_attachment(pdf_path.read_bytes(), maintype="application", subtype="pdf", filename="exhibit_a.pdf")
    msg.add_attachment(docx_path.read_bytes(), maintype="application",
                        subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
                        filename="redline.docx")
    msg.add_attachment(xlsx_path.read_bytes(), maintype="application",
                        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        filename="fee_schedule.xlsx")
    write_raw(name, msg.as_bytes())
    write_expected(name, plain.strip())
    record(name, "eml", "attachments:pdf,docx(real-track-changes),xlsx",
           "Three real Office/PDF attachments, including a DOCX with genuine Word track-changes XML "
           "(w:ins/w:del) — the actual redline text only exists inside the attachment, not the body. "
           "Tests whether a parser (a) recognizes OOXML content-type strings rather than skipping "
           "unknown MIME types, and (b) doesn't crash walking a MIME tree with several binary leaves.")


def _inject_trackchanges(docx_path):
    """Post-process a python-docx file to add a real w:ins/w:del pair."""
    import shutil
    tmp_extract = docx_path.parent / (docx_path.stem + "_x")
    if tmp_extract.exists():
        shutil.rmtree(tmp_extract)
    with zipfile.ZipFile(docx_path) as z:
        z.extractall(tmp_extract)
    doc_xml_path = tmp_extract / "word" / "document.xml"
    xml = doc_xml_path.read_text(encoding="utf-8")
    ins_del = (
        '<w:ins w:id="1" w:author="Carol Smith" w:date="2024-02-08T00:00:00Z">'
        '<w:r><w:t xml:space="preserve"> The term shall be five (5) years.</w:t></w:r></w:ins>'
        '<w:del w:id="2" w:author="Carol Smith" w:date="2024-02-08T00:00:00Z">'
        '<w:r><w:delText xml:space="preserve"> The term shall be three (3) years.</w:delText></w:r></w:del>'
    )
    xml = xml.replace("</w:body>", ins_del + "</w:body>")
    doc_xml_path.write_text(xml, encoding="utf-8")
    docx_path.unlink()
    with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in tmp_extract.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(tmp_extract))
    shutil.rmtree(tmp_extract)


# ---------------------------------------------------------------------------
# 20. Inline cid: image, multipart/related.
# ---------------------------------------------------------------------------
def f20():
    name = "20_inline_cid_image.eml"
    html = (
        "<p>Signature comparison below:</p>"
        '<img src="cid:sig1" width="200"><br>'
        '<img src="cid:sig2" width="200">'
        "<p>The second signature does not match the exemplar on file.</p>"
    )
    plain = "Signature comparison below (images not shown in plain text). The second signature does not match the exemplar on file.\r\n"
    msg = EmailMessage()
    msg["From"] = "forensics@example.com"
    msg["To"] = "alice@example.com"
    msg["Subject"] = "Signature comparison"
    msg["Date"] = "Mon, 12 Feb 2024 19:00:00 -0500"
    msg["Message-ID"] = "<f20@example.com>"
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")
    # Attach a tiny 1x1 PNG twice, as related inline images (not regular attachments).
    png_1x1 = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    html_part = msg.get_payload()[1]
    html_part.add_related(png_1x1, maintype="image", subtype="png", cid="<sig1>")
    html_part.add_related(png_1x1, maintype="image", subtype="png", cid="<sig2>")
    write_raw(name, msg.as_bytes())
    write_expected(name, "Signature comparison below (images not shown in plain text). The second signature does not match the exemplar on file.")
    record(name, "eml", "attachments:inline-cid-image(multipart/related)",
           "Two inline images referenced via cid: inside multipart/related, nested inside "
           "multipart/alternative. Tests whether the parser distinguishes multipart/related inline "
           "parts (rendering aids, not real attachments) from multipart/mixed real attachments — "
           "conflating the two produces a wrong attachment count and can mistake render-only assets "
           "for evidence.")


# ---------------------------------------------------------------------------
# 21. Nested message/rfc822 attachment: the real content is one level down.
# ---------------------------------------------------------------------------
def f21():
    name = "21_nested_rfc822_attachment.eml"
    inner = EmailMessage()
    inner["From"] = "carol@example.com"
    inner["To"] = "alice@example.com"
    inner["Subject"] = "RE: Settlement number"
    inner["Date"] = "Fri, 9 Feb 2024 10:00:00 -0500"
    inner["Message-ID"] = "<f21-inner@example.com>"
    inner.set_content("Client will accept $85,000 to settle, final number.\r\n")

    outer = EmailMessage()
    outer["From"] = "alice@example.com"
    outer["To"] = "billing@example.com"
    outer["Subject"] = "FYI - see attached email re: settlement"
    outer["Date"] = "Mon, 12 Feb 2024 20:00:00 -0500"
    outer["Message-ID"] = "<f21@example.com>"
    outer.set_content("FYI, forwarding as an attachment (not inline) for the file. See attached.\r\n")
    outer.add_attachment(inner.as_bytes(), maintype="message", subtype="rfc822", filename="original.eml")
    write_raw(name, outer.as_bytes())
    write_expected(name, "Client will accept $85,000 to settle, final number.")
    record(name, "eml", "attachments:nested-message-rfc822",
           "The substantive content (the actual settlement number) is inside a message/rfc822 "
           "attachment — a full email attached as a file rather than pasted inline — while the "
           "top-level body is just a one-line FYI. A parser that only reads the top-level body "
           "(or that walks multipart/* parts but stops at the first non-multipart leaf without "
           "recursing into an attached message) reports the FYI text and completely misses the "
           "real number. Ground truth here is the number, not the FYI line.")


# ---------------------------------------------------------------------------
# 22. Zip attachment containing another .eml.
# ---------------------------------------------------------------------------
def f22():
    name = "22_zip_with_eml.eml"
    inner = EmailMessage()
    inner["From"] = "david@example.com"
    inner["To"] = "alice@example.com"
    inner["Subject"] = "Archived correspondence"
    inner["Date"] = "Fri, 9 Feb 2024 09:00:00 -0500"
    inner["Message-ID"] = "<f22-inner@example.com>"
    inner.set_content("Per our call, the deadline is extended to March 15.\r\n")

    tmp = ROOT / "scripts" / "_tmp"
    tmp.mkdir(exist_ok=True)
    zip_path = tmp / "archive.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("archived_email.eml", inner.as_bytes())

    outer = EmailMessage()
    outer["From"] = "alice@example.com"
    outer["To"] = "paralegal@example.com"
    outer["Subject"] = "Please file - zipped correspondence"
    outer["Date"] = "Mon, 12 Feb 2024 21:00:00 -0500"
    outer["Message-ID"] = "<f22@example.com>"
    outer.set_content("Please file the attached zipped correspondence in the case file.\r\n")
    outer.add_attachment(zip_path.read_bytes(), maintype="application", subtype="zip", filename="archive.zip")
    write_raw(name, outer.as_bytes())
    write_expected(name, "Please file the attached zipped correspondence in the case file.")
    record(name, "eml", "attachments:zip-containing-eml",
           "A .zip attachment contains a further .eml file. Tests whether the pipeline attempts to "
           "open compressed containers at all — most naive parsers list 'archive.zip' as an "
           "attachment filename and never look inside it. Ground truth is the top-level body only "
           "(the harness's single extraction task does not require zip traversal); the manifest "
           "flags this file separately as an 'attachment traversal' case for pipelines that claim "
           "to do full-text indexing of archives.")


# ---------------------------------------------------------------------------
# 23. Corrupted / truncated PDF attachment.
# ---------------------------------------------------------------------------
def f23():
    name = "23_corrupted_attachment.eml"
    truncated_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog"  # deliberately truncated, no %%EOF
    msg = EmailMessage()
    msg["From"] = "paralegal@example.com"
    msg["To"] = "alice@example.com"
    msg["Subject"] = "Scan attached (may be corrupted, resending)"
    msg["Date"] = "Mon, 12 Feb 2024 22:00:00 -0500"
    msg["Message-ID"] = "<f23@example.com>"
    msg.set_content("Scan attached, let me know if it opens on your end.\r\n")
    msg.add_attachment(truncated_pdf, maintype="application", subtype="pdf", filename="scan.pdf")
    msg.add_attachment(b"", maintype="application", subtype="pdf", filename="scan_empty.pdf")
    write_raw(name, msg.as_bytes())
    write_expected(name, "Scan attached, let me know if it opens on your end.")
    record(name, "eml", "attachments:corrupted-truncated-pdf; attachments:zero-byte",
           "One attachment is a truncated PDF (valid header, no %%EOF, unreadable by a real PDF "
           "parser) and one is a zero-byte file with a PDF filename. Tests whether one bad attachment "
           "crashes extraction of the whole message rather than degrading gracefully.")


def main():
    for fn in [f01, f02, f03, f04, f05, f06, f07, f08, f09, f10, f11, f12, f13, f14, f15, f16,
               f17, f18, f19, f20, f21, f22, f23]:
        fn()
    print(f"Generated {len(MANIFEST)} .eml fixtures.")
    return MANIFEST


if __name__ == "__main__":
    manifest = main()
    # Written/merged with .msg entries by build_manifest.py afterwards.
    import json
    (ROOT / "scripts" / "_eml_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (EXPECTED / "_subjects.json").write_text(json.dumps(SUBJECTS, indent=2, ensure_ascii=False), encoding="utf-8")
