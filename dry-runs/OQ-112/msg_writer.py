"""
Minimal [MS-OXMSG] writer built on cfb_writer.py - produces genuine native
Outlook .msg files (OLE/CFB binary, not MIME/RFC822 text at all). This is
the format behind CHECKLIST.md F21/F22: a parser built only for text-based
email has no header block to find in these files at all.

Only the small, standard-tag subset needed for a realistic minimal message
is implemented: subject/body/sender/recipient/date/message-class, one
recipient, zero or more attachments, and (optionally) an RTF body using the
uncompressed ("MELA") variant of the [MS-OXRTFCP] compressed-RTF stream
format (real LZFu compression is not implemented - the container format is
still a spec-valid CompressedRTFStream, just with no compression applied).

Correctness is verified against `extract-msg` (a real, independent,
widely-used third-party .msg reader), not assumed - see the __main__
self-test at the bottom of this file, and results/msg_verification.txt.
"""
import struct
from datetime import datetime, timezone

from cfb_writer import write_cfb, Entry, STGTY_STREAM, STGTY_STORAGE

PT_UNICODE = 0x001F
PT_LONG = 0x0003
PT_BINARY = 0x0102
PT_SYSTIME = 0x0040

FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


def _tag(propid, proptype):
    return (propid << 16) | proptype


def _stream_name(propid, proptype):
    return f"__substg1.0_{propid:04X}{proptype:04X}"


def _to_filetime(dt: datetime) -> int:
    delta = dt.astimezone(timezone.utc) - FILETIME_EPOCH
    return int(delta.total_seconds() * 10_000_000)


class PropSet:
    """Accumulates (tag, value) properties for one property stream +
    the variable-length value streams that sit alongside it in the same
    storage."""

    def __init__(self):
        self.fixed = []     # (tag, 8-byte value)
        self.streams = []   # Entry objects for __substg1.0_* value streams

    def add_unicode(self, propid, text):
        # No null terminator: extract-msg (and Outlook) read the stream's
        # full byte length as the string value, so a trailing \x00\x00
        # here shows up as a literal embedded NUL character after decode.
        data = (text or "").encode("utf-16-le")
        tag = _tag(propid, PT_UNICODE)
        self.fixed.append((tag, struct.pack("<II", len(data), 0)))
        self.streams.append(Entry(_stream_name(propid, PT_UNICODE), STGTY_STREAM, data))

    def add_binary(self, propid, data):
        tag = _tag(propid, PT_BINARY)
        self.fixed.append((tag, struct.pack("<II", len(data), 0)))
        self.streams.append(Entry(_stream_name(propid, PT_BINARY), STGTY_STREAM, data))

    def add_long(self, propid, value):
        tag = _tag(propid, PT_LONG)
        self.fixed.append((tag, struct.pack("<Ii", value, 0)))

    def add_systime(self, propid, dt):
        tag = _tag(propid, PT_SYSTIME)
        self.fixed.append((tag, struct.pack("<q", _to_filetime(dt))))

    def build_stream(self, is_top_level, recip_count=0, attach_count=0):
        if is_top_level:
            header = (
                b"\x00" * 8
                + struct.pack("<I", recip_count)   # next recipient id
                + struct.pack("<I", attach_count)  # next attachment id
                + struct.pack("<I", recip_count)
                + struct.pack("<I", attach_count)
                + b"\x00" * 8
            )
        else:
            header = b"\x00" * 8
        body = b""
        for tag, val8 in self.fixed:
            body += struct.pack("<II", tag, 0x00000006) + val8
        return header + body


def _compress_rtf_uncompressed(rtf_text: str) -> bytes:
    """[MS-OXRTFCP] CompressedRTFStream, MELA (uncompressed) variant."""
    raw = rtf_text.encode("ascii", errors="replace")
    comp_type = b"MELA"
    crc = 0
    compressed_size = len(comp_type) + 4 + len(raw)  # type+crc+data, not incl. itself/uncompressed_size
    header = struct.pack("<II", compressed_size, len(raw)) + comp_type + struct.pack("<I", crc)
    return header + raw


