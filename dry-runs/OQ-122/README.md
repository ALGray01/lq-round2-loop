# OQ-122 — MCP-accessible statutes-and-regulations source

An MCP server over a real slice of federal regulatory law: **21 CFR Part 11**
(Electronic Records; Electronic Signatures) plus **21 CFR Part 1 Subpart J**
(Establishment, Maintenance, and Availability of Records). Both are ingested
from the live [eCFR API](https://www.ecfr.gov/api) — the official,
continuously-updated electronic Code of Federal Regulations published by
GPO/NARA — not scraped HTML, not a static text dump.

## Why this corpus

The brief asks to solve currency, hierarchy, and cross-reference honestly for
one real slice of law, not to boil the ocean. 21 CFR Part 11 was chosen
because:

- It's real, actively-used primary law (FDA electronic records/signatures
  rule — relevant to every regulated life-sciences company).
- It's small enough to ingest, verify, and reason about by hand within the
  time available (10 sections), while still having genuine internal
  structure (Title → Part → Subpart → Section) and genuine cross-references,
  both to other sections in the same part and to *other* parts of the CFR.
- Part 11 §11.1(f) cross-references "§§ 1.326 through 1.368 of this chapter"
  and "part 1, subpart J of this chapter" repeatedly. **Part 1 Subpart J is
  ingested alongside Part 11 specifically so some of those cross-references
  actually resolve** within the corpus, instead of every single reference
  coming back "external, unverified" — which would be closer to papering
  over the cross-reference problem than solving it. The corpus therefore has
  a realistic mix: some citations resolve, most (to parts like 117, 507, 112,
  121, and to US Code sections) honestly don't, because they're out of the
  ingested scope.

This is not a claim that Part 11 is *the* important gap in affordable legal
data access — it's a deliberately small, real, verifiable slice chosen to
demonstrate the mechanism end-to-end rather than a plan to eventually scrape
all of Title 21.

## Architecture

```
src/ingest.py     -- fetches from the live eCFR API, parses hierarchy/text/
                     cross-references, writes data/corpus.db
src/server.py     -- MCP server (stdio) reading data/corpus.db
src/test_server.py -- real end-to-end test: launches server.py as a
                     subprocess, connects a real MCP client, calls every
                     tool including negative/edge cases
data/corpus.db    -- the ingested snapshot (SQLite), committed so the
                     server runs immediately without needing network access
```

### How currency is handled

Every ingestion run records, alongside the text:
- `ingested_at_utc` — when this snapshot was built
- `ecfr_latest_amended_on` / `ecfr_up_to_date_as_of` — the eCFR API's own
  metadata about how current *its* copy of Title 21 was at ingestion time
- per-section `last_amended` — the most recent substantive amendment date
  for that specific section, from eCFR's `/versioner/v1/versions` endpoint

The `check_currency` MCP tool calls the **live** eCFR API right now and
compares its current `latest_amended_on` for Title 21 against what's stored
in the snapshot. If they differ, it says so and tells you to re-run
`ingest.py` — it does not claim the snapshot is current just because it once
was. The `stale: true` path (not just the happy path) is covered by a
permanent, automated assertion in `test_server.py`: the test mutates
`data/corpus.db`'s stored date to `1999-01-01` mid-session, confirms the
already-running server picks it up and reports `stale: true` against the
live date, then restores the original value and confirms it reads as
current again. An earlier draft of this README claimed this was verified
"via test_server.py" while the corrupt/restore check actually only existed
as a manual, uncommitted step during development — a second audit pass
caught that gap between the claim and what was actually committed, so the
test above was added for real rather than the wording being softened.

**Limitation:** currency is checked at the whole-title granularity against
the live API (that's what eCFR's summary endpoint exposes cheaply); it does
not re-diff every section's live text on every check. A `stale: true` result
means "something in Title 21 changed since ingestion, re-ingest to be safe,"
not "this specific section changed."

### How hierarchy is handled

