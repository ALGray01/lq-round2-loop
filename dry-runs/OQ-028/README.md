# Client "mini brain" MCP

An MCP server design + one working endpoint for a per-client, self-updating
context store ("mini brain") built from emails, notes, and prior-matter
documents, queryable by a lawyer's agent during work and optionally
surfaceable to the client themselves.

This answers OQ-028. It ships:

- A concrete data model (`schema/schema.sql`, SQLite).
- The MCP tool contract (`schema/query_client_brain.tool.json`).
- A working, executable endpoint: `query_client_brain`, exposed over a real
  MCP-style JSON-RPC stdio server (`server.py`), backed by `brain.py`.
- Seed data (`seed.py`) that deliberately encodes an adversarial scenario
  (two clients suing each other, a lawyer wrongly staffed on both) so the
  isolation logic can be checked, not just asserted.
- An executed test suite (`test_server.py`) that calls the real server
  subprocess, including true-negative cases.

## Quick start

```
python seed.py --db mini_brain.db     # builds and populates the DB
python test_server.py                  # runs the executed test suite (uses its own test DB)

# Manual MCP session:
python server.py --db mini_brain.db
# then paste, one JSON object per line, e.g.:
# {"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
# {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
# {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"query_client_brain","arguments":{"requester_user_id":"user-priya","client_id":"client-acme","query":"settlement"}}}
```

Requires only Python 3 stdlib (`sqlite3`, `json`, `argparse`) — no network
install needed, so there's nothing for the retry-wrapped installer in
`lib/retry.sh` to do here.

## Design

### What gets ingested vs. left out

**Ingested**, per client, tagged to that client's mini-brain:
- Email correspondence on the matter (client, opposing counsel, court,
  third parties), captured via the firm's mail/DMS integration and tagged
  to a matter at ingestion time.
- Internal notes, memos, call notes, strategy notes.
- Prior-matter documents for that same client: filings, contracts,
  correspondence, closed-matter history.

**Deliberately left out** (see `documents.excluded` in the schema, which
keeps the exclusion decision itself auditable rather than silently dropping
rows):
- Personal/non-matter correspondence swept up by a mailbox sync filter
  (`doc-3` in the seed data is exactly this case — a "dinner plans" email
  that got ingested by an over-broad filter and is explicitly excluded with
  a reason, not deleted).
- Third-party confidential material received under an NDA that doesn't
  cover this client relationship.
- Discovery material from an adverse party, obtained under a protective
  order — this is a firm-wide ethical-wall issue (see below), not something
  the mini-brain repackages as "context."
- Anything privileged to a *different* client (structurally impossible here
  anyway, since ingestion is scoped by `client_id` at write time, not
  filtered afterward).
- Raw sensitive PII (SSNs, full financial account numbers) beyond what's
  needed for the matter — production ingestion would redact these before
  they ever reach `documents.body`; this prototype does not implement
  redaction (see Limitations).

Ingestion is scoped by `client_id` *before* anything reaches the store, not
by post-hoc filtering — the strongest guarantee against cross-client leakage
is "it was never in this client's table in the first place."

### Permission model: lawyer-only vs. lawyer-and-client

Two layers, both enforced by `query_client_brain` (see `brain.py`), not left
to the caller's honesty:

1. **Client-level gate** (`client_access` table): a user has *no* access to
   a client's brain unless there is an active (`revoked_at IS NULL`) grant
   row for that exact `(client_id, user_id)` pair. Being a firm employee, or
   even a lawyer generally, grants nothing by itself — access is opt-in per
   engagement. Revoking access is a single `UPDATE ... SET revoked_at = ...`,
   not a data-deletion exercise.

2. **Document-level visibility** (`documents.visibility`): every document is
   tagged `lawyer_only` or `lawyer_and_client` at ingestion/authoring time.
   When the requester's role (`users.role`) is `client`, the query is
   restricted to `lawyer_and_client` documents only — internal strategy
   notes, settlement floors, and privileged analysis never reach the client
   portal even though the client has a legitimate grant to query *something*
   about their own matter. See `doc-1` vs. `doc-2` in the seed data and the
   corresponding test cases.

The two layers answer different questions: "can this person query this
client's brain at all" vs. "which of that client's documents is it safe to
show *this specific* requester."

### Refresh cadence

