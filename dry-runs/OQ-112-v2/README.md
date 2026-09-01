# Messy native .eml/.msg test corpus for legal document pipelines

Answers OQ-112. "Try the Enron dataset" falls short for testing document
pipelines because Enron is overwhelmingly clean, single-part plain text —
it doesn't exercise nested quoting, HTML/table mixing, encoding edge cases,
tracked-change-style edits, or the native `.msg` binary format at all. This
repo is a small (28-file), fully synthetic, labeled corpus that deliberately
hits those failure points, plus a harness that runs one real extraction
task against it and reports where a realistic naive parser actually breaks.

## What's here

```
FEATURE_CHECKLIST.md   Part (1): the messiness feature checklist + why each
                        feature breaks naive parsers
MANIFEST.csv            Part (2): every corpus file -> which feature(s) it
                        exercises, plus a one-line description
corpus/                 28 native .eml/.msg files (23 .eml, 5 .msg)
expected/               Hand-authored ground truth per file: the correct
                        "latest message" text and correct decoded subject
harness/
  extract_latest.py      The extraction task under test (part 3)
  run_eval.py             Runs it over corpus/, scores against expected/,
                        prints a PASS/PARTIAL/FAIL report
scripts/
  generate_eml_corpus.py  Regenerates all 23 .eml fixtures + their ground truth
  generate_msg_corpus.py  Regenerates all 5 .msg fixtures via real Outlook
                        COM automation (Windows + Outlook installed only)
  build_manifest.py       Merges both generators' per-fixture records into
                        MANIFEST.csv
```

## Run it

```
pip install -r requirements.txt
python harness/run_eval.py            # summary report
python harness/run_eval.py --verbose  # also shows expected/got for PASS rows
```

No Windows/Outlook dependency to *run* the eval — the `.msg` files are
already committed to `corpus/`, and `extract-msg` (pure Python) reads them.
Outlook is only needed to *regenerate* the `.msg` fixtures from scratch:

```
python scripts/generate_eml_corpus.py   # portable, any OS with Python
python scripts/generate_msg_corpus.py   # Windows + Outlook installed only
python scripts/build_manifest.py
```

## Part 1 — the feature checklist

See `FEATURE_CHECKLIST.md`. Seven categories, each row naming a concrete
feature and the specific parsing assumption it violates: chain depth/
structure, quoting styles, table/HTML mixing, inline redline-style edits,
encoding edge cases, attachment types, and native-format-specific traps
(`.msg` vs `.eml`). Every row is mapped to at least one corpus file.

## Part 2 — the corpus

28 files, entirely synthetic (no real correspondence, no Enron data, no
PII) — generated programmatically so there is nothing to license or
redact. `MANIFEST.csv` lists, per file: format, the feature(s) it
exercises, a description, and any note on why the expected answer is what
it is. 23 `.eml` files are built as real RFC 5322 bytes (either via
Python's `email.message.EmailMessage`, or hand-assembled where the
messiness *is* the wire format — folded headers, wrong charsets, missing
blank lines before quote markers). 5 `.msg` files are genuine binary OLE2
Compound-File-Binary documents produced by driving actual Outlook via COM
automation (`win32com`) — not `.eml` files renamed to `.msg`, which would
defeat the point of testing the native binary format.

Attachments are real files, not stubs: the DOCX in
`19_multi_attachment_types.eml` contains genuine Word track-changes XML
(`<w:ins>`/`<w:del>`), built by generating a document with `python-docx`
and then splicing real track-changes markup into `word/document.xml`
before re-zipping.

## Part 3 — the harness

**Task:** given a message (possibly with a quoted history), extract (a)
the text of the newest, non-quoted reply, and (b) the message subject.
This is chosen over "extract a clean table" because it's affected by
nearly every checklist category at once (quoting style, HTML/table mixing,
encoding, attachment structure), making it a better single stress test.

**The extractor under test** (`harness/extract_latest.py`) is a
deliberately realistic "built it in an afternoon" implementation, not a
strawman:

- MIME structure and `Content-Transfer-Encoding` via Python's stdlib
  `email.message_from_bytes` (compat32) — the classic quick-script choice.