The `nodes` table stores every Part/Subpart/Section (and eCFR's occasional
"subject group" grouping layer, e.g. under Part 1 Subpart J) with its parent
citation, taken directly from eCFR's own `hierarchy_metadata` on each XML
element — not re-derived or guessed from citation string parsing. The
`list_hierarchy` tool walks this tree.

### How cross-references are handled

`ingest.py` regex-extracts three kinds of citation from each section's text:
1. Section references (`§ 11.2`, `§§ 1.326 through 1.368`)
2. Other-CFR-part references, in either word order the eCFR text actually
   uses (`part 117 of this chapter`, `part 1, subpart J of this chapter`,
   *and* `subpart L of part 1 of this chapter` — §11.1 alone uses both
   orders across its subsections; an audit pass caught the reverse-order
   phrasing collapsing into a bare, subpart-less "Part 1" match, which has
   since been fixed and reverified against the live-fetched text)
3. U.S. Code statute references (`21 U.S.C. 321-393`)

Every extracted citation is tagged `resolved: true` only if the target is
actually present in the ingested corpus, `resolved: false` otherwise. The
server never silently drops or fabricates a resolution — an unresolved
citation is reported as exactly that, with the raw text and the target it
couldn't verify, so a caller knows to go look it up elsewhere rather than
being told (wrongly) that the reference was checked.

**Self-references are deliberately excluded, not just resolved.** Some
sections cite their own paragraphs by full section number (e.g. 21 CFR
1.352(e) says "the information in § 1.352(a), (b), (c), or (d)" while
inside § 1.352 itself). These are real text, correctly matched by the
regex, but excluded from the citation graph entirely (`ingest.py`'s
`extract_citations`, the `target == section_citation` check) because they
aren't a cross-reference to *another* provision — showing a section as its
own `cited_by` would be noise, not signal, for a tool whose purpose is
mapping relationships between provisions. This was tightened during a
second audit pass after an earlier fix (below) only handled a different
root cause of the same "cites itself" symptom.

An earlier version of the extractor also picked up a distinct, unrelated
bug: each section's own HEAD text (e.g. "§ 11.1 Scope.") was included in
the text scanned for citations, so *every* section spuriously "cited
itself" via its own heading. That was a parsing artifact (fixed by
excluding `HEAD` from the text passed to the extractor), separate from the
genuine-body-text self-reference case above, which required a second,
explicit exclusion rule once the heading bug was fixed and the residual
case surfaced.

**Known limitations of the extractor** (regex-based, not a full legal
citation parser):
- "Through" ranges are expanded only for `X.Y through X.Z` (via the two
  endpoints); it does not enumerate or verify every section in between.
- It cannot distinguish a citation appearing in narrative text from one in a
  parenthetical aside — both are extracted the same way.
- It only extracts citation *patterns*; it does not resolve pinpoint
  paragraph-level cites (e.g. `§ 11.10(a)`) — the resolved/unresolved
  granularity is at the section level.

## MCP tools

| Tool | Purpose |
|---|---|
| `get_by_citation(citation)` | Retrieval by citation — accepts `11.10`, `21 CFR 11.10`, `21 CFR Part 1 Subpart J`, etc. Returns full text, hierarchy position, last-amended date, source URL. Returns `found: false` with an honest reason if out of corpus scope. |
| `get_cross_references(citation)` | Structured query over the citation graph: outbound (what this section cites, resolved/unresolved) and inbound (what in-corpus sections cite this one). |
| `list_hierarchy(parent_citation)` | Structured query over the Part → Subpart → Section tree; empty string lists top-level parts. |
| `search_text(query, limit)` | Full-text search (SQLite FTS5) over section headings/text, per-word prefix matching (`biometric` matches `Biometrics`), ranked results with a highlighted snippet. Query terms are extracted as `\w+` words and individually quoted before being placed in the FTS5 MATCH expression, so FTS query-syntax injection (`OR`, column filters, `"..."`) degrades to a harmless literal search rather than an unintended boolean query — verified in `test_server.py`. |
| `check_currency()` | Live freshness check against the eCFR API (see above). |