`ingestion_log` models a two-speed pipeline:
- **Event-driven, near-real-time**: new emails tagged to a matter, new notes
  saved, new filings docketed — ingested within minutes via a webhook/queue
  from the mail system and DMS, each write logged as one `ingestion_log` row
  per source per run.
- **Nightly reconciliation sweep**: a full per-client pass that catches
  anything the event stream missed (delayed webhook, backfilled document)
  and re-checks exclusion rules against the current policy (e.g. if a
  redaction rule changes, it's reapplied retroactively, not just to new
  documents).
- **On-demand**: a lawyer can trigger an immediate re-index for their client
  before a hearing or closing, rather than waiting for the nightly sweep.

`ingestion_log.status` (`ok` / `partial` / `failed`) makes silent ingestion
failure visible and queryable, rather than a mini-brain that quietly goes
stale with no signal.

### Conflict-of-interest isolation

This is the part most worth attacking, so it's enforced twice:

1. **Structural**: `client_access` grants are per-client. A lawyer who was
   never staffed on a matter simply has no row, so they can't query it —
   this is the normal case and needs no special logic.
2. **Defense-in-depth, at query time**: `brain.py`'s
   `query_client_brain` doesn't stop at "does a grant row exist." It also
   checks the `conflicts` table (symmetric client-pairs recorded as
   adverse — e.g. active litigation between them) against every *other*
   client the requester currently holds an active grant to. If the
   requester holds simultaneous active access to two clients recorded as
   adverse, the query is **denied even though a grant row technically
   exists** — because a grant existing is exactly the failure mode a
   mis-issued grant produces, and the ACL table alone can't catch its own
   mistake.

The seed data encodes this directly: `user-sam` has active grants to both
`client-acme` and `client-beta`, who are recorded as adverse
(`Acme v. Beta Industries` litigation) in the `conflicts` table. Querying
either client's brain as Sam is denied with `conflict_wall`, and this is
exercised by an executed test (`test_server.py`), not just asserted in
prose — see "Verification" below, including a check that the test *fails*
when this logic is sabotaged.

In a real deployment, a genuine conflict (not a mis-issued grant) would be
resolved before any grant is created — via the firm's conflict-check
process at intake — and an *ethical screen* would be modeled as simply never
issuing the grant, or explicitly revoking it. The runtime check here is a
backstop against human/process error in issuing that grant, not a
replacement for the intake-time conflict check.

### Interaction with firm-wide knowledge

Firm-wide knowledge (practice-group know-how, standard clause libraries,
mediation playbooks — see `doc-5` in the seed data) lives in the *same*
`documents` table but with `client_id = NULL` and
`source_type = 'firm_wide_kb'`. It is:

- **Never client-confidential by construction** — nothing with a real
  `client_id` can be reclassified as firm-wide; the two are structurally
  disjoint in the schema, not merely tagged differently.
- **Addressable independent of any `client_access` grant** — no client
  relationship is required to search it, since it's not client data.
- **Returned in a separate array** (`firm_wide_results`, distinct from
  `client_results`) in every response, so a caller (or the lawyer's agent
  reading the tool output) can never conflate "the firm's generic mediation
  playbook" with "this specific client's confidential settlement floor,"
  even when both match the same query. This is the one place the design
  actively resists a tempting simplification (just merge everything into
  one ranked list) because blending them silently is exactly how a firm's
  general know-how ends up looking, to a careless reader, like something
  specific to the client at hand.

### Schema

See `schema/schema.sql` for full DDL and inline rationale comments. Summary:

```
conflict_groups --< clients >-- conflicts (self-referencing, symmetric)
clients --< matters
clients --< client_access >-- users
clients --< documents >-- matters (nullable; client_id NULL = firm-wide)
                          ingestion_log (per client, per source, per run)
(every query) --> audit_log (allowed/denied, reason, result_count)
```

### The one working endpoint

`query_client_brain(requester_user_id, client_id, query, include_firm_wide=true, max_results=10)`
→ `{allowed, denial_reason, client_results[], firm_wide_results[]}`

Full contract: `schema/query_client_brain.tool.json`. Implementation:
`brain.py` (pure logic, testable by direct import) wired into an actual
MCP-style stdio JSON-RPC server in `server.py` (`initialize`, `tools/list`,
`tools/call`). Every call — allowed or denied — is written to `audit_log`.

## Verification