- Quote-stripping via [`email_reply_parser`](https://pypi.org/project/email-reply-parser/),
  a real, independently-maintained PyPI library (Python port of GitHub's
  original Ruby gem), not code written for this eval.
- `.msg` bodies via [`extract-msg`](https://pypi.org/project/extract-msg/),
  the standard third-party library for reading `.msg` without Outlook.
- The specific naive choices baked in are named in the module docstring:
  prefers `text/plain` over `text/html` unconditionally (even when the
  plain part is a content-free client placeholder), falls back to a crude
  regex tag-strip for HTML-only messages, and **hardcodes UTF-8** for
  character decoding regardless of the part's declared charset — the
  single most common real-world naive-decoder bug.

**Why real libraries, not hand-rolled logic:** the brief warns that a
self-authored "adversarial" test only proves a self-authored parser fails
its own quiz. Composing two genuinely independent, widely-used libraries
the way an unsophisticated pipeline would is a stronger claim than writing
a strawman regex myself. It also surfaced a real, unplanned finding: an
attempt to also fold in `mail-parser` (another popular PyPI library) hit
`TypeError: getaddresses() got an unexpected keyword argument 'strict'`
under Python 3.12 — a genuine dependency/interpreter-version break in a
real library, encountered while building this, not manufactured for the
demo. It was dropped rather than worked around, since stdlib `email` was
sufficient and this write-up should not overstate what was actually used.

**Scoring:** normalized-text similarity via `difflib.SequenceMatcher`
against the hand-authored ground truth in `expected/`, bucketed into
PASS (≥0.90), PARTIAL (≥0.50), FAIL (below). Table-tagged fixtures use a
stricter 0.98 bar — explained under "Is the grader trustworthy?" below.
Subject decoding is checked separately, exact-match after whitespace
normalization.

### Results (last run against the committed corpus)

```
TOTAL: 28   PASS: 16   PARTIAL: 10   FAIL: 2   SUBJECT-MISMATCH: 1
```

Run `python harness/run_eval.py --verbose` for the full expected/got diff
on every file. Highlights:

- **Clean failures (FAIL):** `04_gmail_html_blockquote_no_plain.eml` (the
  extractor picks the useless `text/plain` placeholder over the real
  HTML content — 0.32 similarity); `21_nested_rfc822_attachment.eml` (the
  real content is inside a `message/rfc822` attachment; the extractor
  reports the one-line FYI body instead — 0.26 similarity, the single
  worst score in the corpus and the clearest "the answer was in the
  attachment" pipeline failure).
- **Partial failures worth reading in full:** `05_deep_chain_mixed_quote_chars.eml`
  (mixed `>`/`>>`/`|` quote characters — the library strips some hops and
  leaves others); `11_redline_inline_color.eml` and
  `26_outlook_native_redline_color.msg` (the one substantive edit is
  discarded along with the "quoted history" it's nested inside);
  `16_legacy_shiftjis_forward.eml` (the hardcoded-UTF-8 decode mangles the
  Japanese content, leaving only the English preamble); `08`/`09`/`25`
  (table/nested-table fixtures — real structural damage, see below); every
  `-----Original Message-----` fixture that lacks a leading blank line
  before the marker (`03`, `24`) keeps the marker line itself in the output.
- **Subject decoding:** `17_rfc2047_encoded_subject.eml` is the one
  SUBJECT-MISMATCH — the extractor reports the literal
  `=?UTF-8?B?...?=` encoded-word text because it never calls
  `email.header.decode_header`.
- **Real passes, not just easy fixtures:** quoted-printable and base64
  body decoding both pass cleanly (`get_payload(decode=True)` genuinely
  handles `Content-Transfer-Encoding` correctly) — a useful negative
  result showing that particular failure class is *not* present once the
  right stdlib call is used, in contrast to the charset-hardcoding bug,
  which is present regardless.

### Is the grader trustworthy?

`harness/run_eval.py` includes a `sanity_check()` that fails the whole run
(non-zero exit code) unless (a) the positive-control fixture passes and
(b) at least one fixture designed to defeat the extractor actually
registers as a failure. This isn't decorative — **it caught a real problem
during development.** The first version of the scorer used a single 0.90
similarity threshold for every file, and `08_html_table_merged_cells.eml`
scored 0.94 and registered PASS despite the extractor silently dropping
the rowspan association between "Discovery" and "Depositions" (see the
verbose diff — the category label is just gone from one row). Character-level
similarity under-weights that kind of structural damage because most of
the individual words still match. The fix — a stricter 0.98 bar for
`table:`-tagged fixtures, since table correctness is closer to binary than
prose paraphrase — is a feature-tag rule set from `MANIFEST.csv` (written
independently of the scorer, at fixture-authoring time), not a per-file
override chosen to force a particular result. The sanity check is left in
so this class of scorer error can't silently regress again.

## Real-world spot check

The scored 28-file corpus is synthetic, and the extraction task, corpus,
and harness were all built in one sitting — exactly the setup where a high
score would mostly prove that the corpus and the harness agree with each
other rather than that the extractor is actually any good. As a check on
that, `real_world_spotcheck/` holds 12 real, unmodified `.eml` files
pulled from [mailgun/talon](https://github.com/mailgun/talon)'s own test
fixtures (Apache-2.0; see `real_world_spotcheck/NOTICE.md`) — genuine
captured replies from Gmail, Outlook, Apple Mail, Yahoo, AOL, Comcast,
Hotmail, Android, iPhone, Sparrow, and Thunderbird, used by a real
production library to test the same "strip the quote, keep the reply"
task. Run `python scripts/run_real_world_spotcheck.py` to reproduce.

Result: 11 of 12 extract cleanly (just `"Hello"`, the actual new content,
correctly stripped of all quoted history) — including `outlook.eml`, a
genuine Word/Outlook-generated MIME message with the full
`From:`/`Sent:`/`To:`/`Subject:` quote-block style and no `>` prefix,
confirming the synthetic-corpus result for that same pattern (`03`, `24`)
against a real sample, not just a constructed one.

The 12th, `android.eml`, surfaces a real failure the synthetic corpus
didn't anticipate: the message is a Russian-language Gmail-for-Android
reply, and the quote-block header reads
`"...написал:"` (Cyrillic for "...wrote:") instead of English `"wrote:"`.
`email_reply_parser`'s marker detection is English-locale-specific, so it
still strips the `>`-prefixed quoted line underneath, but leaves the
localized header line itself in the output:

```
Hello
02.04.2012 14:20 пользователь "bob@xxx.mailgun.org" <
bob@xxx.mailgun.org> написал:
```

This is a genuine, organically-discovered gap (locale/language-specific
quote-header phrasing), not one of the planned checklist features — worth
adding to `FEATURE_CHECKLIST.md` as a follow-up row if this corpus is
extended.

## Licensing / privacy

Every file in `corpus/` is synthetic: fictional names (`Alice`, `Bob`,
`Carol`, generic `example.com`/`example.org` domains), fictional case
facts, no real correspondence of any kind. No public dataset (Enron or
otherwise) was scraped or redistributed. This sidesteps the licensing and
privacy review that would otherwise be required for any corpus built from
real email. The separate `real_world_spotcheck/` directory (not part of
the scored corpus) does contain real client-generated samples; see its own
`NOTICE.md` for source and license (Apache-2.0, from mailgun/talon's test
suite, no personal data of consequence — the samples are synthetic-content
test fixtures ("Test" / "Hello") authored by talon's maintainers to
exercise mail-client quoting formats, not real correspondence).

## Reflection

**What I built, from memory, then checked against the actual code:** I
recall building 23 `.eml` fixtures (via raw RFC 5322 byte templates for
cases where the wire format itself is the messiness, and
`email.message.EmailMessage` for the rest) and 5 `.msg` fixtures via real
Outlook COM automation, all listed in `MANIFEST.csv` with ground truth in
`expected/`. The harness (`harness/extract_latest.py`) composes stdlib
`email` + the real `email_reply_parser` and `extract-msg` libraries, scored
by `harness/run_eval.py` via `difflib` similarity with a stricter 0.98 bar
for table fixtures. I recalled the last real run as 16 PASS / 10 PARTIAL /
2 FAIL / 1 SUBJECT-MISMATCH. I re-ran `python harness/run_eval.py` just now
to check this claim rather than trust memory of it: it reproduced exactly
(28 total, same split, sanity check passing). One thing memory got fuzzy
on: whether the `.msg` RTF-only fixture (`28`) actually demonstrated the
intended failure — checking `README`'s own "Known limitations" section
below confirms it did **not** (Outlook auto-synced a plain body, so it
passes), which I had documented honestly at the time rather than misremembered
as a win just now.

**Weakest remaining claim:** the 28-file corpus and its `expected/` ground
truth were authored by the same process (me) in the same sitting as the
harness, even though the extractor itself uses two genuine third-party
libraries rather than hand-rolled logic. A skeptical reader's best
challenge: pick any `expected/*.txt` file and ask whether a human, given
only the raw `.eml` and no access to my intent, would write the identical
ground truth. For most fixtures the answer is clearly yes (the "new"
content is visually obvious), but for a couple of the redline/interleaved
fixtures (`06`, `11`, `26`) reasonable people could draw the boundary of
"the latest message" slightly differently, since it's inherently a
judgment call once quoting stops being purely mechanical. The mitigation
already in the repo — `real_world_spotcheck/` running the same extractor
against independently-sourced talon fixtures — only partially covers this,
since those files don't have hand-authored ground truth either (it's a
qualitative read-through, not a scored check).

**Most consequential design decision:** using two real, independently-maintained
libraries (`email_reply_parser`, `extract-msg`) inside the "naive extractor"
instead of writing my own quote-stripping/HTML-flattening logic. The
rejected alternative was a hand-rolled naive parser I fully controlled,
which would have been easier to tune for dramatic, guaranteed failures on
every fixture. I didn't take it because a self-written parser failing a
self-written adversarial corpus proves nothing beyond internal consistency
(this is FAILURE-CLASSES.md item 7's exact trap) — a real library's actual,
sometimes-surprising behavior (e.g. it correctly handles "-----Original
Message-----" quoting, which I expected to be a clean fail) is a stronger,
if messier, result.

**Verified vs. assumed:** actually ran, with real output inspected: every
`generate_*_corpus.py` script (corpus exists on disk, 28 files); every
`.msg` file's OLE2 magic bytes via `olefile.isOleFile`; `harness/run_eval.py`
against the committed corpus, twice, at different points, with matching
output; `pip install -r requirements.txt` into a throwaway venv followed by
`python harness/run_eval.py` in that clean venv (confirms the README's
install instructions actually work, not just "should work"); `extract_msg`
against the RTF-only `.msg` fixture specifically, to check the claimed
limitation rather than assert it; a byte-level `git cat-file` comparison
against on-disk bytes that caught a real CRLF-normalization bug from the
ambient `core.autocrlf=true` git config, which I then fixed with
`.gitattributes -text` and re-verified via the same byte comparison. Not
yet independently verified at the time of this paragraph: a dispatched
adversarial-audit subagent's findings were received but not yet acted on
in this draft (see the commit history and any later revision of this
section for what came of that).

**With another 30 minutes:** extend the harness's extractor to actually
open/attempt-parse attachment content (PDF/DOCX text extraction, at least
a page count or "opened without error" check) rather than only ever
reading the message body. Right now `19_multi_attachment_types.eml`,
`20_inline_cid_image.eml`, and `23_corrupted_attachment.eml` are
structurally guaranteed to score PASS because the extractor's code path
never touches non-text MIME parts — the corpus files correctly exist to
probe that, but the harness doesn't yet close the loop on them, which
overstates what those three rows of `MANIFEST.csv` actually demonstrate.
That's a real gap, not a hypothetical one, and it's the highest-value fix
available in the time remaining.

## Known limitations

- **The RTF-only `.msg` body trap didn't reproduce.** The feature
  checklist (and `generate_msg_corpus.py`'s docstring) call out that some
  real `.msg` files store their readable content *only* in a compressed
  RTF stream, with no synced plain-text or HTML property — a case
  `extract-msg`'s plain `.body` accessor can return empty for. I
  attempted to approximate this by composing `28_outlook_native_richtext_only.msg`
  with `BodyFormat = olFormatRichText` via Outlook COM automation, and
  verified the actual result rather than assuming it: Outlook still
  auto-synced a readable plain-text body, so `extract-msg` returns it
  correctly (`27`/`28` both PASS). Forcing genuine RTF-only storage
  requires either a lower-level COM library (e.g. Redemption, not
  installed here) or hand-building a compressed-RTF stream per
  MS-OXRTFCP, both out of scope for the time available. This is reported
  as a negative result, not silently dropped or faked.
- **Zip/archive traversal is out of scope for the harness.**
  `22_zip_with_eml.eml` exists to test whether a pipeline even attempts to
  open a `.zip` attachment; the single extraction task only checks the
  top-level body (correctly, since opening the zip isn't part of "extract
  the latest message"), so this fixture always passes the harness's task
  and its interesting property (does your pipeline recurse into archives
  at all?) has to be checked by hand, as noted in `MANIFEST.csv`.
- **`mail-parser` was tried and dropped**, not because it's a bad library,
  but because the installed version (4.4.0) breaks under Python 3.12 —
  see the harness section above. Worth retrying with a version-pinned
  environment if this corpus is reused elsewhere.
- **28 files, not 30** — comfortably inside the brief's 15-30 range;
  stopped there because every checklist row already had coverage and
  additional files would have been redundant variants rather than new
  failure mechanisms.
- 90-minute budget: no attempt was made at deeper chain depths (>8 hops),
  additional legacy encodings beyond Shift_JIS, or PST-file-level corpus
  packaging (Outlook data files), all of which are reasonable follow-ups.
