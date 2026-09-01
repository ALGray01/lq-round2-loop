# Statutes/Regs MCP: 16 CFR Part 312 (COPPA Rule)

An MCP server over a real, currently-in-force slice of U.S. federal law:
**16 CFR Part 312**, the FTC's Children's Online Privacy Protection Rule
(the regulation implementing COPPA), plus a companion corpus of the
statute it implements, **15 U.S.C. 6501-6506**. It supports
retrieve-by-citation, hierarchy browsing, full-text search, and
cross-reference lookups (both "what does this section cite" and "what
cites this section") — against real primary-source text pulled from the
official [eCFR](https://www.ecfr.gov) versioner API and, for the
statute, [GovInfo](https://www.govinfo.gov)'s citation link service —
not a plan or a mock.

## Why this slice

The brief asked for one honestly-solved slice rather than a plan to scrape
everything. 16 CFR Part 312 was chosen because it is:

- **Real, current, primary law** — pulled directly from the eCFR API
  (`https://www.ecfr.gov/api/versioner/v1/`), which is itself the U.S.
  government's authoritative, daily-updated XML rendering of the CFR.
- **Bounded but non-trivial** — 13 sections, ~49KB of text, dense with
  real internal cross-references (definitions section alone is cited by
  half the other sections) and real external references (to its enabling
  statute, to the FTC Act, to other CFR provisions) — enough to actually
  exercise the cross-reference problem instead of trivially "solving" it
  on a single self-contained paragraph.
- **Cleanly structured** in the source XML (`DIV5`/`DIV8` elements with
  citation metadata already attached), so the hierarchy and citation
  parsing is a real parsing problem, not something faked with hand-typed
  JSON.

This deliberately does **not** try to cover an entire CFR title, a whole
state code, or all of EU secondary legislation — that would have been the
"plan to scrape everything" the brief explicitly said beats a working
slice. The architecture (fetch → build → serve) generalizes to any other
eCFR title/part by changing two CLI arguments (see below); it does not
generalize automatically to non-eCFR sources.

## Architecture

```
scripts/fetch_ecfr.py   -- the only network-touching code. Hits the public
                            eCFR versioner API, saves raw JSON/XML into
                            data/raw/. Retries with exponential backoff
                            (bash's lib/retry.sh isn't usable in this
                            environment - see Environment note below - so
                            this reimplements the same retry contract in
                            Python).
scripts/build_corpus.py -- parses the raw XML + structure JSON into
                            data/corpus.json: one record per section with
                            citation, heading, text, full hierarchy path,
                            and an extracted/resolved cross-reference list.
data/corpus.json        -- the queryable CFR corpus. Committed to the repo,
                            so the server runs fully offline (no network
                            needed except for the optional check_currency
                            tool).
scripts/fetch_usc.py    -- fetches 15 U.S.C. 6501-6506 (COPPA's enabling
                            statute) as PDFs from GovInfo's citation link
                            service - the closest thing to a
                            citation-addressable official U.S. Code source
                            this project could find (see Companion U.S.
                            Code corpus below for why this is PDF-based
                            rather than clean XML/JSON like eCFR).
scripts/build_usc_corpus.py -- extracts clean per-section text from those
                            PDFs into data/usc_corpus.json, handling
                            page-overlap deduplication and chapter-boundary
                            cleanup (see below - a real bug here was found
                            and fixed by inspecting actual output).
data/usc_corpus.json    -- the companion statute corpus. Also committed,
                            also offline-servable.
server/statutes_mcp.py  -- the MCP server itself (FastMCP, stdio
                            transport). Reads data/corpus.json and, for
                            get_usc_citation, data/usc_corpus.json.
tests/test_mcp_client.py -- an end-to-end check that drives the server
                            over the real MCP client SDK (stdio transport,
                            not a hand-rolled stub) and asserts on the
                            actual protocol responses.
```

## How it solves currency / hierarchy / cross-reference

**Currency.** The corpus is a snapshot, stamped with the exact eCFR
`snapshot_date` it was pulled as of (`2026-07-27` at build time) and the
literal source URL used. Rather than silently assuming that stays valid,
the server exposes a `check_currency` tool that re-queries the *live* eCFR
titles endpoint at call time and reports whether the cached snapshot is
still the latest issued text, and what to run if it isn't
(`scripts/fetch_ecfr.py` + `scripts/build_corpus.py`). This was verified
against the real API (see Verification below), not assumed.

**Hierarchy.** Every section carries its full ancestor path (title →
chapter → subchapter → part), recovered by walking the real eCFR structure
tree rather than hand-encoded. `list_structure` exposes this so a caller
can browse from the top instead of already knowing a citation.

**Cross-reference.** `scripts/build_corpus.py` extracts every
cross-reference in each section's text via patterns calibrated against the
actual text (not invented in the abstract - see the regexes' comments),
and classifies each one:
- `internal_section` — another section of this same part (e.g. `§ 312.5`,
  or a range like `§§ 312.2 through 312.8, and 312.10`, which is expanded
  to every section in the range, not just the two endpoints). These are
  **resolved**: checked against the actual set of sections in the corpus.
- `usc` — a U.S. Code citation (e.g. `15 U.S.C. 6501`, including the
  worded form `section 551(1) of title 5, United States Code`).
- `named_act_section` — a section number tied to a named Act rather than a
  bare U.S.C. cite (e.g. `section 6502(a) of this Act`).
- `self_reference` — "this part"/"this section"/"this paragraph".

Of the 4 distinct `usc`-type citations actually found in this corpus'
text, exactly one — `15 U.S.C. 6501` — points to the statute this Part
implements; the other three (`15 U.S.C. 45`, `15 U.S.C. 57a(a)(1)(B)`,
`5 U.S.C. 551(1)`) point to a different statute (the FTC Act) or a
different title (the APA) entirely. For that one in-scope case, this
project **does** ingest and resolve the target text: a companion corpus
of 15 U.S.C. 6501-6506 (see Companion U.S. Code corpus, below), so
`get_cross_references` can report `15 U.S.C. 6501` as
`resolved_in_companion_usc_corpus` — fetchable in full via
`get_usc_citation` — while the FTC Act and APA cites, genuinely out of
scope, stay honestly in `external_unresolved` rather than being silently
lumped in with the one that's actually resolved.

`named_act_section` references get the same treatment, one level more
carefully: `"section 6502(a) of this Act"` and `"sections 6503 and 6505
of the Children's Online Privacy Protection Act of 1998"` both refer to
COPPA itself, and this project verified by reading the actual retrieved
statute text (not assumed) that COPPA's own enabling-statute section
numbers happen to equal their final U.S. Code section numbers directly
(§ 6502 "of this Act" really is 15 U.S.C. 6502) - so those *do* resolve
via the companion corpus, exactly like a bare `usc` cite. But
`"section 18(a)(1)(B) of the Federal Trade Commission Act"` — a
different Act entirely, whose own section 18 is *not* 15 U.S.C. 18 (it's
15 U.S.C. 57a, per the very next parenthetical in the same sentence) —
correctly stays unresolved: `is_coppa_self_reference` only recognizes
"this Act" and "the Children's Online Privacy Protection Act" by name,
and doesn't generalize to any other named Act, because doing that
correctly would need ingesting that Act's own text too (exactly the same
reasoning that kept the FTC Act and APA out of scope above). The raw
citation text is returned for every unresolved case, so a caller knows
exactly what wasn't chased down and can look it up itself.
`find_sections_citing` then answers the reverse question — "which
sections cite X?" — which is the one query that genuinely needs an
index over the whole corpus rather than just one section's text, and is
the "structured query" half of the brief.

A second, independent structured query comes from parsing the CFR's
standard definitions convention (a paragraph opening with "Term means
..." / "Term includes ...") out of § 312.2, giving `list_definitions` /
`get_definition` — a direct answer to "what does this regulation mean by
X", rather than making the caller keyword-search and read the whole
definitions section by hand. All 18 terms extracted this way were
manually spot-checked against the real text (see Verification below); the
heuristic correctly captures multi-word terms (`"Mixed audience website
or online service"`) and the one term that uses "includes" instead of
"means" (`"Parent"`), and correctly stays silent on the many paragraphs
elsewhere in the part that happen to contain the word "means" or
"includes" without being definitions.

## Companion U.S. Code corpus (15 U.S.C. 6501-6506)

Unlike eCFR, there's no clean per-section XML/JSON REST API for the
U.S. Code that this project could find (`uscode.house.gov`'s bulk data
is organized by Congress/release-point ZIP files, not addressable by
citation; `api.congress.gov` requires a signup API key not available in
this environment). What *is* citation-addressable without a key is
GovInfo's link service, `https://www.govinfo.gov/link/uscode/{title}/
{section}` — but each request resolves to a rendered **PDF** of the
printed statute page(s) around that section, not structured text: the
same "Page 2243/2244..." scanned-book layout as the physical U.S. Code
volumes, where adjacent sections' fetches overlap on shared pages and a
page can contain the tail of the section before the one requested and/or
the start of the one after.

`scripts/fetch_usc.py` fetches the 6 PDFs (one per section, 6501-6506);
`scripts/build_usc_corpus.py` deduplicates the overlapping pages by their
own printed page number, concatenates the unique pages in order, and
splits on real `"§ NNNN. Heading"` boundaries rather than trusting
individual fetch boundaries. Building it against the real PDFs surfaced
a genuine bug the same way the CFR corpus's bugs were found — by
inspecting actual output, not by reading the code: the last section
(6506) was silently swallowing the *next* U.S. Code chapter's heading and
table of contents, because nothing stopped extraction at a chapter
boundary when there was no further section heading to stop at. Fixed
(`CHAPTER_BOUNDARY_RE`) and pinned down with `tests/test_build_usc_corpus.py`,
written against synthetic text shaped like the real extraction output.

**Honest caveats specific to this corpus**: the text comes from PDF
extraction of a scanned/rendered book layout, not a structured source, so
it may carry minor artifacts (line-break hyphenation like `"col-\nlected"`
was observed and left as-is rather than silently "corrected" in a way
that could introduce its own errors); it includes the official
"Statutory Notes and Related Subsidiaries" / effective-date notes
alongside the operative text, which is how the real U.S. Code presents
it but is more verbose than the CFR corpus's plain-section text; and it
is not a substitute for the official printed or XML U.S. Code where
legal certainty matters. `get_usc_citation`'s docstring and
`data/usc_corpus.json`'s own `note` field say this explicitly rather than
presenting the text as equivalent in cleanliness to the eCFR-derived
corpus.

## Tools exposed

| Tool | Purpose |
|---|---|
| `get_citation(citation)` | Retrieve-by-citation. Accepts `"16 CFR 312.5"`, `"312.5"`, `"§ 312.5"`, `"312.5(c)(1)"`. |
| `list_structure()` | Hierarchy + list of all 13 sections, for browsing. |
| `search_text(query, max_results=10)` | Full-text keyword search with snippets. |
| `find_sections_citing(citation)` | Reverse cross-reference lookup — a structured query. |
| `get_cross_references(citation)` | Forward cross-reference lookup, split into resolved-in-corpus / resolved-in-companion-USC-corpus / external-unresolved / self-reference. |
| `list_definitions()` | Every defined term in the part (from § 312.2), each tagged with its citation. |
| `get_definition(term)` | Look up one defined term by name, case-insensitive. |
| `get_usc_citation(citation)` | Retrieve-by-citation from the companion statute corpus. Accepts `"15 U.S.C. 6501"`, `"6501"`, `"§ 6501"`. |
| `check_currency()` | Live re-check against the eCFR API for staleness. |

## Worked example (real output, captured from an actual MCP call)

`get_citation("312.7")`:

```
An operator is prohibited from conditioning a child's participation in a
game, the offering of a prize, or another activity on the child's
disclosing more personal information than is reasonably necessary to
participate in such activity.
```

`find_sections_citing("312.4")` — the reverse cross-reference query, i.e.
"what in this corpus cites the Notice section?":

```json
{
  "target": "16 CFR 312.4",
  "cited_by_count": 4,
  "cited_by": [
    { "citation": "16 CFR 312.3", "via": ["§ 312.4(b)"] },
    { "citation": "16 CFR 312.5", "via": ["§ 312.4", "§ 312.4(c)(1)", "..."] },
    { "citation": "16 CFR 312.10", "via": ["§ 312.4(d)"] },
    { "citation": "16 CFR 312.11", "via": ["§§ 312.2 through 312.8, and 312.10"] }
  ]
}
```

Note the last hit: `§ 312.11` cites `312.4` only because it cites the
*range* `§§ 312.2 through 312.8, and 312.10`, which the range-expansion
logic (see Verification below) correctly unrolls to include `312.4` — a
naive "does the literal string 312.4 appear nearby" search would have
missed this entirely.

## Running it

```bash
pip install -r requirements.txt

# (Optional - data/corpus.json is already committed) Re-fetch and rebuild:
python scripts/fetch_ecfr.py --title 16 --part 312
python scripts/build_corpus.py

# (Optional - data/usc_corpus.json is already committed) Re-fetch and
# rebuild the companion U.S. Code corpus:
python scripts/fetch_usc.py
python scripts/build_usc_corpus.py
python scripts/build_corpus.py   # re-run after, to re-resolve usc cross-refs against it

# Run the server directly (speaks MCP over stdio):
python server/statutes_mcp.py

# Or verify it end-to-end over the real MCP client SDK:
python tests/test_mcp_client.py
```

To use from Claude Desktop or another MCP host, point it at
`server/statutes_mcp.py` with `python` as the command, e.g. in
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "coppa-rule": {
      "command": "python",
      "args": ["/absolute/path/to/server/statutes_mcp.py"]
    }
  }
}
```

## Verification actually performed

- `python tests/test_mcp_client.py` spawns the real server as a subprocess
  and drives it via `mcp.client.stdio` / `ClientSession` (the official SDK
  client, not code written by this project) through `initialize` →
  `list_tools` → `call_tool`, asserting on the real protocol responses:
  citation lookup for three input forms, a deliberately-missing citation
  (312.99) correctly reporting `found: false`, a reverse cross-reference
  query, a full-text search, cross-reference honesty (312.9 correctly
  shows `usc` and `named_act_section` as external/unresolved), a live
  `check_currency` call against the real eCFR API, and a structure listing
  confirming exactly 13 sections. Last run: all checks passed, including
  `check_currency` reaching the live API and confirming `up_to_date: true`
  against snapshot date 2026-07-27.
- The cross-reference range-expansion logic (`§§ 312.2 through 312.8, and
  312.10`) was manually inspected against `data/corpus.json` output and a
  bug (only the two endpoints being captured, and combined `", and"`
  separators being dropped) was found and fixed this way, not assumed
  correct from reading the regex.
- `tests/test_retry.py` actually exercises `scripts/fetch_ecfr.py`'s
  retry-with-backoff helper against simulated transient and permanent
  failures (not just the happy path every real fetch so far has taken,
  since the eCFR API answered successfully both times it was called) -
  confirms it recovers after transient failures, backs off with
  (roughly) doubling delay, gives up and re-raises after exhausting
  attempts, and doesn't sleep at all on first-try success.
- `tests/test_build_corpus.py` (`python -m pytest tests/ -v`, 48 tests
  total across `test_build_corpus.py` (23), `test_retry.py` (4),
  `test_missing_corpus.py` (1), `test_server_helpers.py` (12), and
  `test_build_usc_corpus.py` (8)) unit
  tests the extraction logic against real sentences from the source text,
  including true-negative cases it must get right by *not* matching or
  *not* resolving: a citation to a section number absent from the corpus
  (`§ 312.99`) must come back `resolved: False`; a U.S.C. cite must never
  be marked resolved; plain text with zero citations must yield zero
  references. Writing these caught a second, more serious bug: the range
  expander was double-counting the first section in every `"X through Y"`
  span (e.g. `312.2 through 312.8` produced `[312.2, 312.2, 312.3, ...
  312.8]`), which the earlier manual spot-check had missed because it
  only looked for *drops*, not *duplicates*. Fixed and re-verified by
  re-running both the unit tests and the full MCP client test end-to-end.
- Ran adversarial inputs through the real MCP client against every
  `citation`-taking tool: a path-traversal string, an empty string, a
  100,000-character string, a SQL-injection-shaped string, an XSS-shaped
  string, and `None` in place of a string. None crashed the server; `None`
  correctly failed MCP-level schema validation (`isError: True`) before
  ever reaching the tool body. The 100,000-character input surfaced a real
  (minor) issue - it was being echoed back in full inside the error
  message - which is now fixed with a length cap (`MAX_CITATION_LEN`,
  `safe_repr`) verified to truncate the echoed value instead.
- **Reserve-phase adversarial audit** (three independent, fresh-context
  subagents with no prior knowledge of this build - see Reflection below
  for how this was run): an **attacker** subagent live-fired path
  traversal, null bytes, format-string payloads, unicode tricks (RTL
  override, zero-width space, BOM), oversized input, and non-string types
  against every tool over the real MCP protocol, and found one genuine
  gap: `search_text`'s `query` parameter had no length cap and echoed a
  1,000,000-character input back in full, unlike `get_citation`,
  `find_sections_citing`, `get_cross_references`, and `get_definition`,
  which were already guarded. Fixed (`MAX_QUERY_LEN`, verified the fix
  drops the response from ~1MB to 325 bytes) and added as a permanent
  regression check in `tests/test_mcp_client.py`. Everything else the
  attacker tried was already handled safely. A **verification skeptic**
  subagent independently rebuilt the corpus from raw XML and confirmed a
  byte-identical SHA256 hash against the committed `data/corpus.json`,
  manually recounted all 18 definitions and spot-checked several
  cross-references directly against the raw XML (not against this
  project's own code output), reproduced the README's worked examples and
  confirmed byte-for-byte matches, and deliberately renamed
  `data/corpus.json` away to confirm the server fails with a clean,
  honest MCP error (`isError: True`) rather than misbehaving silently -
  restoring the file immediately afterward. That missing-corpus check is
  now also a permanent test (`tests/test_missing_corpus.py`, run against
  an isolated scratch copy of the server so it can never touch the real
  committed data file). Nothing hollow or circular was found. A
  **baseline builder** subagent's findings are written up in their own
  section below.
- **Second audit round** (the protocol calls for a repeat round when the
  first found real issues): a fresh **attacker** subagent independently
  re-verified the `search_text` fix at 2x the payload size (2,000,000
  chars, same 325-byte bounded response) and confirmed it didn't
  regress normal search, then found two new low-severity bugs by testing
  surfaces round 1 hadn't touched: (1) `search_text(max_results=0)` (or
  any non-positive value) returned 1 result instead of 0, because the
  result-count cap was checked *after* appending a match rather than
  before; (2) `safe_repr`'s truncation bounded the *input* character
  count, not the *rendered* output size, so escape-heavy input (e.g. 1000
  zero-width spaces, each rendering as the 6-character escape `​`)
  could still produce an error message several times longer than
  intended. Both fixed (`search_text` now checks `max_results <= 0`
  up front; `safe_repr` now bounds the rendered string directly, not just
  the input slice) and covered by new tests
  (`tests/test_server_helpers.py`, plus a `max_results<=0` case in
  `tests/test_mcp_client.py`). The same subagent also tried 5 concurrent
  MCP client sessions with 7 simultaneous tool calls each (35 total) and
  citation-shaped-but-nonexistent letter-suffix identifiers (`"312.5a"`)
  - both clean. A fresh **verification skeptic** subagent caught a real
  documentation bug: README still said "18 pytest tests" and named only
  two of three test files, left over from before
  `tests/test_missing_corpus.py` was added - fixed (now correctly says
  19, then 25 after this round's additions). It also confirmed the
  `search_text` fix and the missing-corpus test both do exactly what
  their commit messages claim, by reading the diffs and re-running
  everything directly. A fresh **baseline builder** subagent extended the
  cross-reference comparison from round 1's 3 sample targets to all 13
  possible targets, and found that round 1's "no false positives" claim
  didn't survive full coverage — see Baseline comparison below.
- **Companion U.S. Code corpus** (built after the audit rounds, with
  remaining budget): fetched the 6 real PDFs from GovInfo's link service,
  and found a real bug by inspecting the extracted output rather than
  trusting the regex - the last section (6506) was silently swallowing
  the next U.S. Code chapter's heading/table of contents, since nothing
  stopped extraction at a chapter boundary. Fixed, then caught a *second*
  bug the same way while writing `tests/test_build_usc_corpus.py`: the
  first version of that test used a plain hyphen instead of the real
  em-dash character GovInfo's PDFs actually use in chapter headings,
  which would have made the test pass without actually exercising the
  fix - caught because the test failed against real extracted text and
  the mismatch was diagnosed rather than the assertion being loosened to
  make it pass. All 6 sections' start/end boundaries were then manually
  read end-to-end to confirm no other section's text bleeds into its
  neighbor. Wired into the CFR corpus (`resolve_usc_against_companion`)
  and the server (`get_usc_citation`, updated `get_cross_references`),
  verified live over the real MCP client: `15 U.S.C. 6501` (the one
  in-scope citation) correctly moves to `resolved_in_companion_usc_corpus`
  with real retrievable text, while `15 U.S.C. 57a` (a real citation, but
  outside the ingested 6501-6506 range) correctly stays in
  `external_unresolved` rather than being over-eagerly marked resolved.
  Also re-ran the same adversarial oversized-input check used on other
  tools against `get_usc_citation` directly - clean, the existing
  length-cap pattern held without needing a fix.
- **Fresh audit of the USC feature specifically** (the two prior audit
  rounds happened before this feature existed, so it had never been
  independently reviewed): a fresh subagent with no context of this
  session found one **critical** bug by driving the real server -
  `get_usc_citation`/`normalize_usc_citation` matched on bare section
  number alone, ignoring any stated U.S.C. title, so `"20 U.S.C. 6501"`
  or `"42 U.S.C. 6501"` (real citations to different, unrelated statutes)
  silently returned Title 15's real COPPA text instead of failing. The
  build-time equivalent (`resolve_usc_against_companion` in
  `scripts/build_corpus.py`) already checked title *and* section
  correctly - the same fix just hadn't been carried over to the
  query-time tool, and no test caught the gap. Fixed by validating an
  explicitly-stated title against the corpus's actual title (15) before
  accepting a bare section number, confirmed against every adversarial
  case the audit found (`20/42/5 U.S.C. 6501`, and the malformed reversed
  order `"6501 U.S.C. 20"`), and pinned down with new tests in
  `tests/test_server_helpers.py` and `tests/test_mcp_client.py`. The same
  audit found a **minor** metadata defect - § 6502's real printed heading
  spans 4 lines before its body starts, but the section-splitting regex
  only captured the first line, silently leaving the rest as a prefix of
  `text` instead (no data was lost, just misfiled between `heading` and
  `text`). Investigated a general fix using PyMuPDF's per-span bold/font
  metadata (confirmed section headings are bold in the source PDFs) and
  rejected it: subsection labels like `"(a) Acts prohibited"` turned out
  to use the *identical* bold styling with no intervening plain-text
  span, so "stop at the first non-bold span" over-captures into the body
  instead of solving the problem - verified this by direct extraction
  before deciding not to ship it, not by assuming it would be too messy.
  Applied a manually-verified, self-checking correction instead (fails
  loudly if the expected continuation text isn't found, rather than
  silently mis-applying), covered by `tests/test_build_usc_corpus.py`.
- **Extended USC resolution to COPPA self-references** (with remaining
  budget, closing a gap the Limitations section had explicitly flagged):
  read the real retrieved text of `15 U.S.C. 6502` to confirm, rather
  than assume, that `"section 6502(a) of this Act"` in the CFR text and
  `15 U.S.C. 6502` really are the same section - true for COPPA because
  its own drafting cites itself using the final codified U.S. Code
  numbers directly, not original Public Law section numbers. Verified
  the distinction holds by checking the one case in this corpus where it
  *doesn't* apply: `"section 18(a)(1)(B) of the Federal Trade Commission
  Act"`, which the same sentence's own parenthetical confirms is actually
  `15 U.S.C. 57a(a)(1)(B)` - proving "Act section number = U.S.C. section
  number" is specific to COPPA's drafting, not a general rule, and
  correctly staying unresolved rather than being (wrongly) generalized.
  Live-checked over the real MCP client: `get_cross_references("312.9")`
  (the one section citing both cases) now shows 3 entries correctly
  resolved via the companion corpus and 2 correctly still external.
  6 new unit tests cover the distinction, including a true-negative for
  a `named_act_section` entry with no candidate citation at all.
- **Reserve-phase audit, third round** (fresh attacker/skeptic/baseline
  subagents, covering everything committed since the second round -
  the COPPA self-reference resolution above had not yet been
  independently reviewed): the **attacker** found one more **critical,
  live** bug - the prior title-validation fix for `get_usc_citation`
  only recognized the abbreviated citation form (`"N U.S.C."`); the
  *worded* form (`"section 6502 of title 20, United States Code"`,
  `"Title 20, section 6502"`, `"20 United States Code 6502"`) bypassed
  it entirely and still returned Title 15's real text for other titles.
  Fixed by checking broadly for any U.S.C./title marker word first and
  requiring every title number found near one to equal 15, so an
  unanticipated phrasing fails closed instead of silently falling
  through to the bare-number match - confirmed against all the
  attacker's exact cases plus the legitimate worded form, and pinned
  down with new tests. The attacker also found (but rated low-severity,
  since it fails by omission not misresolution) that `is_coppa_self_reference`
  has no antecedent tracking - it's a same-sentence coincidence that "this
  Act" resolves correctly in the real text, not true reference tracking,
  and `NAMED_ACT_RE` is case-sensitive. The **verification skeptic**
  independently re-confirmed both specific factual claims behind the
  COPPA-self-reference feature by reading the raw source files directly,
  re-ran the full suite (46 passed, matching README), rebuilt
  `data/corpus.json` from scratch and diffed it byte-for-byte identical
  against the committed file, and found one additional real (low
  severity, not currently triggered) gap: named-Act range phrasing
  ("sections 6501 through 6506 of this Act") only captures the two
  endpoints, unlike the CFR-internal path's proper range expansion. The
  **baseline builder** built a naive version of the COPPA-self-reference
  gate (skip `is_coppa_self_reference`, resolve any in-range number
  regardless of Act name) and found it produces byte-identical output to
  the shipped version on the real corpus - the gate is currently
  unexercised as a discriminator by this specific data - but confirmed
  with a synthetic counter-example that the gate prevents a real
  false-positive class the naive version would produce under a different
  Act name using an in-range number. All three findings not already fixed
  are recorded honestly in Limitations below rather than left only in
  this log.

## Reflection

**What I built (recall check — written from memory, then verified against
the actual code/output before finalizing).** A fetch→build→serve pipeline
over 16 CFR Part 312 (COPPA Rule): `scripts/fetch_ecfr.py` pulls the raw
structure + full-text XML from the real eCFR versioner API;
`scripts/build_corpus.py` parses that into `data/corpus.json` — 13
sections, each with citation, heading, full hierarchy path, an extracted
and resolved/unresolved cross-reference list, plus a corpus-wide
definitions list (18 terms). This section of the Reflection was drafted
at the reserve-phase checkpoint, when the server exposed 8 tools and the
suite had 25 tests; after that, with more budget available, a companion
15 U.S.C. 6501-6506 corpus was added (`get_usc_citation`, bringing the
server to 9 tools) and audited fresh, which found and fixed one more real
bug (see the Verification entries above) - the suite now has 40 pytest
tests across six files (`test_build_corpus.py`, `test_retry.py`,
`test_missing_corpus.py`, `test_server_helpers.py`,
`test_build_usc_corpus.py`) plus `test_mcp_client.py`'s separate
end-to-end run. I recalled the test suite as "pytest unit tests plus an
MCP client test" and went back to check the exact numbers each time
rather than assert them from memory - my first-draft recollection
undercounted it (I remembered "a dozen or so" before checking), and a
round-2 verification-skeptic subagent later caught that this very
sentence still said "18" after a test file had already been added,
which was corrected and has now been updated twice more since. One
thing my memory got right without needing correction: that the two real
bugs found during the build (range-expansion dropping/duplicating section
numbers) were both caught by actually inspecting `data/corpus.json`
output, not by the regex looking correct on a read-through.

**The single weakest remaining claim.** The cross-reference and
definitions extraction logic is regex/heuristic-based, calibrated
entirely against the actual text of this one part (16 CFR Part 312). It
has never been run against a different CFR title or part, so "this
correctly parses CFR cross-references" is really only proven for this
specific corpus's citation conventions — a different title's drafting
style (longer citation chains, different range phrasing, footnote-style
references) could easily break patterns like `SECTION_REF_RE` or
`DEFINITION_RE` in ways nothing here would catch. A skeptic could expose
this in about five minutes by pointing `fetch_ecfr.py` at a different
title/part and diffing the extracted references against a manual read of
the text.

**The single most consequential design decision — revised once, honestly.**
Originally: scoping the corpus to 16 CFR Part 312 alone and *not* also
ingesting the U.S. Code text its `usc` cross-references point to,
because I'd concluded (without actually testing it) that there was no
official per-section U.S. Code source clean enough to be worth the
budget - uscode.house.gov's bulk data being release-point ZIPs, not a
citation endpoint. That conclusion was itself never verified by
execution, which is exactly the failure mode this whole exercise is
supposed to catch. With more budget available, I went and actually
checked: GovInfo's citation link service (`govinfo.gov/link/uscode/...`)
*is* addressable by citation, resolving to a rendered PDF of the printed
statute page - messier than eCFR's clean XML, but genuinely extractable
(confirmed by building it - see Companion U.S. Code corpus, above, and
the Verification entry on it). So the original decision wasn't wrong
given the assumption it was made under; the assumption itself just
hadn't been tested, and turned out to be only half true. What I still
did *not* do: chase the FTC Act (`15 U.S.C. 45`, `57a`) or the APA
(`5 U.S.C. 551`) cross-references - those remain honestly unresolved,
because ingesting them would mean repeating this same PDF-extraction
effort for two more, unrelated statutes, which is real, uncapped scope
growth rather than closing the one loop (regulation → its own enabling
statute) that was already half-built and directly motivated. I did later
extend resolution to `named_act_section` references, but only the subset
that are actually COPPA self-references ("section 6502(a) of this Act"),
verified against the retrieved statute text rather than assumed - not to
`named_act_section` references naming any other Act, which stay
unresolved for the same "don't chase a second statute" reasoning as the
FTC Act/APA case.

**What I actually ran to verify this, versus what I never got to.** Ran:
all 48 pytest unit tests (real output, real pass); the full
`tests/test_mcp_client.py` suite through the actual `mcp.client.stdio` SDK
against the real subprocess server (not a hand-rolled stub) — citation
lookup in three input forms, a true-negative missing-citation lookup,
reverse and forward cross-reference lookups, full-text search, definition
lookup with a true-negative, and a live `check_currency` call that
actually reached the real eCFR API and confirmed `up_to_date: true`;
adversarial inputs (path traversal string, empty string, 100,000-char
string, SQL/XSS-shaped strings, `None`) run through the real MCP client
against `get_citation`, which surfaced and let me fix a real
input-echoing issue; a simulated "fresh clone" (copying exactly the
git-tracked files into a scratch directory, since this environment's
broken `sh.exe` makes `git clone` itself fail) confirmed the repo runs
correctly from a clean checkout; and `tests/test_retry.py`, added
specifically because I noticed the retry-with-backoff helper had only
ever been exercised on network calls that happened to succeed on the
first try. What I never got to: running the pipeline against a second
eCFR title/part to see whether the extraction logic generalizes at all
(see weakest claim above), and load/concurrency behavior with multiple
simultaneous MCP client sessions. (The missing-corpus-file path was a gap
in this list until the reserve-phase verification-skeptic subagent
checked it directly - now covered by `tests/test_missing_corpus.py`.)

**Post-audit update.** After drafting the above, two rounds of a
three-subagent adversarial audit (attacker / verification skeptic /
baseline builder, each fresh subagent with no prior context of this
session) ran against the repository. Round 1 found and I fixed one real
issue (`search_text` missing the length cap other tools had), confirmed
the missing-corpus-file failure mode is honest (now a permanent test),
and ran a 3-target baseline comparison. Round 2 - deliberately told to
verify round 1's fixes rather than repeat its ground, and to attack round
1's own conclusions rather than rebuild them - found two more real,
low-severity bugs (`search_text(max_results<=0)` returning 1 result
instead of 0; `safe_repr` bounding input length rather than rendered
output length, letting escape-heavy input balloon past its cap), both
fixed and covered by new tests; caught a documentation staleness bug
(README's test count wasn't updated when a test file was added, found and
fixed, then found *again* stale after the next addition - a genuine
"who verifies the verifier's paperwork" moment); and re-ran the baseline
comparison across all 13 possible targets instead of round 1's 3,
which overturned part of round 1's own conclusion (see Baseline
comparison below - round 1's "no false positives" claim was an artifact
of an under-sampled test, not a real property of the naive alternative).
Nothing else survived either round's scrutiny. This matches, rather than
contradicts, the weakest-claim assessment above - every gap found was
either an edge case (oversized/adversarial input, a missing dependency,
a boundary value) that untested code tends to have, or a verification
process correcting its own under-coverage on a second, harder look - not
evidence the core citation/hierarchy/cross-reference logic itself was
wrong. If anything, the audit's own trajectory (round 2 catching what
round 1's narrower sampling missed, including in round 1's *own* claims)
is a concrete illustration of why this repeat-if-issues-found protocol
exists rather than stopping after one pass.

**With another 30 minutes** — I said I'd point `scripts/fetch_ecfr.py` at
a second CFR part with a different citation style and subparts, and then
actually did it before running out of things to spend remaining budget
on well (see Generalization test below): 16 CFR Part 5 confirmed the
core parsing/hierarchy/definitions logic generalizes, but surfaced two
real, previously-hypothetical gaps (subpart identity is dropped;
non-`§` cross-references like "5 CFR part 2635" are silently missed
rather than flagged unresolved). Neither affects the shipped Part 312
corpus, but both are now documented as confirmed limitations instead of
guesses. With yet another 30 minutes from here, the next thing I'd do is
fix the non-`§` cross-reference gap specifically (it's the one that
silently drops information rather than just missing structure), since a
caller currently has no way to know that kind of reference exists at
all, versus the subpart gap, which is at least visible as "no subpart
field in the response."

**Reserve-phase checkpoint (this is the current, authoritative answer to
the five points below — the paragraphs above are the real history of how
it got here, not superseded or wrong, just earlier).**

*Recall check (final, post-round-3).* From memory, before re-checking:
the server has 9 tools, backed by two committed corpora, with a pytest
suite in the high 40s plus the separate `test_mcp_client.py` end-to-end
run, and I recalled the third audit round having found and fixed one
critical bug. Checked just now: `python -m pytest tests/ -q` → **48
passed**; `python tests/test_mcp_client.py` → all checks passed
(including the two new worded-form-collision checks); `git log
--oneline` confirms the critical fix (worded-form U.S.C. citations
bypassing title validation) is committed. Memory was correct on all of
this; the only thing worth flagging is that the test count keeps moving
as rounds add tests, which is expected, not a sign of drift.

*Single weakest remaining claim — updated by round 3.* Previously this
was "extraction logic is regex-based, unverified beyond Part 312's
conventions" (still true, see Generalization test above). Round 3's
attacker found something more precise and more load-bearing: the
COPPA-self-reference resolution (`is_coppa_self_reference`) has no real
antecedent tracking — it correctly resolves `"this Act"` in the shipped
text only because COPPA happens to be the most recently named Act at
that point in the sentence, not because the code tracks which Act "this
Act" actually refers to. A synthetic counter-example (a different Act
named immediately before a `"this Act"` reference) produces a wrong
resolution today. This is a real, confirmed gap in the newest feature,
not a hypothetical — a skeptic could reproduce it in under a minute by
feeding `extract_cross_references` a two-sentence string naming a
different Act first.

*Single most consequential design decision — reaffirmed under attack.*
Still the same one: extending USC resolution to COPPA self-references
rather than leaving all `named_act_section` refs unresolved. Round 3's
audit attacked this decision directly (finding the antecedent-tracking
gap above) and it survived in the form that matters: on the actual
shipped corpus, the resolution is correct, verified against the real
retrieved statute text, not merely plausible. The gap that was found is
a generalization risk for different/future text, honestly disclosed in
Limitations, not evidence the shipped data is wrong.

*What was actually run vs. never verified.* Run this session (round 3):
all 48 pytest tests; the full MCP-protocol end-to-end suite including 2
new worded-form-citation checks; a hand-written verification script
driving the real server via the actual `mcp` client SDK against all 15
of the attacker's exact collision cases plus 6 legitimate forms (all 15
passed) before the fix was trusted; `git status`/`git diff` reviewed
before every commit to avoid sweeping in subagent scratch files. Never
verified: the antecedent-tracking gap above was found and confirmed by a
subagent, not fixed (real antecedent tracking would need a materially
different parsing approach, out of scope for the remaining reserve
budget) — it's disclosed, not silently left for a reader to discover.

*With another 30 minutes.* Fix the antecedent-tracking gap in
`is_coppa_self_reference` (the single most consequential remaining gap
found this round, ahead of the non-`§` CFR cross-reference gap from
earlier, since it's in newer, less-hardened code and was demonstrated
with a working counter-example rather than only hypothesized) — likely
by tracking the most-recently-named Act as extraction scans through a
section's text in order, rather than a stateless per-match substring
check.

## Baseline comparison (from the reserve-phase audit, two rounds)

A fresh subagent, with no prior context of this build, built a genuinely
separate naive baseline for the strongest implicit complexity claim in
this repo — that the regex-based cross-reference extraction/resolution in
`scripts/build_corpus.py` (classification, range expansion, the
`find_sections_citing` index) is worth its complexity over a "does this
section-number string appear as a substring elsewhere?" check.

**Round 1** ran both against 3 targets (`312.4`, `312.5`, `312.2`) and
reported: identical results on 312.5/312.2, one genuine extra hit for the
real tool on 312.4 (via range expansion of `"§§ 312.2 through 312.8, and
312.10"`), and — based on that 3-target sample — no false positives found
for the naive approach.

**Round 2** (a fresh subagent, explicitly told to attack round 1's
validity rather than repeat it) ran the *same* comparison against **all
13 possible targets** instead of 3, and that changed the conclusion in
both directions:

- The range-expansion advantage generalizes: 4 of 13 targets (`312.3`,
  `312.4`, `312.6`, `312.7`) get a real extra hit from the shipped tool
  that the naive approach misses, not just the one round 1 happened to
  sample.
- But round 1's "no false positives" claim was an artifact of which 3
  targets it picked, not a real property of the naive approach: for
  target `312.1`, the naive substring check reports 3 sections
  (`312.4`, `312.5`, `312.11`) as citing it, and **all three are wrong**
  — `"312.1"` is a literal prefix of `"312.10"` and `"312.11"`, so the
  naive check is matching inside those longer numbers, not a real
  citation to §312.1. The real tool correctly reports zero citations to
  312.1 (confirmed by reading §312.1's actual text — a one-sentence scope
  statement nothing else references). Round 1's chosen targets (312.2,
  312.4, 312.5) happened to be exactly the ones in this corpus that
  aren't numeric prefixes of another section, so this failure mode was
  structurally invisible to a 3-target sample.