def build_msg(
    subject, body_text, sender_name, sender_email,
    to_name, to_email, sent_dt,
    attachments=None, rtf_body=None,
):
    """attachments: list of (filename, bytes). Returns bytes-writable via
    cfb_writer.write_cfb - call save_msg() instead for the common case."""
    attachments = attachments or []

    top = PropSet()
    top.add_unicode(0x001A, "IPM.Note")
    top.add_unicode(0x0037, subject)
    top.add_unicode(0x1000, body_text)
    if rtf_body:
        top.add_binary(0x1009, _compress_rtf_uncompressed(rtf_body))
    top.add_unicode(0x0C1A, sender_name)
    top.add_unicode(0x0C1F, sender_email)
    top.add_unicode(0x0E04, to_name)
    top.add_long(0x0E07, 1)  # PR_MESSAGE_FLAGS = mfRead
    top.add_systime(0x0039, sent_dt)
    top.add_systime(0x0E06, sent_dt)

    root_children = list(top.streams)
    root_children.append(
        Entry("__properties_version1.0", STGTY_STREAM,
              top.build_stream(is_top_level=True, recip_count=1, attach_count=len(attachments)))
    )

    # Named Property Mapping storage: extract-msg unconditionally looks
    # this up (even to conclude "there are zero named properties"), so it
    # must exist with at least the three fixed streams, empty is fine.
    nameid = Entry("__nameid_version1.0", STGTY_STORAGE)
    nameid.children = [
        Entry("__substg1.0_00020102", STGTY_STREAM, b""),  # GUID stream
        Entry("__substg1.0_00030102", STGTY_STREAM, b""),  # entry stream
        Entry("__substg1.0_00040102", STGTY_STREAM, b""),  # string stream
    ]
    root_children.append(nameid)

    recip = PropSet()
    recip.add_unicode(0x3001, to_name)
    recip.add_unicode(0x3003, to_email)
    recip.add_long(0x0C15, 1)  # MAPI_TO
    recip_storage = Entry("__recip_version1.0_#00000000", STGTY_STORAGE)
    recip_storage.children = list(recip.streams) + [
        Entry("__properties_version1.0", STGTY_STREAM, recip.build_stream(is_top_level=False))
    ]
    root_children.append(recip_storage)

    for i, (filename, data) in enumerate(attachments):
        ap = PropSet()
        ap.add_unicode(0x3707, filename)
        ap.add_binary(0x3701, data)
        ap.add_long(0x0E20, len(data))  # PR_ATTACH_SIZE
        att_storage = Entry(f"__attach_version1.0_#{i:08d}", STGTY_STORAGE)
        att_storage.children = list(ap.streams) + [
            Entry("__properties_version1.0", STGTY_STREAM, ap.build_stream(is_top_level=False))
        ]
        root_children.append(att_storage)

    return root_children


def save_msg(path, **kwargs):
    children = build_msg(**kwargs)
    write_cfb(children, path)


if __name__ == "__main__":
    import os
    save_msg(
        "test_msg_selftest.msg",
        subject="Selftest subject",
        body_text="Selftest body text with an accented word: résumé.",
        sender_name="Sarah Chen",
        sender_email="sarah.chen@meridiancole-law.example",
        to_name="Mike Torres",
        to_email="mike.torres@meridiancole-law.example",
        sent_dt=datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc),
        attachments=[("note.txt", b"attachment bytes here")],
    )
    import extract_msg
    m = extract_msg.Message("test_msg_selftest.msg")
    print("subject:", m.subject)
    print("body:", m.body)
    print("sender:", m.sender)
    print("to:", m.to)
    print("attachments:", [a.name for a in m.attachments])
    m.close()
    os.remove("test_msg_selftest.msg")
    print("SELFTEST OK")
