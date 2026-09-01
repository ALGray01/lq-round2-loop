# "Realistic and messy" feature checklist

Concrete features a native `.eml`/`.msg` test corpus for legal document
pipelines needs, and *why* each one breaks naive parsers (regex-over-body,
`email.message_from_bytes` + take-first-text-part, or a bare HTML-to-text
strip). Each feature has an ID (`Fxx`) used in `corpus/manifest.json` to tag
which files exercise it.

## A. Chain / threading structure

- **F1 — Deep chains (4-6 hops, mixed Reply/Fwd).** Naive "grab the body"
  extraction returns the entire history as one undifferentiated blob. Any
  downstream task that wants "the latest message" or "what did the last
  person actually say" needs a real boundary detector, not just `body`.
- **F2 — Mixed quoting styles in one chain.** Outlook's
  `-----Original Message-----` block, Gmail's `On <date>, <name> wrote:` +
  `>` prefixing, and Apple Mail's `On <date>, at <time>, <name> wrote:` all
  signal "here begins quoted history" differently. A parser tuned to one
  regex signature misses the others, so chain-boundary detection silently
  degrades depending on which mail client produced each hop.
- **F3 — Interleaved / bottom-posted replies.** Real replies often answer
  point-by-point *inside* the quoted original, so new content appears
  scattered between blocks of `>`-quoted text. The common heuristic
  "everything after the first quote marker is history" throws away real,
  new content that happens to sit below a `>` line.
- **F4 — Inconsistent quote-depth markers.** Repeated forward/reply cycles
  through different clients corrupt the `>` nesting (`>>>`, `> >`, missing
  levels after re-wrapping). Regexes assuming a clean, uniform `> ` prefix
  per depth either under- or over-strip.
- **F5 — Forward as a real nested MIME message vs. pasted-in-body text.**
  A true forward attaches the original as a `message/rfc822` part; a manual
  forward pastes the old text into the new body. Parsers that only read the
  top-level body miss the former; parsers that blindly recurse into every
  attachment double-count the latter as "new" content.

## B. Body / content-type structure

- **F6 — `multipart/alternative` where plain and HTML disagree.** Real
  mail clients sometimes ship a stale/stub plain-text part ("This message
  requires an HTML-capable client") alongside a materially different HTML
  part. A pipeline that always takes `text/plain` silently gets the wrong
  — or no — content.
- **F7 — `multipart/related` inline images mixed with real attachments.**
  Inline images referenced by `cid:` inside the HTML are logically part of
  the *display*, not standalone attachments. Flat attachment-listing code
  either miscounts them as attachments or, in the other direction, misses
  a real attachment sitting alongside them.
- **F8 — Messy HTML tables (nested tables, colspan/rowspan, div-grid
  fake tables).** Legal correspondence routinely encodes structured data
  (payment schedules, redline comparison tables) as HTML tables — or as
  `<div>` grids with no `<table>` tag at all. Naive HTML-to-text conversion
  (`.get_text()`/tag-stripping) collapses rows and columns into a run of
  text with the column alignment gone, and the failure is *silent*: no
  exception, just wrong data.
- **F9 — Inline "tracked-change"-style edits.** "See amended text in red
  below" rendered as `<span style="color:red">`/`<strike>` in HTML, or as
  bracketed conventions (`[deleted: ...]`, `[inserted: ...]`) in plain
  text. Stripping all markup (which naive extractors do to get "clean
  text") destroys the very signal that distinguishes an edit request from
  ordinary text — the pipeline can no longer tell that an amendment was
  proposed at all.
- **F10 — Plain-text-only redlines.** Same problem as F9 but with no HTML
  to fall back on: the only signal is the bracket convention itself, so a
  parser that doesn't know the convention has literally no way to recover
  it.

## C. Encoding / transport edge cases

- **F11 — Mixed/non-UTF-8 encodings across header vs. body.** RFC 2047
  encoded-word subjects in `iso-8859-1`/`windows-1252` next to a UTF-8
  body (with accented legal terms, e.g. French/German contract language).
  Code that does one blanket `.decode('utf-8')` over everything either
  throws or mangles characters.
- **F12 — Mixed `Content-Transfer-Encoding` across parts of one message**
  (base64 / quoted-printable / 7bit/8bit in different parts of the same
  multipart tree), including a quoted-printable soft line break that
  splits a multi-byte UTF-8 sequence across two lines. Code hardcoded to
  one decode path corrupts or crashes on the others; the QP soft-break
  case corrupts a character even in *correct* per-part decoding if the
  line-unwrap step isn't done before UTF-8 decoding.
- **F13 — Missing/incorrect charset declaration.** Header claims
  `us-ascii` but the body has raw high-byte bytes (mojibake smart quotes
  from a Word paste). Strict decoders raise `UnicodeDecodeError`; lenient
  ones produce silently wrong text — either way the declared charset
  cannot be trusted.
- **F14 — Non-ASCII/encoded display names + long folded header lines.**
  RFC 2047-encoded names in `From/To/Cc`, plus a large Cc list that wraps
  across many header continuation lines. Naive header splitting on raw
  newlines (rather than proper unfolding) breaks mid-name.
- **F15 — Invisible characters (BOM, zero-width spaces, smart quotes)**
  from a Word copy-paste. These don't render as anything visually wrong,
  but break exact-string matching, deduplication, and downstream regexes
  that assume plain ASCII punctuation.

## D. Attachments

- **F16 — Nested `.eml`-in-`.eml`.** A forwarded raw message that itself
  contains a further forward and its own attachment. Tests whether
  extraction is recursive or only looks one level deep.
- **F17 — RFC 2231 encoded attachment filenames**
  (`filename*=UTF-8''%C3%84nderung.pdf`). Parsers that grab a literal
  `filename=` value get either garbled bytes or nothing at all for
  non-ASCII filenames — common in international legal correspondence.
- **F18 — Mislabeled attachment content-type**, e.g. a `.docx` served as
  `application/octet-stream`, or a file named `contract.pdf` that is
  actually an executable. Requires content sniffing, not header trust —
  and is a real security-relevant case (extension spoofing) as well as a
  parsing one.
- **F19 — Corrupted/zero-byte/truncated attachment**, simulating a bad
  export. Should not crash the whole extraction run — one bad attachment
  must not take down the rest of the pipeline's output.
- **F20 — Attachment that is itself an email chain** (re-entrancy: the
  extraction task must be able to recurse into a `.eml` attachment and
  apply the same logic again).

## E. `.msg`-specific (native Outlook binary format)

- **F21 — OLE/Compound File Binary structure**, not MIME/RFC 822 text at
  all. A parser built only for text-based email (regex over raw bytes, or
  feeding bytes straight to `email.message_from_bytes`) doesn't error
  cleanly — it just produces garbage, because there is no header block to
  find. This is the single biggest reason "just use the Enron corpus" (all
  `.eml`/plain text) doesn't cover real-world Outlook export pipelines.
- **F22 — RTF (often compressed) message body**, the historic Outlook
  default instead of HTML/plain. Requires RTF decompression and
  de-escaping — a code path most "read the body" tooling simply doesn't
  have, so it silently returns nothing or raw RTF control words.

## Corpus-design note

Real messy mail rarely exercises one feature in isolation — a forwarded
chain with broken quote depth *and* a mislabeled attachment *and* mixed
encoding is normal, not exceptional. The corpus therefore combines 2-4
features per file rather than isolating one feature per file 1:1; see
`corpus/manifest.json` for the exact tag set per file.