## Running it

```bash
pip install -r requirements.txt

# (optional) refresh the snapshot from the live eCFR API
python src/ingest.py

# run the MCP server (stdio transport)
python src/server.py

# run the real end-to-end test (spawns the server, connects a real
# MCP client, calls every tool, including negative/stale-state cases)
python src/test_server.py
```

To wire this into an MCP-aware client (Claude Desktop, etc.), add a stdio
server entry pointing at this script, e.g. in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cfr-statutes": {
      "command": "python",
      "args": ["/absolute/path/to/OQ-122/src/server.py"]
    }
  }
}
```

### Example session (real captured output)

Output below was generated by directly calling the tool functions against
the current committed `data/corpus.db` immediately before this commit (not
edited or hand-assembled afterward). `cites` for §11.1 is long (11.1 has
more cross-references than any other ingested section) and is truncated
here with an explicit `... (N more)` marker rather than silently cut:

```
> search_text(query="biometric")
{
  "query": "biometric",
  "results": [
    {"citation": "21 CFR 11.200", "heading": "§ 11.200 Electronic signature components and controls.",
     "snippet": "(a) Electronic signatures that are not based upon >>biometrics<< shall:\n(1) Employ..."},
    {"citation": "21 CFR 11.3", "heading": "§ 11.3 Definitions.",
     "snippet": "...321-393)).\n(2) Agency means the Food and Drug Administration.\n(3) >>Biometrics<<..."}
  ]
}

> get_cross_references(citation="21 CFR 11.1")
{
  "found": true,
  "citation": "21 CFR 11.1",
  "cites": [
    {"raw_text": "§ 11.2", "target_type": "section", "target_citation": "21 CFR 11.2", "resolved": 1},
    {"raw_text": "§§ 1.326 through 1.368", "target_type": "section", "target_citation": "21 CFR 1.326", "resolved": 1},
    {"raw_text": "§§ 1.326 through 1.368", "target_type": "section", "target_citation": "21 CFR 1.368", "resolved": 1},
    {"raw_text": "§ 101.11", "target_type": "section", "target_citation": "21 CFR 101.11", "resolved": 0},
    {"raw_text": "§ 101.8", "target_type": "section", "target_citation": "21 CFR 101.8", "resolved": 0},
    {"raw_text": "subpart L of part 1 of this chapter", "target_type": "cfr_part",
     "target_citation": "21 CFR Part 1 Subpart L", "resolved": 0},
    ... (10 more: subparts M/O/R of Part 1, and Parts 117/507/112/121, each cited twice, all resolved: 0) ...
    {"raw_text": "part 1, subpart J of this chapter", "target_type": "cfr_part",
     "target_citation": "21 CFR Part 1 Subpart J", "resolved": 1}
  ],
  "cited_by": []
}
```

Note `cited_by` is empty here because nothing in this two-part corpus cites
*11.1 specifically* back (11.1 is cited by nothing else, only cites out).
For a section that genuinely has resolvable inbound citations, see
`21 CFR 1.326` in `test_server.py` (11.1's own citation range resolves back
to it).

Malformed input at the MCP/JSON-RPC layer (wrong argument type, missing
required field, unknown tool name) was also tested directly against a live
server via a real client, not assumed safe: FastMCP's pydantic-based
validation rejects each with a structured `isError: true` response and a
specific message (e.g. `"Input should be a valid integer, unable to parse
string as an integer"` for a non-numeric `limit`) rather than crashing the
process or returning a misleading result.

## Honest limitations / what's not solved here

- **Scope**: two slices of one CFR title (23 sections total), not all of
  Title 21, and nowhere near all of the CFR. This is a demonstrated
  mechanism, not a completed corpus. Extending to more parts is
  mechanical — add entries to `CORPUS_SLICES` in `ingest.py` — but each
  addition should be re-checked for how many of its cross-references
  actually resolve, and the regex extractor re-validated against that
  part's citation phrasing (FDA parts are fairly uniform; other titles may
  use different conventions).