**Honest, corrected verdict**: the shipped regex-based approach earns its
complexity two ways on real data, not one — range expansion (recovers
real citations the naive check drops) *and* citation-boundary awareness
(avoids false positives from number-prefix collisions, e.g. 312.1 vs.
312.10/312.11, that a bare substring check produces). The original
round-1 conclusion ("only range expansion matters, no false-positive
benefit on this corpus") was itself a case of under-sampled verification
producing a too-generous read of the naive alternative — caught by
deliberately re-running the same comparison more completely rather than
trusting the first pass's coverage.

## Generalization test (does this work on a different CFR part?)

The Reflection above named "does the extraction logic generalize beyond
this one part?" as the weakest untested claim and the first thing worth
doing with more budget. Rather than leave that as a hypothesis, I ran it:
pointed `scripts/fetch_ecfr.py`/`scripts/build_corpus.py` at **16 CFR
Part 5 (Standards of Conduct)** - a different part of the same title,
chosen specifically because it has real subpart structure (`DIV6`
elements: Subparts A, B, C-D, E) that Part 312 doesn't, and a noticeably
different drafting style (heavy cross-referencing to a *different* CFR
title, 5 CFR, rather than to its own enabling statute). This was a
throwaway experiment against a git-clean tree, inspected, and then
reverted (`git checkout -- data/`) - **the shipped corpus is still only
16 CFR Part 312**; Part 5 was never adopted as a second corpus. It found:

- **Basic parsing generalizes fine.** All 21 real sections were extracted
  correctly, including one the parser had never seen before (`<CITA>`
  citation-history elements, e.g. `[58 FR 15764, Mar. 24, 1993, as
  amended...]`) - these are correctly excluded from paragraph text
  without crashing or requiring changes, since `parse_sections` only
  reads `HEAD`/`P` children of each section.
- **Definitions extraction correctly stayed silent** (0 terms) rather
  than producing false positives - Part 5 genuinely doesn't use the
  "Term means ..." convention (it's a conduct-standards part, not a
  definitions-heavy one), and the heuristic didn't hallucinate any.
- **Two real, confirmed generalization gaps**, previously only
  hypothesized:
  1. **Subpart identity is silently dropped.** `find_hierarchy_path`
     resolves the hierarchy once per *part*, not per section, so a
     section's membership in Subpart A vs. Subpart E of the same part is
     never captured anywhere in the corpus. This doesn't affect Part 312
     (it has no subparts), but would need fixing before shipping any part
     that does.
  2. **Cross-references without a `§` symbol are missed entirely, not
     even flagged as unresolved.** § 5.1's actual text cites "5 CFR part
     2635" and "5 CFR 5701" - real external cross-references - but
     `SECTION_REF_RE` requires a `§`/`§§` mark, so these are silently
     absent from `cross_references` rather than showing up as an
     `other_cfr_part` or similar entry a caller could at least see. Part
     312's own text happens to always use `§` for its cross-references
     (verified by re-reading the raw XML), so this gap is invisible in
     the shipped corpus but real and confirmed on genuine CFR text from
     the same title.

This is exactly the kind of finding the weakest-claim assessment
predicted rather than one that contradicts it: the core citation lookup,
hierarchy walk, and definitions heuristic hold up on unfamiliar real
text, but the cross-reference regex is confirmed - not just suspected -
to be narrower than "all CFR cross-references," specifically missing the
non-`§` citation style. Fixing it (a second regex for `\d+ CFR (?:part
)?\d+` phrasing) would be the concrete next step, not a vague "extend
coverage" gesture.

## Limitations (honest)

- **Scope**: 16 CFR Part 312 (13 sections) plus its own enabling statute,
  15 U.S.C. 6501-6506 (6 sections, companion corpus). Not the rest of
  Title 16, not other CFR titles, not the FTC Act or the APA that a
  couple of Part 312's sections also cite in passing (those stay
  genuinely unresolved - see the Companion U.S. Code corpus section
  above for why closing every cited statute wasn't attempted). Named-Act
  self-references to COPPA itself (e.g. "section 6502(a) of this Act")
  *are* resolved against the companion corpus, verified against the
  actual statute text rather than assumed; named-Act references to any
  *other* Act (e.g. "section 18... of the Federal Trade Commission Act")
  are not, and deliberately don't try to generalize past this one
  verified case (see How it solves cross-reference, above).
- **`is_coppa_self_reference` has no antecedent tracking**, confirmed by
  a reserve-phase audit: it treats any "this Act" match as COPPA
  unconditionally, rather than tracking which Act was actually most
  recently named. It happens to be correct on the real shipped text
  (COPPA is named before "this Act" appears in § 312.9), but that's a
  property of this specific sentence's order, not of the mechanism - a
  synthetic counter-example (a different named Act followed by "this
  Act") produces a wrong resolution. The same audit found
  `NAMED_ACT_RE` is case-sensitive (a lowercase "this act" is silently
  not extracted at all, not even as unresolved) and that named-Act range
  phrasing ("sections 6501 through 6506 of this Act") only captures the
  two endpoints, unlike the CFR-internal path's proper range expansion -
  neither is triggered by the real ingested text, both are latent gaps
  in the parsing approach rather than corrections to what's shipped.
- **The COPPA-self-reference gate is currently unexercised as a
  discriminator by this corpus's real data** - a baseline-builder
  subagent confirmed that removing `is_coppa_self_reference` entirely
  wouldn't change a single byte of `data/corpus.json`, because the one
  real non-COPPA named-Act reference in this text (the FTC Act's
  "section 18") never produces a candidate number in the first place
  (2 digits, below the 3-5 digit threshold). Its value was only
  demonstrated synthetically (a constructed counter-example where a
  different Act's in-range number would otherwise be wrongly resolved),
  not by any case actually present in the shipped corpus.
- **Cross-reference extraction is regex-based**, calibrated against the
  actual text of this one part, and is not a general CFR/USC citation
  parser. Confirmed by actually testing it (see Generalization test
  above) against a different, real part of the same title: it correctly
  parses unfamiliar text and doesn't hallucinate definitions where there
  are none, but it silently drops cross-references that don't use a `§`
  mark (e.g. "5 CFR part 2635"), and doesn't capture subpart-level
  hierarchy at all (only title/chapter/subchapter/part). Neither gap
  affects the shipped Part 312 corpus (which has no subparts and always
  cites with `§`), but both are real, confirmed limitations of the
  parsing approach, not hypothetical ones.
- **No point-in-time history**: the server holds one snapshot (as of the
  date it was built) plus a live staleness check, not a queryable history
  of amendments over time.
- **The companion U.S. Code corpus has no currency check.** Unlike
  `data/corpus.json`, there's no `check_currency`-style live re-check for
  `data/usc_corpus.json` - it's a one-time PDF extraction with no
  equivalent to eCFR's "latest issue date" endpoint used to verify it.
  It also carries PDF-extraction artifacts (see Companion U.S. Code
  corpus, above) that the eCFR-derived corpus doesn't have.
- **Environment note**: this machine's bash (Git Bash / Cygwin) fails to
  launch (`error while loading shared libraries: C: cannot open shared
  object file`) for reasons unrelated to this project, so the
  harness-provided `lib/retry.sh` could not be sourced or run. All
  network-fetch retry logic in `scripts/fetch_ecfr.py` reimplements the
  same retry-with-backoff contract directly in Python instead, and every
  shell command in this session was run through PowerShell.