`test_server.py` spawns the real `server.py` subprocess and drives it over
stdin/stdout with actual JSON-RPC requests — it does not call `brain.py`
functions directly, so it also exercises the transport layer. It was run
and produced:

```
All checks passed.
```

(26/26 — see the file for the full list: protocol handshake, tool
discovery, a staffed lawyer's happy path, an unknown user, an un-staffed
lawyer, the conflict-wall denial in *both* directions at both the literal
client and conflict-group level, the client-visibility filter in both
directions, the hard-exclusion path, a check that a firm-wide/other-client
search never leaks another client's document, and a crafted-input block per
FAILURE-CLASSES.md item 5: a missing required argument, an invalid
`max_results` in three ways (wrong type, below minimum, above maximum), an
unknown tool name, a SQL-metacharacter-laden query string checked against
actual table survival afterward, and a malformed JSON line followed by a
well-formed one in the same session.)

Per this project's own failure-class checklist (`FAILURE-CLASSES.md`,
item 4 — "a grader/scorer that could be wrong in its own favor"), the
conflict-wall check in `brain.py` was deliberately disabled and the test
suite re-run: it caught both conflict-wall test cases and exited non-zero,
then the sabotage was reverted and the suite re-run clean. This is what
makes "all checks passed" mean something rather than being a test suite
that would pass regardless of whether the isolation logic actually worked.

### Adversarial audit (fresh subagent, no prior context of this session)

A fresh subagent was dispatched to audit this repository cold against
FAILURE-CLASSES.md, scoped away from the harness scaffolding. It found two
real bugs, both since fixed and re-verified:

1. **Conflict wall only matched literal `client_id`, not `conflict_group_id`.**
   The schema and this README always described the conflict check as
   group-aware (parent/subsidiary clustering), but `brain.py`'s query-time
   check only compared the exact client ids in the `conflicts` table — a
   lawyer staffed on an adverse client's same-group sibling (not itself
   named in `conflicts`) slipped through. Fixed by expanding both sides of
   the check to full conflict-group membership (`_group_members` in
   `brain.py`). Reproduced with a new seed scenario
   (`client-acme-sub`/`user-alex`) and covered by two new tests; both were
   confirmed to fail against the pre-fix code and pass against the fix.
2. **An invalid `max_results` (wrong type or out-of-range) crashed the
   entire server process** with an uncaught `TypeError`, instead of
   returning a clean JSON-RPC error — a one-field denial-of-service from any
   caller. Fixed by validating `max_results` in `brain.py` and mapping the
   resulting `ValueError` to a `-32602` JSON-RPC error in `server.py`.
   Covered by three new tests (string, below-min, above-max), each
   confirmed to crash the pre-fix server and pass cleanly post-fix.

The audit found nothing else after genuinely attempting to break the
permission/visibility filtering, case-sensitivity of ids, revoked-grant
handling, and injection-style inputs.

