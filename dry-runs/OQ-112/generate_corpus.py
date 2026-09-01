#!/usr/bin/env python3
"""
Generates the synthetic messy .eml corpus for OQ-112 into corpus/eml/, and
writes corpus/manifest.json describing which CHECKLIST.md feature IDs each
file exercises plus the ground-truth "latest message" text used by
harness.py to grade extraction.

All senders/companies/domains are fictional (``*.example`` domains, per
RFC 2606) — nothing here is real correspondence. See README.md's "Corpus:
what it is and where it came from" section for the corpus-wide licensing
note (this file *is* the documented generation method the question asks
for).

Two construction paths are used deliberately:
  - `email.message.EmailMessage` / `email.mime.*` for messages whose
    messiness is structural (multipart layout, attachments, nesting) —
    using the real stdlib MIME writer keeps boundaries/encodings valid,
    same as a real MUA would produce.
  - Raw byte-template construction (`raw()`/`write_raw`) for messages whose
    messiness is a header/encoding lie (wrong charset, broken quote-depth
    text, folded headers) — using the stdlib writer here would "fix" the
    very brokenness we're trying to test, so we build exact bytes by hand.

Output is deterministic (fixed Date header, fixed MIME boundaries) so
re-running this script reproduces the corpus byte-for-byte - an earlier
version used `email.utils.formatdate()` (wall-clock time) and stdlib's
randomly-generated MIME boundaries, which an audit caught making that
claim false; both are now pinned.

Run: `python generate_corpus.py`
"""
import json
import os
import quopri
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart as _MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.message import MIMEMessage
from email.utils import formatdate as _formatdate

OUT_DIR = os.path.join(os.path.dirname(__file__), "corpus", "eml")
os.makedirs(OUT_DIR, exist_ok=True)

_FIXED_DATE = _formatdate(1785200000)  # fixed timestamp for reproducible output


def formatdate(*_a, **_kw):
    return _FIXED_DATE


_boundary_counter = [0]


class MIMEMultipart(_MIMEMultipart):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _boundary_counter[0] += 1
        self.set_boundary(f"===corpus-boundary-{_boundary_counter[0]:04d}===")

MANIFEST = []

DISCLAIMER = (
    "This message and any attachments are confidential and intended solely "
    "for the addressee. If you are not the intended recipient, please "
    "notify the sender and delete this message. Meridian & Cole LLP accepts "
    "no liability for the contents of this email where modified without "
    "the sender's consent."
)


def register(fid, filename, features, scenario, expected_latest, notes=""):
    MANIFEST.append({
        "id": fid,
        "file": filename,
        "features": features,
        "scenario": scenario,
        "expected_latest_message": expected_latest,
        "notes": notes,
    })


def save(msg, filename):
    path = os.path.join(OUT_DIR, filename)
    with open(path, "wb") as f:
        f.write(bytes(msg))
    return path


def save_raw(text, filename, encoding="utf-8"):
    path = os.path.join(OUT_DIR, filename)
    data = text.replace("\n", "\r\n").encode(encoding)
    with open(path, "wb") as f:
        f.write(data)
    return path


