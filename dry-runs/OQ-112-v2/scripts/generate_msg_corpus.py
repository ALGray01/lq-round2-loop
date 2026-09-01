"""
Generates the .msg half of the corpus by driving real Outlook via COM
automation (win32com) and saving genuine OLE2 Compound-File-Binary .msg
files - not .eml files renamed to .msg. Requires Outlook installed locally;
this is a native Windows/Outlook-only script, documented as such in the
README.

Run: python scripts/generate_msg_corpus.py
"""
import json
from pathlib import Path

import win32com.client

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
EXPECTED = ROOT / "expected"
CORPUS.mkdir(exist_ok=True)
EXPECTED.mkdir(exist_ok=True)

olMailItem = 0
olFormatHTML = 2
olFormatPlain = 1
olFormatRichText = 3
olSaveAsMsg = 3  # olMSG

MANIFEST = []


def record(filename, fmt, features, description):
    MANIFEST.append({
        "filename": filename, "format": fmt, "features": features, "description": description,
        "expected_note": "",
    })


def new_mail(app):
    return app.CreateItem(olMailItem)


SUBJECTS = {}


def save_msg(mail, name):
    SUBJECTS[name] = mail.Subject
    path = CORPUS / name
    if path.exists():
        path.unlink()
    mail.SaveAs(str(path), olSaveAsMsg)
    mail.Close(1)  # olDiscard, don't leave it sitting in Drafts


def write_expected(name, text):
    (EXPECTED / (Path(name).stem + ".txt")).write_text(text, encoding="utf-8")