A second fresh-subagent audit round was run against the fixed code
specifically to re-attack both fixes rather than trust them, plus new edge
cases (a self-referential conflict row, a conflict_group with no other
members, a dangling `conflict_group_id` after its `conflict_groups` row was
deleted, `revoked_at` set to `''` instead of `NULL`, `max_results` as a bool
or float). It found nothing further. The most valuable edge cases it had
tried ad hoc (and then thrown away) were formalized into permanent
regression tests in `test_server.py`: a lawyer legitimately staffed on two
same-group siblings that are *not* adverse to each other must stay allowed
(guards against the group-level fix over-correcting into "any shared group
is disqualifying"), a `revoked_at=''` grant must be treated as revoked, and
a bool `max_results` must be rejected like any other wrong type. Each new
test was itself mutation-tested (temporarily broken, confirmed to fail,
reverted, confirmed to pass) before being trusted — see the two sabotage/
revert cycles run during this pass, same method as the original conflict-
wall mutation test above. 30/30 checks pass on the current committed
state.

## Limitations (honest)

- **Retrieval is substring matching, not semantic search.** Production would
  embed documents at ingestion time and do vector similarity search; this
  prototype has no network/model access available to it, so it uses a
  case-insensitive substring match over title+body. This is a real
  functional gap (a query for "payment dispute" won't match a document that
  only says "invoice disagreement"), not just a cosmetic simplification —
  flagged here rather than glossed over.
- **No ingestion connectors.** `seed.py` populates the schema directly;
  there's no actual email/DMS/calendar integration. The schema and
  `ingestion_log` model what a real pipeline would write, but nothing here
  parses a real mailbox.
- **No redaction pipeline.** PII/privilege redaction on ingested text is
  described as a design requirement but not implemented; `documents.body`
  stores raw text as seeded.
- **Authentication is out of scope.** `requester_user_id` is trusted as
  given — a real deployment sits this endpoint behind the firm's SSO/auth
  layer, which authenticates the caller *before* this code ever sees a
  `user_id`, not inside this tool.
- **Conflict data entry is manual here.** `conflicts` rows are seeded by
  hand; a real system would populate this from the firm's conflict-check /
  intake system, and this endpoint's runtime check is a backstop against
  *that* system's mistakes, not a substitute for it.
- **Single-firm, single-database assumption.** No multi-tenancy, no
  encryption-at-rest configuration, no backup/retention policy — all
  out of scope for "ship the schema and one working endpoint."

## Reflection

**Weakest remaining claim.** `server.py` implements a hand-rolled subset of
the MCP JSON-RPC surface (`initialize`, `tools/list`, `tools/call`) and
every check in this repo verifies it by feeding raw JSON-RPC over
stdin/stdout with `subprocess.run` — never by connecting an actual MCP
client library or host (the official `mcp` Python SDK's client, Claude
Desktop, etc.). So "this is an MCP server" is true of the message shapes I
implemented, but unverified against a real client's handshake sequence,
capability negotiation, or error-framing expectations beyond the three
methods I chose to implement. Someone could catch this in under five
minutes by pointing `pip install mcp`'s client, or any MCP-compatible host,
at `python server.py --db mini_brain.db` and seeing whether the handshake
actually completes — I never did this, and it's the single most likely
place a real integration would surface a gap this test suite can't see.

**Most consequential design decision.** Enforcing the conflict wall a
second time at query time (`_group_members` + the `conflicts` table scan in
`brain.py`), instead of treating conflict-of-interest isolation as solved
entirely by the firm's intake-time conflict check plus a correctly-issued
`client_access` grant. The alternative — trust the ACL, no runtime
re-check — is less code, no full-table scan of `conflicts` per query, and
is how a lot of real access-control systems are built ("the grant table is
the source of truth"). I rejected it because the premise the seed data
encodes (`user-sam`, `user-alex`: mis-issued grants to two adverse clients)
is a realistic failure mode, not a hypothetical, and an adversarial audit
proved the runtime check earns its cost: round 1 found it was checking
literal `client_id` instead of `conflict_group_id` and missed a same-group
sibling entirely. A grant-only design would have had no second layer to
catch that gap at all — it would have simply been a bug in the ACL story
with nothing to contradict it. The cost I accepted: `brain.py` now does an
unindexed full scan of `conflicts` per query, which is fine at this scale
and wrong at firm scale — noted, not fixed, since fixing it (e.g. an
indexed junction table of resolved adverse-client-pairs, precomputed at
conflict-entry time) was a reasonable scope cut given the budget remaining.

**What was actually verified vs. not.** Verified by execution: `python
seed.py` and `python test_server.py` (30/30, twice, on the current
committed state — not just once early on); a manual JSON-RPC session
against `server.py` piped through PowerShell reproducing the README's
copy-pasteable example; two rounds of fresh-subagent adversarial audit,
each of which ran its own throwaway scripts against the real code rather
than reading it; and, for every fix made in response to those audits
(the group-level conflict check, the `max_results` validation, and each of
the three new regression tests added afterward), a deliberate
sabotage-then-revert cycle confirming the relevant test actually fails
before the fix and passes after — not just that it passes once. Not
verified: connecting a real MCP client (see above); any test with more than
five documents or documents longer than a paragraph (recall/precision of
the substring-match retrieval at realistic corpus size is unknown); and the
`conflicts` full-table-scan's behavior at a scale beyond a handful of rows.

**Next 30 minutes.** Wire up the official `mcp` Python SDK's client (or a
minimal hand-written one using a real MCP client library rather than raw
JSON-RPC) against `server.py` and confirm the handshake and a `tools/call`
round-trip actually succeed end-to-end. That's the highest-value next step
because it's the gap most likely to be wrong in a way none of the existing
30 tests could catch — they all talk to `server.py` the same way I built
it, which is exactly the blind spot a real client would expose.