- **Cross-reference extraction is regex-based**, not a real citation parser
  (no NLP model, no formal grammar for CFR citations). It was validated
  against the actual text of the ingested sections (see test assertions),
  not against a hand-built synthetic example designed to pass.
- **`search_text` is whole-word prefix matching, not semantic search** — it
  will not find "signature" from a query for "sign-off," and it ranks by
  FTS5's built-in bm25-style relevance, not by legal importance.
- **`check_currency` needs network access** to do a live check; without it,
  it falls back to reporting only the snapshot's own recorded date rather
  than silently claiming freshness (see the `except` branch in
  `check_currency`).
- Not legal advice; this is a data-access mechanism, not a substitute for
  reading the authoritative eCFR text linked in each response.

## Reflection

**Weakest remaining claim.** `get_cross_references`'s `cited_by` field is a
lower bound, not a verified absence, and this isn't fully spelled out
elsewhere. It only reflects citations found by regex-scanning the 23
sections actually ingested. If some *other* CFR part outside this corpus
(say, 21 CFR Part 211, never ingested) cites into `21 CFR 11.10`, this
server has no way to know and `cited_by` for `11.10` will simply omit it —
not report it as unresolved, just silently not have it, because inbound
citations are keyed off of what the ingested sections themselves say, not
off a real citator index. Someone could catch this by grep-ing the full
eCFR text for `"part 11"` outside Title 21's Part 11 itself and finding
citing sections this server never surfaces as `cited_by`.

**Most consequential design decision.** Ingesting exactly two related CFR
slices (Part 11 + Part 1 Subpart J) instead of one large part (e.g. all of
Part 117, which Part 11 actually cites) or all of Title 21. The rejected
alternative — going broad — would have produced more raw coverage but left
less time to verify the mechanics per the brief's actual ask (currency,
hierarchy, cross-reference, *done honestly*): three adversarial audit
passes this session found and fixed four real bugs even in this small,
two-part corpus (a regex word-order gap, a heading-leak self-citation
artifact, a genuine-but-noisy self-reference case, and an unbacked
verification claim in an earlier README draft). A broader corpus ingested
in the same time budget would almost certainly have carried more
undiscovered bugs of the same kind, just spread thinner and less
scrutinized — depth over breadth, deliberately.

**What was actually verified vs. not.** Verified by running real commands,
this session: `ingest.py` against the live eCFR API (repeatedly,
reproducing byte-identical section/citation counts); the full
`test_server.py` suite via a real MCP stdio client (not a mock), including
adversarial inputs (SQL injection, path traversal, FTS5-syntax injection,
malformed MCP-layer arguments, an unknown tool name) and a forced-stale
`check_currency` path with a genuine restore step; `source_url` links via
direct `curl` (all returned live HTTP 200s); that only `check_currency`
touches the network (`grep -n urllib src/server.py`). **Never verified:**
behavior under a corpus larger than 23 sections (FTS ranking, hierarchy
queries, and citation-graph joins are untested at scale); concurrent access
from multiple simultaneous MCP clients against the same SQLite file;
whether an actual GUI MCP client (Claude Desktop or similar) loads and
displays this server correctly — only the low-level `mcp` Python SDK's
`ClientSession` was exercised, not a real client application; and whether
the regex extractor's patterns generalize to a differently-drafted CFR
title's citation phrasing (untested outside Title 21).

**With another 30 minutes**, the first thing to do would be ingesting one
more real, moderately-sized part that Part 11 already cites but that isn't
currently resolved (a meaningful slice of Part 117, say) — not for
coverage's own sake, but because it's the single best test of whether the
regex extractor (built by eyeballing only two parts' phrasing conventions)
actually generalizes, which is the biggest untested assumption behind the
"cross-reference problem solved honestly" claim. Converting more
`resolved: false` results into either genuinely-resolved or
confirmed-still-external, on a part drafted independently of the two
already ingested, would be a stronger test than anything performance- or
UI-related, given this submission is about the correctness of the
citation/hierarchy/currency mechanism specifically.
