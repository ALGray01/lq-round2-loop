-- Client "mini brain" MCP data model
-- SQLite. See README.md for the design rationale behind each table.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Identity & conflict-of-interest structure
-- ---------------------------------------------------------------------------

-- A conflict_group clusters entities that must be treated as "the same side"
-- for conflict-check purposes (e.g. a parent company and its subsidiaries,
-- or spouses in a joint matter). Two clients in the same conflict_group are
-- allied; the `conflicts` table below records when two clients/groups are
-- adverse to one another.
CREATE TABLE conflict_groups (
    conflict_group_id   TEXT PRIMARY KEY,
    label               TEXT NOT NULL
);

CREATE TABLE clients (
    client_id           TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    conflict_group_id   TEXT REFERENCES conflict_groups(conflict_group_id),
    status              TEXT NOT NULL CHECK (status IN ('prospective','active','former')),
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Explicit, symmetric record of which clients (or their conflict groups) are
-- adverse to one another. This is the source of truth the endpoint checks
-- at query time -- it does NOT rely solely on who happens to hold an access
-- grant, because grants can be mis-issued. Store both directions is not
-- required; the query layer checks both (a,b) and (b,a).
CREATE TABLE conflicts (
    client_id_a         TEXT NOT NULL REFERENCES clients(client_id),
    client_id_b         TEXT NOT NULL REFERENCES clients(client_id),
    reason              TEXT NOT NULL,
    recorded_at         TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (client_id_a, client_id_b)
);

CREATE TABLE users (
    user_id             TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    -- 'lawyer' | 'paralegal' | 'client' | 'admin'
    -- Role here is the user's firm-wide role; per-client relationship and
    -- visibility entitlement is governed by client_access below.
    role                TEXT NOT NULL CHECK (role IN ('lawyer','paralegal','client','admin')),
    email               TEXT
);

-- Per-client access grants. No row => no access, full stop. This is how a
-- lawyer who is walled off from a matter (conflict, ethical screen, simply
-- never staffed on it) is kept out: access is opt-in and explicit, not
-- inherited from being a firm employee.
CREATE TABLE client_access (
    client_id           TEXT NOT NULL REFERENCES clients(client_id),
    user_id             TEXT NOT NULL REFERENCES users(user_id),
    -- 'responsible_lawyer' | 'team_lawyer' | 'client_portal_user' | 'admin'
    access_role         TEXT NOT NULL CHECK (
        access_role IN ('responsible_lawyer','team_lawyer','client_portal_user','admin')
    ),
    granted_at          TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at          TEXT,
    PRIMARY KEY (client_id, user_id)
);

-- ---------------------------------------------------------------------------
-- Matters & content
-- ---------------------------------------------------------------------------

CREATE TABLE matters (
    matter_id           TEXT PRIMARY KEY,
    client_id           TEXT NOT NULL REFERENCES clients(client_id),
    title               TEXT NOT NULL,
    opened_at           TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at           TEXT,
    status              TEXT NOT NULL CHECK (status IN ('open','closed'))
);

-- The ingested corpus. client_id IS NULL is reserved for firm-wide knowledge
-- (see source_type='firm_wide_kb') which is never client-confidential and is
-- addressable independent of any client_access grant.
CREATE TABLE documents (
    doc_id              TEXT PRIMARY KEY,
    client_id           TEXT REFERENCES clients(client_id),
    matter_id           TEXT REFERENCES matters(matter_id),
    -- 'email' | 'note' | 'filing' | 'contract' | 'memo' | 'firm_wide_kb'
    source_type         TEXT NOT NULL CHECK (
        source_type IN ('email','note','filing','contract','memo','firm_wide_kb')
    ),
    title               TEXT NOT NULL,
    body                TEXT NOT NULL,
    -- 'lawyer_only'      : never shown to a client_portal_user
    -- 'lawyer_and_client': safe to surface to the client themselves
    visibility          TEXT NOT NULL CHECK (visibility IN ('lawyer_only','lawyer_and_client')),
    -- Hard exclusion: content that was ingested (or considered for ingestion)
    -- but must never be retrievable, regardless of requester or role. Kept
    -- as a row (not deleted) so the exclusion decision is itself auditable.
    excluded            INTEGER NOT NULL DEFAULT 0,
    exclusion_reason    TEXT,
    source_ref          TEXT,          -- e.g. original email message-id / DMS doc id
    ingested_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_documents_client ON documents(client_id);

-- ---------------------------------------------------------------------------
-- Operational logs
-- ---------------------------------------------------------------------------

-- One row per ingestion sweep, per client, per source. Drives the "refresh
-- cadence" story: near-real-time event-driven ingestion for email/notes,
-- reconciled by a nightly full sweep per client.
CREATE TABLE ingestion_log (
    log_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id           TEXT REFERENCES clients(client_id),
    source_type         TEXT NOT NULL,
    run_at              TEXT NOT NULL DEFAULT (datetime('now')),
    documents_added     INTEGER NOT NULL DEFAULT 0,
    documents_skipped   INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL CHECK (status IN ('ok','partial','failed'))
);

-- Every query to the mini-brain endpoint is logged, allowed or denied. This
-- is what makes the conflict wall and visibility filter checkable after the
-- fact, and is itself part of the conflict-of-interest control (a denied
-- query is evidence a wall is holding, not just evidence of a bug).
CREATE TABLE audit_log (
    audit_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                  TEXT NOT NULL DEFAULT (datetime('now')),
    user_id             TEXT NOT NULL,
    client_id           TEXT NOT NULL,
    query_text          TEXT NOT NULL,
    decision            TEXT NOT NULL CHECK (decision IN ('allowed','denied')),
    denial_reason       TEXT,
    result_count        INTEGER NOT NULL DEFAULT 0
);