# ---------------------------------------------------------------------------
# 01 - deep 5-hop chain mixing Outlook / Gmail quoting, top+interleaved posts
# ---------------------------------------------------------------------------
def gen_01():
    latest = (
        "Sarah,\n\n"
        "Confirmed - Blackstone Ridge accepts the revised indemnification cap "
        "at $2.5M. Please send the updated Schedule C for signature by EOD "
        "Friday.\n\nMike"
    )
    body = latest + "\n\n" + (
        "On Tue, 14 Jul 2026 at 09:12, Sarah Chen <sarah.chen@meridiancole-law.example> wrote:\n"
        "> Mike,\n"
        "> Following up on the call - can you confirm Blackstone Ridge is OK\n"
        "> with the $2.5M cap? We need to close this out before the holiday.\n"
        ">\n"
        "> -----Original Message-----\n"
        "> From: David Osei <d.osei@harrowgate-partners.example>\n"
        "> Sent: Monday, July 13, 2026 4:47 PM\n"
        "> To: Sarah Chen\n"
        "> Subject: RE: RE: Fwd: Blackstone Ridge - Indemnification cap\n"
        ">\n"
        "> Sarah - our client won't move off $2.5M, that's the number from the\n"
        "> term sheet. See thread below for the history.\n"
        ">\n"
        "> > On Fri, 10 Jul 2026, Priya Patel <priya.patel@blackstoneridge.example> wrote:\n"
        "> > All - reattaching the executed term sheet for reference. The cap\n"
        "> > we discussed in the June 28 call was $2.5M, not $3M as drafted in\n"
        "> > v2 of the agreement. Please correct.\n"
        "> >\n"
        "> > ---------- Forwarded message ---------\n"
        "> > From: Linda Vance <l.vance@meridiancole-law.example>\n"
        "> > Date: Thu, 25 Jun 2026 at 11:03\n"
        "> > Subject: Blackstone Ridge - draft term sheet v1\n"
        "> >\n"
        "> > Attached is the first draft term sheet for review ahead of Monday's\n"
        "> > call. Indemnification section is still a placeholder pending\n"
        "> > partner sign-off.\n"
    )
    msg = EmailMessage()
    msg["From"] = "Mike Torres <mike.torres@meridiancole-law.example>"
    msg["To"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    msg["Subject"] = "RE: RE: Fwd: Blackstone Ridge - Indemnification cap"
    msg["Date"] = formatdate()
    msg.set_content(body + "\n\n" + DISCLAIMER)
    fn = "01_deep_chain_5hop_mixed_quoting.eml"
    save(msg, fn)
    register("01", fn, ["F1", "F2", "F3"],
              "5-hop reply/fwd chain mixing Outlook '-----Original Message-----' "
              "and Gmail 'On ... wrote:' quoting styles, plus a nested nested-quote "
              "forward at the bottom.",
              latest)


# ---------------------------------------------------------------------------
# 02 - broken/inconsistent quote-depth markers
# ---------------------------------------------------------------------------
def gen_02():
    latest = (
        "All,\n\nAgreed, let's proceed on that basis. I'll circulate the final "
        "redline tonight.\n\nBest,\nDavid"
    )
    body = latest + "\n\n" + (
        ">On 12 Jul 2026, Priya Patel wrote:\n"
        ">> On 11 Jul 2026, Sarah Chen wrote:\n"
        ">>>On 10 Jul 2026, Mike Torres wrote:\n"
        "> > Let's just use the number from the term sheet, no need to\n"
        ">reopen it.\n"
        ">> Agreed with Mike here.\n"
        ">Fine by me too, moving to final.\n"
    )
    msg = EmailMessage()
    msg["From"] = "David Osei <d.osei@harrowgate-partners.example>"
    msg["To"] = "Priya Patel <priya.patel@blackstoneridge.example>"
    msg["Subject"] = "Re: Indemnification cap - final"
    msg["Date"] = formatdate()
    msg.set_content(body)
    fn = "02_broken_quote_depth.eml"
    save(msg, fn)
    register("02", fn, ["F4"],
              "Quote-depth markers corrupted by repeated forwarding through "
              "different clients: inconsistent '>' counts, missing spaces, "
              "no blank line separating levels.",
              latest)


# ---------------------------------------------------------------------------
# 03 - forward as real nested message/rfc822 attachment
# ---------------------------------------------------------------------------
def gen_03():
    latest = (
        "Priya - forwarding the original engagement letter you asked for, see "
        "attached. Let me know if you need anything else pulled from the file."
    )
    outer = MIMEMultipart("mixed")
    outer["From"] = "Linda Vance <l.vance@meridiancole-law.example>"
    outer["To"] = "Priya Patel <priya.patel@blackstoneridge.example>"
    outer["Subject"] = "Fwd: Engagement letter - Blackstone Ridge"
    outer["Date"] = formatdate()
    outer.attach(MIMEText(latest + "\n\n" + DISCLAIMER))

    inner = EmailMessage()
    inner["From"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    inner["To"] = "Linda Vance <l.vance@meridiancole-law.example>"
    inner["Subject"] = "Engagement letter - Blackstone Ridge"
    inner["Date"] = "Mon, 02 Mar 2026 10:15:00 +0000"
    inner.set_content(
        "Linda, please keep this on file - executed engagement letter for "
        "the Blackstone Ridge matter, effective March 2026."
    )
    outer.attach(MIMEMessage(inner))
    fn = "03_forwarded_as_rfc822_attachment.eml"
    save(outer, fn)
    register("03", fn, ["F5", "F16"],
              "True forward: original message attached as a real message/rfc822 "
              "MIME part (not pasted into the body text).",
              latest)


# ---------------------------------------------------------------------------
# 04 - multipart/alternative where plain stub disagrees with real HTML
# ---------------------------------------------------------------------------
def gen_04():
    latest_html_text = (
        "Team,\n\nPlease see the payment schedule below for Q3. Note row 3 has "
        "been revised upward per the July 14 call.\n\n"
        "Milestone 1: $150,000 (paid)\n"
        "Milestone 2: $225,000 (due Aug 15)\n"
        "Milestone 3: $310,000 (due Sep 30) -- revised from $275,000\n\n"
        "Regards,\nMike"
    )
    plain_stub = "This message requires an HTML-capable email client to view correctly."
    html = """<html><body>
<p>Team,</p>
<p>Please see the payment schedule below for Q3. Note row 3 has been revised
upward per the July 14 call.</p>
<table border="1" cellpadding="4">
<tr><th>Milestone</th><th>Amount</th><th>Status</th></tr>
<tr><td>Milestone 1</td><td>$150,000</td><td>paid</td></tr>
<tr><td>Milestone 2</td><td>$225,000</td><td>due Aug 15</td></tr>
<tr><td>Milestone 3</td><td>$310,000</td><td>due Sep 30 (revised from $275,000)</td></tr>
</table>
<p>Regards,<br>Mike</p>
</body></html>"""
    msg = MIMEMultipart("alternative")
    msg["From"] = "Mike Torres <mike.torres@meridiancole-law.example>"
    msg["To"] = "Blackstone Ridge Deal Team <team@blackstoneridge.example>"
    msg["Subject"] = "Q3 payment schedule"
    msg["Date"] = formatdate()
    msg.attach(MIMEText(plain_stub, "plain"))
    msg.attach(MIMEText(html, "html"))
    fn = "04_alt_html_plain_mismatch.eml"
    save(msg, fn)
    register("04", fn, ["F6", "F8"],
              "multipart/alternative: plain part is a stale 'view in HTML' stub, "
              "real content (incl. a pricing table) is only in the HTML part.",
              latest_html_text,
              notes="Extraction that trusts text/plain gets only the stub sentence.")


# ---------------------------------------------------------------------------
# 05 - multipart/related inline images + real attachment + zero-byte attachment
# ---------------------------------------------------------------------------
def gen_05():
    latest = (
        "See the signature block comparison below (inline images) and the "
        "clean redline attached. The exhibit scan attachment looks corrupted "
        "on my end - can you resend?"
    )
    html = """<html><body>
<p>See the signature block comparison below (inline images) and the clean
redline attached. The exhibit scan attachment looks corrupted on my end -
can you resend?</p>
<img src="cid:sig_old"><br>
<img src="cid:sig_new">
</body></html>"""
    related = MIMEMultipart("related")
    related.attach(MIMEText(html, "html"))
    for cid, name in [("sig_old", "sig_old.png"), ("sig_new", "sig_new.png")]:
        img = MIMEApplication(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, _subtype="octet-stream")
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=name)
        related.attach(img)

    outer = MIMEMultipart("mixed")
    outer["From"] = "Priya Patel <priya.patel@blackstoneridge.example>"
    outer["To"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    outer["Subject"] = "Signature comparison + exhibit scan"
    outer["Date"] = formatdate()
    outer.attach(related)

    redline = MIMEApplication(b"PK\x03\x04" + b"redline-bytes" * 20, _subtype="octet-stream")
    redline.add_header("Content-Disposition", "attachment", filename="redline_v3.docx")
    outer.attach(redline)

    corrupt = MIMEApplication(b"", _subtype="octet-stream")
    corrupt.add_header("Content-Disposition", "attachment", filename="exhibit_scan.pdf")
    outer.attach(corrupt)

    fn = "05_related_inline_images_plus_attachment.eml"
    save(outer, fn)
    register("05", fn, ["F7", "F19"],
              "multipart/related inline cid: images inside multipart/mixed "
              "alongside a real attachment and a zero-byte 'corrupted' attachment.",
              latest)


# ---------------------------------------------------------------------------
# 06 - nested HTML table, colspan/rowspan
# ---------------------------------------------------------------------------
def gen_06():
    latest = (
        "Revised closing schedule attached below - note the escrow release "
        "milestones now span two workstreams (see merged cells)."
    )
    html = """<html><body>
<p>Revised closing schedule attached below - note the escrow release
milestones now span two workstreams (see merged cells).</p>
<table border="1">
<tr><th>Phase</th><th colspan="2">Workstream</th><th>Date</th></tr>
<tr><td rowspan="2">Phase 1</td><td>Legal</td><td>Diligence</td><td>Aug 1</td></tr>
<tr><td>Finance</td><td>Escrow setup</td><td>Aug 3</td></tr>
<tr><td colspan="3">Phase 2 - Joint Closing Review</td><td>Aug 10</td></tr>
<tr><td>Phase 3</td><td>Legal</td><td>Final signatures</td><td>Aug 15</td></tr>
</table>
</body></html>"""
    msg = MIMEMultipart("alternative")
    msg["From"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    msg["To"] = "David Osei <d.osei@harrowgate-partners.example>"
    msg["Subject"] = "Revised closing schedule"
    msg["Date"] = formatdate()
    msg.attach(MIMEText("Revised closing schedule attached below - view in HTML.", "plain"))
    msg.attach(MIMEText(html, "html"))
    fn = "06_messy_html_table_nested.eml"
    save(msg, fn)
    register("06", fn, ["F8"],
              "HTML table with colspan/rowspan merged cells (closing schedule) "
              "in the HTML alternative part.",
              latest)


# ---------------------------------------------------------------------------
# 07 - CSS div-grid pseudo-table (no <table> tag at all)
# ---------------------------------------------------------------------------
def gen_07():
    latest = (
        "Settlement allocation below (rendered as a grid, not a table) - "
        "please confirm the Class B figure before we file."
    )
    html = """<html><body>
<p>Settlement allocation below (rendered as a grid, not a table) - please
confirm the Class B figure before we file.</p>
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;border:1px solid #000;">
<div style="font-weight:bold;">Class</div><div style="font-weight:bold;">Claimants</div><div style="font-weight:bold;">Allocation</div>
<div>Class A</div><div>412</div><div>$1,230,000</div>
<div>Class B</div><div>187</div><div>$540,000</div>
<div>Class C</div><div>63</div><div>$96,500</div>
</div>
</body></html>"""
    msg = MIMEMultipart("alternative")
    msg["From"] = "David Osei <d.osei@harrowgate-partners.example>"
    msg["To"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    msg["Subject"] = "Settlement allocation - confirm before filing"
    msg["Date"] = formatdate()
    msg.attach(MIMEText("Settlement allocation below - view in HTML for the grid.", "plain"))
    msg.attach(MIMEText(html, "html"))
    fn = "07_div_grid_table.eml"
    save(msg, fn)
    register("07", fn, ["F8"],
              "Structured data laid out as a CSS div-grid with zero <table> "
              "tags - table-aware HTML parsers find nothing to extract.",
              latest)


# ---------------------------------------------------------------------------
# 08 - inline tracked-change-style red/strike edits in HTML
# ---------------------------------------------------------------------------
def gen_08():
    latest = (
        "Please see amended clause in red below - we've capped liquidated "
        "damages at 10% of contract value instead of the original 15%."
    )
    html = """<html><body>
<p>Please see amended clause in red below - we've capped liquidated damages
at 10% of contract value instead of the original 15%.</p>
<p>Clause 8.2: In the event of late delivery, Supplier shall pay liquidated
damages equal to <strike>15%</strike> <span style="color:red">10%</span>
of the total Contract Value, calculated per day of delay beyond the
Delivery Date.</p>
</body></html>"""
    msg = MIMEMultipart("alternative")
    msg["From"] = "Mike Torres <mike.torres@meridiancole-law.example>"
    msg["To"] = "David Osei <d.osei@harrowgate-partners.example>"
    msg["Subject"] = "Clause 8.2 - amended in red"
    msg["Date"] = formatdate()
    msg.attach(MIMEText(
        "Please see amended clause in red below (view in HTML for markup): "
        "liquidated damages capped at 10%, was 15%.", "plain"))
    msg.attach(MIMEText(html, "html"))
    fn = "08_tracked_change_red_text.eml"
    save(msg, fn)
    register("08", fn, ["F9"],
              "Inline redline via HTML <strike>/color:red spans ('see amended "
              "in red below') rather than real Word track-changes.",
              latest)


# ---------------------------------------------------------------------------
# 09 - plain-text-only bracket-convention redline
# ---------------------------------------------------------------------------
def gen_09():
    latest = (
        "Attached my comments inline using brackets since I'm on mobile and "
        "can't do track changes right now:\n\n"
        "Clause 4.1: Tenant shall pay a security deposit of [deleted: $10,000] "
        "[inserted: $12,500] within 5 business days of execution."
    )
    msg = EmailMessage()
    msg["From"] = "Priya Patel <priya.patel@blackstoneridge.example>"
    msg["To"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    msg["Subject"] = "Re: Lease clause 4.1 - security deposit"
    msg["Date"] = formatdate()
    msg.set_content(
        latest + "\n\n"
        "On Wed, 15 Jul 2026, Sarah Chen wrote:\n"
        "> Attached the draft lease for review, clause 4.1 has the deposit "
        "figure we discussed.\n"
    )
    fn = "09_bracket_annotation_plaintext.eml"
    save(msg, fn)
    register("09", fn, ["F9", "F10"],
              "Plain-text-only message (no HTML part) using a bracket "
              "[deleted:]/[inserted:] convention as the only redline signal.",
              latest)


# ---------------------------------------------------------------------------
# 10 - RFC2047-encoded subject (latin-1) + accented UTF-8 body
# ---------------------------------------------------------------------------
def gen_10():
    latest = (
        "Bonjour Sarah,\n\nVeuillez trouver ci-joint la clause révisée "
        "concernant la résiliation anticipée du bail commercial. Merci de "
        "confirmer votre accord avant vendredi.\n\nCordialement,\nÉlodie"
    )
    subject_raw = "Bail commercial - clause de résiliation révisée"
    subject_encoded = "=?ISO-8859-1?Q?Bail_commercial_-_clause_de_r=E9siliation_r=E9vis=E9e?="
    raw = (
        "From: =?ISO-8859-1?Q?=C9lodie_Fournier?= <e.fournier@meridiancole-law.example>\n"
        "To: Sarah Chen <sarah.chen@meridiancole-law.example>\n"
        f"Subject: {subject_encoded}\n"
        f"Date: {formatdate()}\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "Content-Transfer-Encoding: 8bit\n"
        "\n"
        f"{latest}\n"
    )
    fn = "10_mixed_encoding_subject.eml"
    save_raw(raw, fn, encoding="utf-8")
    register("10", fn, ["F11", "F14"],
              "RFC 2047 encoded-word Subject and From display-name in "
              "ISO-8859-1, body declared and encoded as UTF-8 with accented "
              "French legal text.",
              latest,
              notes=f"Raw subject text: {subject_raw!r}")


# ---------------------------------------------------------------------------
# 11 - quoted-printable soft line break splitting a multi-byte UTF-8 char
# ---------------------------------------------------------------------------
def gen_11():
    latest = "Total due: 1.250,00 € (incl. VAT) – please confirm receipt of funds."
    qp_body = quopri.encodestring(latest.encode("utf-8")).decode("ascii")
    lines = qp_body.split("\n")
    forced = []
    for ln in lines:
        if "=E2=82=AC" in ln:
            idx = ln.index("=E2=82=AC")
            head, tail = ln[: idx + 3], ln[idx + 3:]
            forced.append(head + "=")
            forced.append(tail)
        else:
            forced.append(ln)
    broken_qp = "\n".join(forced)
    raw = (
        "From: Linda Vance <l.vance@meridiancole-law.example>\n"
        "To: Priya Patel <priya.patel@blackstoneridge.example>\n"
        "Subject: Invoice total - please confirm\n"
        f"Date: {formatdate()}\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "Content-Transfer-Encoding: quoted-printable\n"
        "\n"
        f"{broken_qp}\n"
    )
    fn = "11_qp_soft_break_multibyte.eml"
    save_raw(raw, fn, encoding="ascii")
    register("11", fn, ["F11", "F12"],
              "Quoted-printable body with a soft line break forced in the "
              "middle of a multi-byte UTF-8 sequence (the euro sign), so a "
              "naive per-line QP decode step corrupts the character.",
              latest)


# ---------------------------------------------------------------------------
# 12 - mislabeled charset (declared us-ascii, actual windows-1252 high bytes)
# ---------------------------------------------------------------------------
def gen_12():
    latest = (
        "Client’s counsel confirmed “no objection” to the amended "
        "schedule – see redline attached."
    )
    body_bytes = latest.encode("windows-1252")
    raw_header = (
        "From: David Osei <d.osei@harrowgate-partners.example>\n"
        "To: Sarah Chen <sarah.chen@meridiancole-law.example>\n"
        "Subject: Client confirmed - no objection\n"
        f"Date: {formatdate()}\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=us-ascii\n"
        "Content-Transfer-Encoding: 8bit\n"
        "\n"
    ).encode("ascii")
    fn = "12_mislabeled_charset_mojibake.eml"
    path = os.path.join(OUT_DIR, fn)
    with open(path, "wb") as f:
        f.write(raw_header.replace(b"\n", b"\r\n") + body_bytes + b"\r\n")
    register("12", fn, ["F13"],
              "Header declares charset=us-ascii but the body contains raw "
              "windows-1252 high bytes (curly quotes/en-dash from a Word "
              "paste) - decoding per the declared charset raises or mangles.",
              latest)


# ---------------------------------------------------------------------------
# 13 - mixed content-transfer-encoding across parts of one message
# ---------------------------------------------------------------------------
def gen_13():
    latest = "Three copies of the same notice below in different transport encodings - use whichever your client renders. Final version: escrow release approved for $480,000."
    msg = MIMEMultipart("mixed")
    msg["From"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    msg["To"] = "Escrow Agent <agent@harrowgate-partners.example>"
    msg["Subject"] = "Escrow release notice - $480,000 approved"
    msg["Date"] = formatdate()

    alt = MIMEMultipart("alternative")
    p1 = MIMEText(latest, "plain")
    del p1["Content-Transfer-Encoding"]
    p1["Content-Transfer-Encoding"] = "base64"
    import base64
    p1.set_payload(base64.encodebytes(latest.encode("utf-8")).decode("ascii"))
    alt.attach(p1)

    p2 = MIMEText(latest, "plain", "utf-8")
    del p2["Content-Transfer-Encoding"]
    p2["Content-Transfer-Encoding"] = "quoted-printable"
    p2.set_payload(quopri.encodestring(latest.encode("utf-8")).decode("ascii"))
    alt.attach(p2)

    p3 = EmailMessage()
    p3["Content-Type"] = "text/plain; charset=utf-8"
    p3["Content-Transfer-Encoding"] = "7bit"
    p3.set_payload(latest.replace("–", "-"))
    alt.attach(p3)

    msg.attach(alt)
    fn = "13_mixed_cte_parts.eml"
    save(msg, fn)
    register("13", fn, ["F12"],
              "multipart/alternative where the three equivalent parts use "
              "base64, quoted-printable and 7bit Content-Transfer-Encoding "
              "respectively - a parser hardcoded to one decode path breaks "
              "on the others.",
              latest)


# ---------------------------------------------------------------------------
# 14 - huge Cc list folded across many header continuation lines
# ---------------------------------------------------------------------------
def gen_14():
    latest = (
        "All parties copied for the record - closing is confirmed for "
        "August 15 at 10am. Wire instructions to follow under separate cover."
    )
    names = [
        ("Sarah Chen", "sarah.chen@meridiancole-law.example"),
        ("Mike Torres", "mike.torres@meridiancole-law.example"),
        ("David Osei", "d.osei@harrowgate-partners.example"),
        ("Priya Patel", "priya.patel@blackstoneridge.example"),
        ("Linda Vance", "l.vance@meridiancole-law.example"),
        ("Élodie Fournier", "e.fournier@meridiancole-law.example"),
        ("Jamal Whitfield", "j.whitfield@harrowgate-partners.example"),
        ("Anya Sokolova", "a.sokolova@blackstoneridge.example"),
    ] * 5
    cc_entries = []
    for i, (n, e) in enumerate(names[:38]):
        if any(ord(c) > 127 for c in n):
            enc = "=?UTF-8?Q?" + n.encode("utf-8").hex() + "?="
            import quopri as _q
            enc = "=?UTF-8?Q?" + _q.encodestring(n.encode("utf-8"), quotetabs=True).decode("ascii").replace("=\n", "").replace(" ", "_") + "?="
            cc_entries.append(f"{enc} <{e}>")
        else:
            cc_entries.append(f"{n} <{e}>")
    cc_folded = (",\n\t").join(cc_entries)
    raw = (
        "From: Sarah Chen <sarah.chen@meridiancole-law.example>\n"
        "To: Priya Patel <priya.patel@blackstoneridge.example>\n"
        f"Cc: {cc_folded}\n"
        "Subject: Closing confirmed - August 15\n"
        f"Date: {formatdate()}\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "Content-Transfer-Encoding: 8bit\n"
        "\n"
        f"{latest}\n"
    )
    fn = "14_huge_cc_list_folded_headers.eml"
    save_raw(raw, fn, encoding="utf-8")
    register("14", fn, ["F14"],
              "38-recipient Cc list folded across many header continuation "
              "lines, including RFC 2047-encoded non-ASCII display names.",
              latest)


# ---------------------------------------------------------------------------
# 15 - BOM + zero-width spaces + smart quotes from Word paste
# ---------------------------------------------------------------------------
def gen_15():
    zwsp = "​"
    latest = (
        f"Per{zwsp} our call, the{zwsp} “final” version of Exhibit A "
        f"is attached—please{zwsp} sign and return by Friday."
    )
    raw = (
        "From: Mike Torres <mike.torres@meridiancole-law.example>\n"
        "To: Priya Patel <priya.patel@blackstoneridge.example>\n"
        "Subject: Exhibit A - final for signature\n"
        f"Date: {formatdate()}\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "Content-Transfer-Encoding: 8bit\n"
        "\n"
        f"{latest}\n"
    )
    fn = "15_zero_width_bom_body.eml"
    path = os.path.join(OUT_DIR, fn)
    with open(path, "wb") as f:
        f.write(b"\xef\xbb\xbf" + raw.replace("\n", "\r\n").encode("utf-8"))
    register("15", fn, ["F15"],
              "UTF-8 BOM at the start of the raw file plus zero-width spaces "
              "and curly quotes/em-dash embedded in the body text (typical of "
              "a Word copy-paste).",
              latest.replace(zwsp, ""),
              notes="expected_latest_message has zero-width spaces removed; "
                    "the raw file's body retains them for the parser to trip on. "
                    "Verified separately: stdlib email.message_from_bytes() on "
                    "this file returns m.keys() == [] and a "
                    "MissingHeaderBodySeparatorDefect - the leading BOM makes "
                    "the 'From:' line fail header-line matching, so the parser "
                    "concludes there are NO headers at all and dumps the "
                    "entire header block + body into get_payload() as one "
                    "unparsed blob. From/Subject/etc. are all lost, not just "
                    "body text.")


# ---------------------------------------------------------------------------
# 16 - RFC2231 encoded non-ASCII attachment filename
# ---------------------------------------------------------------------------
def gen_16():
    latest = "Anbei der Änderungsvertrag zur Unterschrift. Bitte bis Freitag zurücksenden."
    msg = MIMEMultipart("mixed")
    msg["From"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    msg["To"] = "David Osei <d.osei@harrowgate-partners.example>"
    msg["Subject"] = "Änderungsvertrag zur Unterschrift"
    msg["Date"] = formatdate()
    msg.attach(MIMEText(latest, "plain", "utf-8"))
    att = MIMEApplication(b"%PDF-1.4 fake pdf bytes " + b"x" * 40, _subtype="pdf")
    att["Content-Disposition"] = (
        "attachment; filename*=UTF-8''%C3%84nderungsvertrag%20%28Entwurf%29.pdf"
    )
    msg.attach(att)
    fn = "16_rfc2231_filename_attachment.eml"
    save(msg, fn)
    register("16", fn, ["F17"],
              "Attachment filename uses RFC 2231 extended parameter encoding "
              "(filename*=UTF-8''...) for a non-ASCII German filename.",
              latest)


# ---------------------------------------------------------------------------
# 17 - mislabeled attachment content-type (docx as octet-stream, exe as .pdf)
# ---------------------------------------------------------------------------
def gen_17():
    latest = "Two files attached: the signed contract and the scanned ID as requested."
    msg = MIMEMultipart("mixed")
    msg["From"] = "Priya Patel <priya.patel@blackstoneridge.example>"
    msg["To"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    msg["Subject"] = "Signed contract + ID scan"
    msg["Date"] = formatdate()
    msg.attach(MIMEText(latest, "plain"))

    docx_bytes = b"PK\x03\x04" + b"real docx content" * 10
    docx = MIMEApplication(docx_bytes, _subtype="octet-stream")
    docx.add_header("Content-Disposition", "attachment", filename="signed_contract.docx")
    msg.attach(docx)

    exe_bytes = b"MZ\x90\x00" + b"\x00" * 60 + b"executable-payload" * 5
    fake_pdf = MIMEApplication(exe_bytes, _subtype="pdf")
    fake_pdf.add_header("Content-Disposition", "attachment", filename="id_scan.pdf")
    msg.attach(fake_pdf)

    fn = "17_mislabeled_attachment_type.eml"
    save(msg, fn)
    register("17", fn, ["F18"],
              "'signed_contract.docx' is declared application/octet-stream "
              "(needs sniffing to recognize as a ZIP/OOXML file), and "
              "'id_scan.pdf' is declared application/pdf but its magic bytes "
              "(MZ) are an executable, not a PDF (%PDF) - a content-sniffing, "
              "security-relevant mismatch.",
              latest)


# ---------------------------------------------------------------------------
# 18 - nested eml-in-eml (forward containing a further forward + attachment)
# ---------------------------------------------------------------------------
def gen_18():
    latest = "Full history attached for the file - this is the complete chain including Linda's original attachment."

    innermost = EmailMessage()
    innermost["From"] = "Linda Vance <l.vance@meridiancole-law.example>"
    innermost["To"] = "Mike Torres <mike.torres@meridiancole-law.example>"
    innermost["Subject"] = "Draft NDA for review"
    innermost["Date"] = "Mon, 01 Jun 2026 09:00:00 +0000"
    innermost.set_content("Attached draft NDA, please review redline before Thursday.")
    innermost.add_attachment(b"NDA draft bytes here" * 5, maintype="application",
                              subtype="octet-stream", filename="NDA_draft_v1.docx")
    # set_content()/add_attachment() go through EmailMessage's own
    # contentmanager, bypassing the deterministic-boundary MIMEMultipart
    # subclass above - pin its boundary explicitly too, or this file (the
    # only one using this API) reintroduces non-determinism.
    _boundary_counter[0] += 1
    innermost.set_boundary(f"===corpus-boundary-{_boundary_counter[0]:04d}===")

    middle = MIMEMultipart("mixed")
    middle["From"] = "Mike Torres <mike.torres@meridiancole-law.example>"
    middle["To"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    middle["Subject"] = "Fwd: Draft NDA for review"
    middle["Date"] = "Tue, 02 Jun 2026 14:30:00 +0000"
    middle.attach(MIMEText("Forwarding Linda's draft NDA, my comments in the redline."))
    middle.attach(MIMEMessage(innermost))

    outer = MIMEMultipart("mixed")
    outer["From"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    outer["To"] = "David Osei <d.osei@harrowgate-partners.example>"
    outer["Subject"] = "Fwd: Fwd: Draft NDA for review"
    outer["Date"] = formatdate()
    outer.attach(MIMEText(latest))
    # Attach the fully-formed middle message (which itself contains innermost)
    outer.attach(MIMEMessage(_bytes_to_message(bytes(middle))))

    fn = "18_nested_eml_in_eml.eml"
    save(outer, fn)
    register("18", fn, ["F16", "F20"],
              "Two levels of nesting: outer message has an attached "
              ".eml (Mike's forward) which itself has a further attached "
              ".eml (Linda's original) carrying its own attachment.",
              latest)


def _bytes_to_message(b):
    from email import message_from_bytes
    return message_from_bytes(b)


# ---------------------------------------------------------------------------
# 19 - corrupted/truncated attachment (claims a size, isn't)
# ---------------------------------------------------------------------------
def gen_19():
    latest = "Attaching the exhibit scan - let me know if it doesn't open, our scanner has been acting up."
    msg = MIMEMultipart("mixed")
    msg["From"] = "Linda Vance <l.vance@meridiancole-law.example>"
    msg["To"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    msg["Subject"] = "Exhibit scan attached"
    msg["Date"] = formatdate()
    msg.attach(MIMEText(latest))
    att = MIMEApplication(b"%PDF-1.4\n", _subtype="pdf")
    att.add_header("Content-Disposition", "attachment", filename="exhibit_scan.pdf")
    att.add_header("X-Expected-Size", "2458112")
    msg.attach(att)
    fn = "19_corrupted_truncated_attachment.eml"
    save(msg, fn)
    register("19", fn, ["F19"],
              "Attachment truncated to a 9-byte PDF header stub (simulating "
              "a failed export) - opening/parsing it should fail gracefully "
              "without aborting extraction of the rest of the message.",
              latest)


# ---------------------------------------------------------------------------
# 20 - top-posted reply with heavy signature/disclaimer footer
# ---------------------------------------------------------------------------
def gen_20():
    latest = "Works for me, please proceed."
    body = latest + "\n\n" + (
        "On Mon, 20 Jul 2026 at 08:00, Sarah Chen <sarah.chen@meridiancole-law.example> wrote:\n"
        "> Can we proceed with filing tomorrow morning?\n"
    ) + (
        "\n\n--\nMike Torres\nAssociate | Meridian & Cole LLP\n"
        "1200 Harborview Plaza, Suite 900\nDirect: (555) 019-2231\n\n"
        + DISCLAIMER
    )
    msg = EmailMessage()
    msg["From"] = "Mike Torres <mike.torres@meridiancole-law.example>"
    msg["To"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    msg["Subject"] = "Re: Filing tomorrow"
    msg["Date"] = formatdate()
    msg.set_content(body)
    fn = "20_top_posted_simple.eml"
    save(msg, fn)
    register("20", fn, ["F1"],
              "Simple single-hop top-posted reply with a large signature "
              "block and legal disclaimer footer - the easy control case "
              "(closest to Enron-style clean plaintext) to confirm the "
              "harness passes when the file genuinely is simple.",
              latest)


# ---------------------------------------------------------------------------
# 21 - deep chain with interleaved (bottom-posted, point-by-point) replies
# ---------------------------------------------------------------------------
def gen_21():
    latest = (
        "See my responses inline below marked [MT]:\n\n"
        "> 1. Confirm the closing date of August 15.\n"
        "[MT] Confirmed.\n\n"
        "> 2. Confirm wire instructions go to the escrow account, not "
        "directly to seller.\n"
        "[MT] Confirmed - escrow account only, per Section 3.\n\n"
        "> 3. Any outstanding diligence items?\n"
        "[MT] Just the environmental report, expected Wednesday."
    )
    body = latest + "\n\n" + (
        "-----Original Message-----\n"
        "From: David Osei\n"
        "Sent: Thursday, July 16, 2026 11:00 AM\n"
        "To: Mike Torres\n"
        "Subject: Pre-closing checklist\n\n"
        "Mike, three items to confirm before we finalize:\n"
        "1. Confirm the closing date of August 15.\n"
        "2. Confirm wire instructions go to the escrow account, not "
        "directly to seller.\n"
        "3. Any outstanding diligence items?\n"
    )
    msg = EmailMessage()
    msg["From"] = "Mike Torres <mike.torres@meridiancole-law.example>"
    msg["To"] = "David Osei <d.osei@harrowgate-partners.example>"
    msg["Subject"] = "RE: Pre-closing checklist"
    msg["Date"] = formatdate()
    msg.set_content(body)
    fn = "21_interleaved_reply_deep.eml"
    save(msg, fn)
    register("21", fn, ["F3"],
              "Point-by-point interleaved reply: new [MT]-tagged content sits "
              "directly between blocks of quoted original text, defeating "
              "'everything after the first > is history' heuristics.",
              latest)


# ---------------------------------------------------------------------------
# 22 - Apple Mail style quoting, different date format
# ---------------------------------------------------------------------------
def gen_22():
    latest = "Sounds good - I'll have the paralegal pull those records this afternoon."
    body = latest + "\n\n" + (
        "On Jul 18, 2026, at 3:41 PM, Sarah Chen <sarah.chen@meridiancole-law.example> wrote:\n\n"
        "> Can someone pull the property records for the Blackstone Ridge "
        "parcel before Monday?\n"
        ">\n"
        "> On Jul 18, 2026, at 2:15 PM, David Osei <d.osei@harrowgate-partners.example> wrote:\n"
        ">>\n"
        ">> We'll need those records ahead of the title review.\n"
    )
    msg = EmailMessage()
    msg["From"] = "Mike Torres <mike.torres@meridiancole-law.example>"
    msg["To"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    msg["Subject"] = "Re: Property records"
    msg["Date"] = formatdate()
    msg.set_content(body)
    fn = "22_apple_mail_style_quote.eml"
    save(msg, fn)
    register("22", fn, ["F2"],
              "Apple Mail-style quoting ('On <date>, at <time>, X wrote:') "
              "with a distinct date format from the Outlook/Gmail styles used "
              "elsewhere in the corpus.",
              latest)


# ---------------------------------------------------------------------------
# 23 - clean plain-text single message control case
# ---------------------------------------------------------------------------
def gen_23():
    latest = (
        "Hi team,\n\nJust confirming receipt of the signed documents. We'll "
        "file with the county clerk tomorrow morning and send confirmation "
        "once recorded.\n\nThanks,\nLinda"
    )
    msg = EmailMessage()
    msg["From"] = "Linda Vance <l.vance@meridiancole-law.example>"
    msg["To"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    msg["Subject"] = "Documents received - filing tomorrow"
    msg["Date"] = formatdate()
    msg.set_content(latest)
    fn = "23_plaintext_only_clean_control.eml"
    save(msg, fn)
    register("23", fn, ["control"],
              "Clean single-message plain text, no chain, no HTML, no "
              "attachments - the Enron-style easy case, included as a "
              "control to show the harness isn't failing on everything.",
              latest)


# ---------------------------------------------------------------------------
# 24 - HTML-only message, no text/plain part at all
# ---------------------------------------------------------------------------
def gen_24():
    intro = "Please review the attached amendment before our 2pm call. Key change highlighted below."
    highlight = "Section 5(b) now requires 30 days' notice instead of 15."
    # NOTE: an earlier draft's expected_latest_message included only
    # `intro`, omitting `highlight` - the single legally material fact in
    # the message (what "Key change highlighted below" refers to). An
    # adversarial audit caught that the ground truth didn't reflect the
    # email's actual substantive content; fixed to include both sentences.
    latest = intro + "\n\n" + highlight
    html = f"""<html><body>
<p>{intro}</p>
<p style="background:#fff3b0;">{highlight}</p>
</body></html>"""
    msg2 = EmailMessage()
    msg2["From"] = "David Osei <d.osei@harrowgate-partners.example>"
    msg2["To"] = "Sarah Chen <sarah.chen@meridiancole-law.example>"
    msg2["Subject"] = "Amendment for 2pm call"
    msg2["Date"] = formatdate()
    msg2["MIME-Version"] = "1.0"
    msg2["Content-Type"] = "text/html; charset=utf-8"
    msg2.set_payload(html, charset="utf-8")
    fn = "24_html_only_no_plain_part.eml"
    save(msg2, fn)
    register("24", fn, ["F6"],
              "Single-part text/html message with no multipart/alternative "
              "and no text/plain fallback at all - code that assumes a plain "
              "part always exists gets nothing.",
              latest)


def main():
    for gen in [gen_01, gen_02, gen_03, gen_04, gen_05, gen_06, gen_07, gen_08,
                gen_09, gen_10, gen_11, gen_12, gen_13, gen_14, gen_15, gen_16,
                gen_17, gen_18, gen_19, gen_20, gen_21, gen_22, gen_23, gen_24]:
        gen()
    manifest_path = os.path.join(os.path.dirname(__file__), "corpus", "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(MANIFEST, f, indent=2, ensure_ascii=False)
    print(f"Generated {len(MANIFEST)} files -> {OUT_DIR}")
    print(f"Manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
