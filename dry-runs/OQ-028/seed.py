"""
Build a fresh mini_brain.db from schema/schema.sql and populate it with a
small, deliberately adversarial sample dataset:

- Two clients (Acme Corp, Beta Industries) who are adverse to each other
  (litigation) -- exercises conflict-of-interest isolation.
- A lawyer staffed only on Acme (Priya), and a lawyer mistakenly holding
  active grants to BOTH sides (Sam) -- exercises the defense-in-depth
  conflict check even when a grant row technically exists.
- A client-portal user (Jordan, Acme's client contact) -- exercises the
  lawyer_only vs lawyer_and_client visibility filter.
- One excluded document (a personal email swept up during ingestion but
  flagged out) -- exercises the hard-exclusion path.
- One firm-wide knowledge-base doc, client_id NULL -- exercises the
  firm-wide-knowledge interaction.

Run:
    python seed.py [--db mini_brain.db]
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema" / "schema.sql"


def build(db_path: str) -> None:
    db_file = Path(db_path)
    if db_file.exists():
        db_file.unlink()

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    conn.executescript(
        """
        INSERT INTO conflict_groups (conflict_group_id, label) VALUES
            ('cg-acme', 'Acme Corp group'),
            ('cg-beta', 'Beta Industries group');

        INSERT INTO clients (client_id, name, conflict_group_id, status) VALUES
            ('client-acme', 'Acme Corp', 'cg-acme', 'active'),
            ('client-acme-sub', 'Acme Subsidiary LLC', 'cg-acme', 'active'),
            ('client-beta', 'Beta Industries', 'cg-beta', 'active');

        INSERT INTO conflicts (client_id_a, client_id_b, reason) VALUES
            ('client-acme', 'client-beta', 'Acme v. Beta Industries, breach of contract litigation');

        INSERT INTO users (user_id, name, role, email) VALUES
            ('user-priya', 'Priya Rao', 'lawyer', 'priya@firm.example'),
            ('user-sam',   'Sam Ito',   'lawyer', 'sam@firm.example'),
            ('user-alex',  'Alex Chen', 'lawyer', 'alex@firm.example'),
            ('user-dana',  'Dana Osei', 'lawyer', 'dana@firm.example'),
            ('user-pat',   'Pat Nguyen','lawyer', 'pat@firm.example'),
            ('user-jordan','Jordan Lee','client', 'jordan@acme.example');

        -- Priya: correctly staffed on Acme only.
        INSERT INTO client_access (client_id, user_id, access_role) VALUES
            ('client-acme', 'user-priya', 'responsible_lawyer');

        -- Sam: mis-issued grants to BOTH adverse clients. This should be
        -- caught and denied at query time, not just relied on to "not
        -- happen" because of the ACL.
        INSERT INTO client_access (client_id, user_id, access_role) VALUES
            ('client-acme', 'user-sam', 'team_lawyer'),
            ('client-beta', 'user-sam', 'team_lawyer');

        -- Alex: mis-issued grants to client-acme-SUB (not client-acme
        -- itself) and client-beta. client-acme-sub isn't named directly in
        -- `conflicts` -- only client-acme is -- but it shares Acme's
        -- conflict_group_id, so this must be caught by group-level
        -- conflict resolution, not a literal client_id match.
        INSERT INTO client_access (client_id, user_id, access_role) VALUES
            ('client-acme-sub', 'user-alex', 'team_lawyer'),
            ('client-beta', 'user-alex', 'team_lawyer');

        -- Dana: legitimately staffed on BOTH client-acme and client-acme-sub
        -- (same conflict_group, but NOT adverse to each other -- a lawyer
        -- can properly work for a parent and its subsidiary at once). This
        -- must stay ALLOWED: the group-level conflict check should catch
        -- adverse siblings without over-denying same-side siblings.
        INSERT INTO client_access (client_id, user_id, access_role) VALUES
            ('client-acme', 'user-dana', 'team_lawyer'),
            ('client-acme-sub', 'user-dana', 'team_lawyer');

        -- Pat: a grant whose revoked_at is an empty string rather than NULL
        -- (e.g. a bad write from some future migration). Must be treated as
        -- revoked (denied), not as "not revoked" via a truthiness check --
        -- the query is `revoked_at IS NULL`, which correctly excludes ''.
        INSERT INTO client_access (client_id, user_id, access_role, revoked_at) VALUES
            ('client-acme', 'user-pat', 'team_lawyer', '');

        -- Jordan: Acme's own client-portal contact.
        INSERT INTO client_access (client_id, user_id, access_role) VALUES
            ('client-acme', 'user-jordan', 'client_portal_user');

        INSERT INTO matters (matter_id, client_id, title, status) VALUES
            ('matter-acme-1', 'client-acme', 'Acme v. Beta Industries', 'open');

        INSERT INTO documents
            (doc_id, client_id, matter_id, source_type, title, body, visibility, excluded, exclusion_reason, source_ref)
        VALUES
            ('doc-1', 'client-acme', 'matter-acme-1', 'email',
             'RE: settlement posture',
             'Internal strategy note: our settlement floor for the Beta Industries dispute is $250,000. Do not share this figure with the client.',
             'lawyer_only', 0, NULL, 'msg-1001'),

            ('doc-2', 'client-acme', 'matter-acme-1', 'note',
             'Client update - case status',
             'Status update prepared for Acme: discovery is complete, mediation scheduled for next month.',
             'lawyer_and_client', 0, NULL, NULL),

            ('doc-3', 'client-acme', NULL, 'email',
             'Personal - dinner plans',
             'Hey, are we still on for dinner Friday? Nothing case-related, this got swept in by the mailbox sync filter.',
             'lawyer_only', 1, 'personal correspondence, not matter-related', 'msg-1002'),

            ('doc-4', 'client-beta', NULL, 'email',
             'Beta internal - litigation budget',
             'Beta Industries internal note on litigation budget for the Acme dispute.',
             'lawyer_only', 0, NULL, 'msg-2001'),

            ('doc-5', NULL, NULL, 'firm_wide_kb',
             'Firm know-how: settlement mediation best practices',
             'General firm guidance (not tied to any client) on preparing for mediation, applicable across matters.',
             'lawyer_only', 0, NULL, NULL);

        INSERT INTO ingestion_log (client_id, source_type, run_at, documents_added, documents_skipped, status) VALUES
            ('client-acme', 'email', datetime('now'), 3, 1, 'ok'),
            ('client-beta', 'email', datetime('now'), 1, 0, 'ok');
        """
    )
    conn.commit()
    conn.close()
    print(f"Seeded {db_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="mini_brain.db")
    args = parser.parse_args()
    build(args.db)
