# Messiness feature checklist

Concrete features a "realistic and messy" native email test corpus must
include, and — for each — the specific mechanism by which it breaks a naive
parser. "Naive parser" here means the kind of code most pipelines start
with: read the file, grab the first `text/plain` part (or strip HTML tags
if there isn't one), maybe regex-strip lines starting with `>`, done.

Every feature below is instantiated by at least one file in `corpus/` — see
`MANIFEST.csv` for the mapping.

## 1. Chain depth and structure

| Feature | Why it breaks naive parsers |
|---|---|
| Shallow chain (1 message, no history) | Baseline / control — a parser should trivially succeed here. If it doesn't, the bug is upstream of chain-handling entirely. |
| Medium chain (3-4 replies, single thread) | Exercises basic quote-stripping. A parser that only checks for `>`-prefixed lines already fails once it meets Outlook-style unmarked quote blocks (see §2). |
| Deep chain (8+ hops, forward-of-a-forward-of-a-reply) | Nested quoting compounds: each hop re-indents or re-wraps the previous quote, so indentation depth stops correlating with recency. A naive "take everything before the first quote marker" parser accumulates false positives (treats an inner quote's fresh-looking header line as new content) or false negatives (bails at the first ambiguous marker and returns almost nothing). |
| Fork/merge chain (two people reply to the same message, later reconciled into one thread) | Chains aren't always linear. A parser that assumes "latest = bottom of file" breaks when two independent reply branches are pasted into one message out of chronological order. |
| Forward with edited subject (`Fwd:` / `FW:` / `Re: Fwd:` stacking) | Subject-based thread reconstruction (common in e-discovery dedup) collapses distinct messages together or fails to link them, depending on locale and mail client subject-prefix conventions. |

## 2. Quoting styles

| Feature | Why it breaks naive parsers |
|---|---|
| Classic `>`-prefixed plain-text quoting (Unix/mutt style) | The one style naive regex-based stripping actually handles — included as a **positive control**. |
| Outlook "`-----Original Message-----`" block with header lines (`From:`/`Sent:`/`To:`/`Subject:`) and **no** `>` prefix | The dominant real-world enterprise pattern. A `>`-only stripper does nothing here; the entire quoted history is misclassified as new content. |
| Gmail/Apple Mail "On [date], [name] wrote:" HTML `<blockquote>` with no plain-text equivalent | Only exists in the HTML part. A parser that only reads `text/plain` (common because it's easier) never sees the quote boundary at all, or — worse — falls back to `text/plain` and gets a client-generated placeholder ("This is an HTML-only message") instead of real content. |
| Top-posting vs. bottom-posting vs. interleaved reply | "Latest content is at the top" is a convention, not a rule. Interleaved replies (respond inline, paragraph by paragraph, inside the quoted body) defeat any position-based heuristic — new and old content alternate line by line. |
| Mixed quote characters in one thread (`>`, `>>`, `| `, `» `) from different mail clients round-tripping the same thread | A regex tuned to one quote character silently stops matching partway down the file once a different client's quoting style takes over. |
| Localized "On [date], [name] wrote:" header in a non-English language (e.g. Russian "...написал:") | *Not in the original checklist — found via the real-world spot check (see README), not designed in.* Quote-marker detection in real libraries (`email_reply_parser` included) is typically English-locale-specific regex. A thread from a non-English-locale mail client leaves the localized header line in the output even when the `>`-prefixed quote body underneath it is stripped correctly. Left in the corpus's covered-features list as a known gap rather than added as a corpus fixture, since fabricating a "genuine" foreign-locale client artifact synthetically would undercut the point that this was found in real captured mail, not designed in. |

## 3. Table / HTML mixing

| Feature | Why it breaks naive parsers |
|---|---|
| HTML table with merged cells (`colspan`/`rowspan`) | Naive tag-stripping (`re.sub('<[^>]+>', '', html)`) collapses a 3x4 table into a run-on string with no column boundaries — merged cells make even "one space per closed tag" heuristics misalign columns. |
| Nested table (a table inside a table cell — common in pasted Excel ranges or Outlook signature blocks) | Tag-stripping regex that isn't a real HTML parser can't distinguish the inner table's row boundaries from the outer one; rows get concatenated across table boundaries. |
| Plain-text ASCII table built with spaces (not tabs) under a proportional font in the source client | Looks aligned in the composing client's font but is not actually column-aligned in the raw text. Any "split on multiple spaces" table extractor mis-detects column boundaries because the space-run lengths vary per row. |
| `text/plain` alternative that is a lossy auto-generated flattening of an HTML table (Outlook's plain-text fallback) | The "safe" fallback a naive parser prefers is exactly the version where table structure has already been destroyed by the client, not by the parser. |

## 4. Inline "tracked-change-style" edits

| Feature | Why it breaks naive parsers |
|---|---|
| Inline colored text ("see amended in red below", `<span style="color:red">`) marking a change inside otherwise-unchanged quoted text | Semantically this is the *only* new content in the message, but it's nested inside what looks like quoted history. A quote-stripping parser that discards anything after the first `-----Original Message-----` marker throws away the one sentence that mattered. |
| Strikethrough + insertion pairs (`<s>old term</s> <b>new term</b>`) simulating manual redlining without Word's real track-changes XML | Visually a redline, but structurally just inline formatting tags. A parser extracting plain text either keeps both old and new text (produces contradictory/duplicated content) or strips tags and produces "old term new term" as if both apply. |
| Real Word track-changes preserved through a `.docx` attachment (not in the email body) | Tests whether the harness/pipeline even opens attachments rather than only reading the message body — a large class of "the answer was in the attachment" pipeline failures. |

## 5. Encoding edge cases

| Feature | Why it breaks naive parsers |
|---|---|
| `quoted-printable` body with soft line breaks (`=\r\n`) splitting a word or an entity mid-token | A parser that decodes the body as raw text without first undoing `Content-Transfer-Encoding: quoted-printable` gets literal `=E2=80=99` sequences and broken words at every wrapped line. |
| `base64`-encoded body | Same failure mode, more total: read raw and the entire body is unreadable noise. Confirms the parser is honoring `Content-Transfer-Encoding` at all rather than assuming 8-bit/7-bit. |
| Declared charset that's wrong or missing (e.g. header says `us-ascii`, body actually `windows-1252` with smart quotes/em-dashes) | A parser that trusts the declared charset over sniffing/fallback produces `UnicodeDecodeError` or silently mojibakes curly quotes into `â€™`. |
| Legacy `ISO-2022-JP` / `Shift_JIS` body mixed into an otherwise English thread (e.g. a forwarded note from an overseas office) | Confirms the parser isn't hardcoded to UTF-8/Latin-1 and can handle multi-byte legacy encodings still common in real enterprise mail archives. |
| RFC 2047 encoded-word headers (`=?UTF-8?B?...?=`) in `Subject`/`From`, including a header split across two encoded words | A parser that reads headers as raw strings without decoding gets literal `=?UTF-8?B?4pi6?=` in the subject line instead of the actual text — breaks any downstream keyword search or subject-based threading. |
| BOM at the start of a UTF-8 `text/plain` part | Naive `str.decode('utf-8')` succeeds but leaves a stray `﻿` character prepended to the "first word" of the message — breaks any exact-match or "starts with" comparison the pipeline does. |

## 6. Attachment types

| Feature | Why it breaks naive parsers |
|---|---|
| PDF attachment | Confirms the pipeline distinguishes "attachment metadata" (filename, size) from "attachment content" — many naive parsers only list filenames and never actually extract attachment text. |
| DOCX / XLSX (zip-based Office formats) | These are themselves multi-file zip archives — a parser using a MIME-type allowlist that doesn't recognize the OOXML content-type string skips them silently. |
| Inline image referenced by `cid:` in the HTML body (not a real attachment target, part of `multipart/related`) | Tests whether the parser understands `multipart/related` vs. `multipart/mixed` — treating a `cid:` inline image as a regular downloadable attachment (or vice versa) is a common structural bug. |
| Nested `message/rfc822` attachment (a full forwarded email attached as a file, not pasted inline) | The "message" the pipeline is looking for may be one level deeper than the top-level MIME tree — a parser that only walks `multipart/*` parts and stops at the first non-multipart leaf never recurses into the attached message. |
| Zip attachment containing another `.eml` | Same failure at one further remove; also tests whether the pipeline attempts to open compressed containers at all. |
| Zero-byte / corrupted attachment (truncated PDF) | Tests failure handling — does the parser crash the whole message extraction because one of several attachments is bad, or does it degrade gracefully? |

## 7. Native-format-specific traps (`.msg` vs `.eml`)

| Feature | Why it breaks naive parsers |
|---|---|
| `.msg` file whose body is stored **only** as compressed RTF (`RTF-in-sync` with no plain-text or HTML body saved) | This happens whenever the message was composed in Outlook with certain format settings. Libraries that expose only `msg.body` (plain-text accessor) return `None` or an empty string — the readable content only exists inside the RTF stream and requires RTF decompression/parsing, which most "native .msg parsers" people reach for (`extract-msg`'s basic API) do not do by default. |
| `.msg` file produced by genuinely running it through Outlook (OLE/Compound File Binary Format), vs. an `.eml` renamed to `.msg` | `.msg` is a binary OLE2 structured-storage format, not text. A parser that tries to `open(...).read().decode()` a `.msg` the way it would an `.eml` gets binary garbage / a decode exception immediately. This is the single most common "it works on my test file" trap when a team only ever tested against `.eml`. |
| `.eml` with `Content-Type` header folded across multiple lines with non-standard whitespace | RFC 5322 allows header folding, but hand-rolled regex header parsers (as opposed to a real MIME parser) often assume one header = one line and silently truncate the `Content-Type`/boundary value. |

## Why this list, not a bigger one

The brief asks for a small corpus that's "immediately usable as an eval," not
maximum coverage. Each row above is deliberately a *distinct failure
mechanism* (wrong assumption about encoding, wrong assumption about MIME
structure, wrong assumption about quote-marker convention, wrong assumption
about file format) rather than a cosmetic variant of one already listed. The
manifest maps every corpus file to the specific row(s) it exercises, so
coverage is auditable rather than asserted.
