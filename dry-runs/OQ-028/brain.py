"""
Core logic for the client "mini brain" endpoint: query_client_brain.

Kept separate from server.py (the MCP/JSON-RPC transport) so it can be
imported directly and unit-tested without going through a subprocess.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional


MAX_SNIPPET_LEN = 200


def _snippet(text: str, query: str, length: int = MAX_SNIPPET_LEN) -> str:
    lower_text = text.lower()
    idx = lower_text.find(query.lower())
    if idx == -1:
        return text[:length] + ("..." if len(text) > length else "")
    start = max(0, idx - 40)
    end = min(len(text), idx + len(query) + 80)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + text[start:end] + suffix


def _matches(title: str, body: str, query: str) -> bool:
    q = query.lower().strip()
    if not q:
        return False
    return q in title.lower() or q in body.lower()


def _group_members(cur: sqlite3.Cursor, client_id: str) -> set:
    """Client ids sharing a conflict_group_id with client_id, plus itself.

    A conflict recorded against one member of a group (e.g. a parent
    company) must also apply to its fellow group members (subsidiaries) --
    otherwise the conflict wall can be routed around by staffing a lawyer
    on a same-side sibling client instead of the one named in `conflicts`.
    """
    row = cur.execute(
        "SELECT conflict_group_id FROM clients WHERE client_id = ?", (client_id,)
    ).fetchone()
    group_id = row["conflict_group_id"] if row else None
    members = {client_id}
    if group_id is not None:
        members |= {
            r["client_id"]
            for r in cur.execute(
                "SELECT client_id FROM clients WHERE conflict_group_id = ?", (group_id,)
            ).fetchall()
        }
    return members


def query_client_brain(
    conn: sqlite3.Connection,
    requester_user_id: str,
    client_id: str,
    query: str,
    include_firm_wide: bool = True,
    max_results: int = 10,
) -> dict:
    if isinstance(max_results, bool) or not isinstance(max_results, int) or not (1 <= max_results <= 50):
        raise ValueError(f"max_results must be an integer between 1 and 50, got: {max_results!r}")

    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    def log(decision: str, denial_reason: Optional[str], result_count: int) -> None:
        cur.execute(
            "INSERT INTO audit_log (user_id, client_id, query_text, decision, "
            "denial_reason, result_count) VALUES (?, ?, ?, ?, ?, ?)",
            (requester_user_id, client_id, query, decision, denial_reason, result_count),
        )
        conn.commit()

    user_row = cur.execute(
        "SELECT * FROM users WHERE user_id = ?", (requester_user_id,)
    ).fetchone()
    if user_row is None:
        log("denied", "unknown_user", 0)
        return _denied("unknown_user")

    client_row = cur.execute(
        "SELECT * FROM clients WHERE client_id = ?", (client_id,)
    ).fetchone()
    if client_row is None:
        log("denied", "unknown_client", 0)
        return _denied("unknown_client")

    grant = cur.execute(
        "SELECT * FROM client_access WHERE client_id = ? AND user_id = ? "
        "AND revoked_at IS NULL",
        (client_id, requester_user_id),
    ).fetchone()
    if grant is None:
        log("denied", "no_active_grant", 0)
        return _denied("no_active_grant")

    # Defense-in-depth conflict wall check: even though a grant row exists,
    # verify the requester doesn't also hold an *active* grant on a client
    # recorded as adverse to this one. A grant existing does not, by itself,
    # prove the wall is intact -- grants can be mis-issued by a human. This
    # is what actually enforces conflict-of-interest isolation at query time.
    #
    # Checked at the conflict_group level, not just literal client_id: a
    # conflict recorded against one member of a group (e.g. a parent
    # company) applies to the whole group (its subsidiaries), otherwise the
    # wall can be routed around via a same-side sibling client that isn't
    # itself named in `conflicts`.
    other_active_clients = [
        r["client_id"]
        for r in cur.execute(
            "SELECT client_id FROM client_access WHERE user_id = ? "
            "AND revoked_at IS NULL AND client_id != ?",
            (requester_user_id, client_id),
        ).fetchall()
    ]
    if other_active_clients:
        my_side = _group_members(cur, client_id)
        other_side: set = set()
        for oc in other_active_clients:
            other_side |= _group_members(cur, oc)
        conflict_rows = cur.execute(
            "SELECT client_id_a, client_id_b FROM conflicts"
        ).fetchall()
        for row in conflict_rows:
            a, b = row["client_id_a"], row["client_id_b"]
            if (a in my_side and b in other_side) or (b in my_side and a in other_side):
                log("denied", "conflict_wall", 0)
                return _denied("conflict_wall")

    role = user_row["role"]
    if role == "client":
        visibility_clause = "AND visibility = 'lawyer_and_client'"
    else:
        visibility_clause = ""

    client_docs = cur.execute(
        f"SELECT * FROM documents WHERE client_id = ? AND excluded = 0 "
        f"{visibility_clause} ORDER BY ingested_at DESC",
        (client_id,),
    ).fetchall()

    client_results = []
    for doc in client_docs:
        if _matches(doc["title"], doc["body"], query):
            client_results.append(
                {
                    "doc_id": doc["doc_id"],
                    "source_type": doc["source_type"],
                    "visibility": doc["visibility"],
                    "matter_id": doc["matter_id"],
                    "title": doc["title"],
                    "snippet": _snippet(doc["body"], query),
                }
            )
        if len(client_results) >= max_results:
            break

    firm_wide_results = []
    if include_firm_wide:
        firm_docs = cur.execute(
            "SELECT * FROM documents WHERE client_id IS NULL "
            "AND source_type = 'firm_wide_kb' AND excluded = 0 "
            "ORDER BY ingested_at DESC"
        ).fetchall()
        for doc in firm_docs:
            if _matches(doc["title"], doc["body"], query):
                firm_wide_results.append(
                    {
                        "doc_id": doc["doc_id"],
                        "title": doc["title"],
                        "snippet": _snippet(doc["body"], query),
                    }
                )
            if len(firm_wide_results) >= max_results:
                break

    log("allowed", None, len(client_results))

    return {
        "allowed": True,
        "denial_reason": None,
        "client_results": client_results,
        "firm_wide_results": firm_wide_results,
    }


def _denied(reason: str) -> dict:
    return {
        "allowed": False,
        "denial_reason": reason,
        "client_results": [],
        "firm_wide_results": [],
    }