def main():
    app = win32com.client.Dispatch("Outlook.Application")

    # 24. Native .msg, Outlook-style "-----Original Message-----" chain,
    #     actually round-tripped through Outlook rather than hand-built.
    name = "24_outlook_native_original_message.msg"
    mail = new_mail(app)
    mail.Subject = "RE: Escrow instructions"
    mail.To = "bob@example.com"
    mail.BodyFormat = olFormatPlain
    mail.Body = (
        "Confirmed, releasing escrow funds today.\r\n"
        "-----Original Message-----\r\n"
        "From: Bob Jones\r\n"
        "Sent: Thursday, February 8, 2024 2:00 PM\r\n"
        "To: Alice\r\n"
        "Subject: Escrow instructions\r\n"
        "\r\n"
        "Please confirm release of escrow funds once signed docs are received.\r\n"
    )
    save_msg(mail, name)
    write_expected(name, "Confirmed, releasing escrow funds today.")
    record(name, "msg", "native-format:msg(OLE2,real-outlook); quoting:outlook-original-message",
           "Genuine binary OLE2 .msg produced by real Outlook (not an .eml renamed to .msg). "
           "A parser that tries to open this the way it opens .eml (raw text read + decode) gets "
           "binary structured-storage bytes, not RFC 5322 text - the single most common "
           "'worked on my test file' trap when a team only ever tested against .eml.")

    # 25. Native .msg with an HTML table (merged cells), sent as HTML format.
    name = "25_outlook_native_html_table.msg"
    mail = new_mail(app)
    mail.Subject = "Native msg: settlement ledger"
    mail.To = "alice@example.com"
    mail.BodyFormat = olFormatHTML
    mail.HTMLBody = (
        "<html><body><p>Ledger below, native Outlook .msg with an HTML table.</p>"
        "<table border=1><tr><th colspan=2>Category</th><th>Amount</th></tr>"
        "<tr><td rowspan=2>Costs</td><td>Filing fees</td><td>$450</td></tr>"
        "<tr><td>Service fees</td><td>$120</td></tr></table></body></html>"
    )
    save_msg(mail, name)
    write_expected(name, "Ledger below, native Outlook .msg with an HTML table.")
    record(name, "msg", "native-format:msg; table:html-merged-cells",
           "Native .msg saved with BodyFormat=HTML containing a merged-cell table, exercising the "
           "table-mixing failure mode inside the binary .msg format rather than .eml, since some "
           "pipelines have separate (and separately-buggy) code paths for each.")

    # 26. Native .msg with an inline red-colored redline edit.
    name = "26_outlook_native_redline_color.msg"
    mail = new_mail(app)
    mail.Subject = "RE: Native msg redline"
    mail.To = "carol@example.com"
    mail.BodyFormat = olFormatHTML
    mail.HTMLBody = (
        "<html><body><p>See amended term in red below.</p>"
        "<p>-----Original Message-----<br>From: Carol<br>Subject: Term sheet</p>"
        '<p>The term shall be <span style="color:red">five (5) years</span> from the Effective Date.</p>'
        "</body></html>"
    )
    save_msg(mail, name)
    write_expected(name, "See amended term in red below.\nThe term shall be five (5) years from the Effective Date.")
    record(name, "msg", "native-format:msg; redline:inline-color-in-quoted-block",
           "Native .msg equivalent of the inline-color redline test: the substantive edit is nested "
           "inside what reads as quoted history, this time inside a real binary .msg file.")

    # 27. Native .msg with a real PDF attachment.
    name = "27_outlook_native_pdf_attachment.msg"
    mail = new_mail(app)
    mail.Subject = "Native msg: exhibit attached"
    mail.To = "alice@example.com"
    mail.BodyFormat = olFormatPlain
    mail.Body = "Please see the attached exhibit (native .msg attachment).\r\n"
    pdf_path = ROOT / "scripts" / "_tmp" / "exhibit_a.pdf"
    mail.Attachments.Add(str(pdf_path))
    save_msg(mail, name)
    write_expected(name, "Please see the attached exhibit (native .msg attachment).")
    record(name, "msg", "native-format:msg; attachments:pdf",
           "Native .msg with a real PDF attachment stored as an OLE sub-storage, not a base64 MIME "
           "part like .eml. Tests whether the attachment-handling code path is genuinely "
           "format-agnostic or was only ever written/tested against .eml's base64 attachments.")

    # 28. Native .msg saved as plain-text-only format (RTF-in-sync edge case
    #     attempt): compose in RichText format but only set the plain Body,
    #     leaving HTMLBody empty, to approximate the "body only exists as
    #     RTF" trap without needing raw RTF stream manipulation via Redemption.
    name = "28_outlook_native_richtext_only.msg"
    mail = new_mail(app)
    mail.Subject = "Native msg: rich text format body"
    mail.To = "bob@example.com"
    mail.BodyFormat = olFormatRichText
    mail.Body = "This message was composed in Rich Text Format. Approve to proceed with filing.\r\n"
    save_msg(mail, name)
    write_expected(name, "This message was composed in Rich Text Format. Approve to proceed with filing.")
    record(name, "msg", "native-format:msg; body-format:richtext(olFormatRichText)",
           "Composed with BodyFormat=olFormatRichText (Outlook's native RTF format, distinct from "
           "HTML or plain). extract_msg's plain-text .body accessor depends on Outlook having kept "
           "a synced plain-text copy; when a message is authored purely in RTF, some real-world .msg "
           "files carry the readable content ONLY in the compressed RTF stream (compressed under "
           "MS-OXRTFCP), which a library that only reads the plain-text or HTML property returns "
           "empty/None for. See README 'Known limitation' - this fixture approximates the scenario "
           "via Outlook's own RTF authoring path rather than hand-crafting a compressed-RTF-only "
           "stream, and the harness records whatever extract_msg actually returns for it as a real, "
           "not simulated, result.")

    print(f"Generated {len(MANIFEST)} .msg fixtures.")
    (ROOT / "scripts" / "_msg_manifest.json").write_text(json.dumps(MANIFEST, indent=2), encoding="utf-8")

    subjects_path = EXPECTED / "_subjects.json"
    existing = json.loads(subjects_path.read_text(encoding="utf-8")) if subjects_path.exists() else {}
    existing.update(SUBJECTS)
    subjects_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
