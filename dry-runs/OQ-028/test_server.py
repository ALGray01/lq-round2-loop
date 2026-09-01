"""
Executed, subprocess-level test of server.py (the actual MCP transport, not
just brain.py's in-process functions). Every assertion here runs the real
server binary over stdin/stdout via JSON-RPC, the same way an MCP host
would.

Deliberately includes true-negative cases (denials that MUST happen) per the
principle that a permission/isolation check is only proven by attacking it,
not by only exercising the happy path:
  - unknown user
  - lawyer with no grant at all to a client (never staffed on it)
  - lawyer with a grant that should be overridden by the conflict wall
  - client-portal user must not see a lawyer_only document
  - an `excluded` document must never surface, to anyone

Run:
    python test_server.py
Exit code 0 = all assertions passed, non-zero = failure (see stderr).
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import seed

TEST_DB = "test_mini_brain.db"

failures = []


def rpc_call(proc_input: list[dict]) -> list[dict]:
    payload = "\n".join(json.dumps(r) for r in proc_input) + "\n"
    proc = subprocess.run(
        [sys.executable, "server.py", "--db", TEST_DB],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"server.py exited {proc.returncode}: {proc.stderr}")
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    return [json.loads(l) for l in lines]


def tool_call(req_id: int, user: str, client: str, query: str, **kwargs) -> dict:
    args = {"requester_user_id": user, "client_id": client, "query": query, **kwargs}
    resp = rpc_call(
        [
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/call",
                "params": {"name": "query_client_brain", "arguments": args},
            }
        ]
    )[0]
    assert "result" in resp, f"expected a result, got: {resp}"
    return json.loads(resp["result"]["content"][0]["text"])


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def main() -> int:
    seed.build(TEST_DB)

    # --- protocol handshake -------------------------------------------------
    init_resp = rpc_call([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}])[0]
    check("initialize returns protocolVersion",
          init_resp.get("result", {}).get("protocolVersion") is not None, str(init_resp))

    list_resp = rpc_call([{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}])[0]
    tool_names = [t["name"] for t in list_resp.get("result", {}).get("tools", [])]
    check("tools/list exposes query_client_brain", "query_client_brain" in tool_names, str(list_resp))

    # --- happy path: correctly-staffed lawyer -------------------------------
    r = tool_call(10, "user-priya", "client-acme", "settlement")
    check("staffed lawyer is allowed", r["allowed"] is True, str(r))
    check("staffed lawyer sees the lawyer_only doc",
          any(d["doc_id"] == "doc-1" for d in r["client_results"]), str(r))
    check("firm-wide result is returned in its own bucket",
          any(d["doc_id"] == "doc-5" for d in r["firm_wide_results"]), str(r))

    # --- true negative: unknown user ----------------------------------------
    r = tool_call(11, "user-ghost", "client-acme", "settlement")
    check("unknown user is denied", r["allowed"] is False and r["denial_reason"] == "unknown_user", str(r))
    check("denied request returns zero results", r["client_results"] == [] and r["firm_wide_results"] == [], str(r))

    # --- true negative: lawyer never staffed on this client ----------------
    r = tool_call(12, "user-priya", "client-beta", "budget")
    check("un-staffed lawyer is denied", r["allowed"] is False and r["denial_reason"] == "no_active_grant", str(r))

    # --- true negative: conflict wall overrides an existing grant row ------
    r = tool_call(13, "user-sam", "client-acme", "settlement")
    check("conflicted lawyer is denied despite holding a grant",
          r["allowed"] is False and r["denial_reason"] == "conflict_wall", str(r))
    r = tool_call(14, "user-sam", "client-beta", "budget")
    check("conflict wall applies symmetrically to the other side",
          r["allowed"] is False and r["denial_reason"] == "conflict_wall", str(r))

    # --- true negative: conflict wall must apply at the conflict_group
    # level, not just literal client_id (a real bug an adversarial audit
    # found: a grant to a same-group sibling client that isn't itself named
    # in `conflicts` used to slip through denied only by client_id match).
    r = tool_call("14a", "user-alex", "client-acme-sub", "settlement")
    check("conflict wall catches a same-conflict-group sibling client, not just the literal named client",
          r["allowed"] is False and r["denial_reason"] == "conflict_wall", str(r))
    r = tool_call("14b", "user-alex", "client-beta", "budget")
    check("conflict wall (group-level) applies symmetrically to the other side",
          r["allowed"] is False and r["denial_reason"] == "conflict_wall", str(r))

    # --- the group-level fix must not over-deny: a lawyer legitimately
    # staffed on two same-group siblings that are NOT adverse to each other
    # (a parent and its subsidiary, both clients of the firm) must stay
    # allowed. This guards against "fixing" the conflict check by treating
    # any shared conflict_group as itself disqualifying.
    r = tool_call("14c", "user-dana", "client-acme", "settlement")
    check("lawyer on two non-adverse same-group siblings is still allowed (client-acme)",
          r["allowed"] is True, str(r))
    r = tool_call("14d", "user-dana", "client-acme-sub", "settlement")
    check("lawyer on two non-adverse same-group siblings is still allowed (client-acme-sub)",
          r["allowed"] is True, str(r))

    # --- true negative: a grant with revoked_at = '' (empty string, not
    # NULL) must be treated as revoked, not as "not revoked." The check is
    # `revoked_at IS NULL`, which correctly treats '' as non-NULL; this
    # locks that behavior in against a future refactor that might swap in a
    # Python truthiness check (`if not revoked_at`) and silently invert it.
    r = tool_call("14e", "user-pat", "client-acme", "settlement")
    check("a grant with revoked_at='' (empty string) is treated as revoked, not active",
          r["allowed"] is False and r["denial_reason"] == "no_active_grant", str(r))

    # --- visibility filter: client must not see lawyer_only content --------
    r = tool_call(15, "user-jordan", "client-acme", "settlement")
    check("client portal user is allowed (has a grant)", r["allowed"] is True, str(r))
    check("client portal user does NOT see the lawyer_only doc",
          all(d["doc_id"] != "doc-1" for d in r["client_results"]), str(r))
    r = tool_call(16, "user-jordan", "client-acme", "discovery")
    check("client portal user DOES see the lawyer_and_client doc",
          any(d["doc_id"] == "doc-2" for d in r["client_results"]), str(r))

    # --- hard exclusion: never surfaces, to anyone --------------------------
    r = tool_call(17, "user-priya", "client-acme", "dinner")
    check("excluded document never surfaces even to a fully-staffed lawyer",
          r["client_results"] == [], str(r))

    # --- firm-wide knowledge never leaks another client's confidential doc -
    r = tool_call(18, "user-jordan", "client-acme", "budget")
    check("firm-wide/other-client search does not leak Beta's confidential doc",
          all(d["doc_id"] != "doc-4" for d in r["client_results"] + r["firm_wide_results"]), str(r))

    # --- attacked, not assumed: crafted/hostile and malformed input --------
    # Missing required argument -> a clean JSON-RPC error, not a crash/traceback.
    resp = rpc_call(
        [
            {
                "jsonrpc": "2.0",
                "id": 19,
                "method": "tools/call",
                "params": {
                    "name": "query_client_brain",
                    "arguments": {"requester_user_id": "user-priya", "query": "settlement"},
                },
            }
        ]
    )[0]
    check("missing required argument returns a JSON-RPC error, not a crash",
          "error" in resp and resp["error"]["code"] == -32602, str(resp))

    # Invalid max_results (wrong type, and out-of-range) must return a clean
    # JSON-RPC error and must NOT crash the server process (a real bug an
    # adversarial audit found: an unvalidated string/out-of-range value used
    # to raise an uncaught TypeError inside the stdin loop and kill the
    # whole session -- a one-field DoS from any caller).
    for bad_value, why in [
        ("3", "wrong type (string, not int)"),
        (0, "below schema minimum"),
        (999, "above schema maximum"),
        (True, "wrong type (bool, not int -- bool is a Python int subclass)"),
    ]:
        resp = rpc_call(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 19,
                    "method": "tools/call",
                    "params": {
                        "name": "query_client_brain",
                        "arguments": {
                            "requester_user_id": "user-priya",
                            "client_id": "client-acme",
                            "query": "settlement",
                            "max_results": bad_value,
                        },
                    },
                }
            ]
        )[0]
        check(f"invalid max_results ({why}) returns a JSON-RPC error, not a crash",
              "error" in resp and resp["error"]["code"] == -32602, str(resp))

    # And the server process must still be alive/responsive after each of
    # those bad calls -- prove it by making one more, separate subprocess
    # call succeed cleanly (rpc_call already spawns a fresh process per
    # call in this test file, so this also confirms the fix doesn't leave
    # the *class* of request permanently broken).
    r = tool_call("19c", "user-priya", "client-acme", "settlement", max_results=5)
    check("valid max_results still works after invalid attempts", r["allowed"] is True, str(r))

    # Unknown tool name.
    resp = rpc_call(
        [
            {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {"name": "delete_everything", "arguments": {}},
            }
        ]
    )[0]
    check("unknown tool name is rejected, not silently ignored",
          "error" in resp and resp["error"]["code"] == -32601, str(resp))

    # SQL-metacharacter-laden query string: must not error, and must not
    # actually mutate the database (query text only ever reaches sqlite
    # through parameterized '?' placeholders or Python-side substring
    # matching -- never string-interpolated into SQL).
    injection_payload = "'; DROP TABLE documents; --"
    r = tool_call(21, "user-priya", "client-acme", injection_payload)
    check("SQL-metacharacter query does not error", r["allowed"] is True, str(r))
    verify_conn = sqlite3.connect(TEST_DB)
    doc_count = verify_conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    verify_conn.close()
    check("documents table survives a SQL-metacharacter query string",
          doc_count > 0, f"doc_count={doc_count}")

    # Malformed JSON line: server must respond with a parse error for that
    # line and keep processing subsequent, well-formed requests in the same
    # session rather than dying.
    raw_lines = [
        '{"jsonrpc":"2.0","id":22,method:"tools/list","params":{}}',  # malformed on purpose
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 23,
                "method": "tools/list",
                "params": {},
            }
        ),
    ]
    proc = subprocess.run(
        [sys.executable, "server.py", "--db", TEST_DB],
        input="\n".join(raw_lines) + "\n",
        capture_output=True,
        text=True,
        timeout=30,
    )
    out_lines = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
    check("malformed JSON line yields a parse error",
          len(out_lines) >= 1 and "error" in out_lines[0] and out_lines[0]["error"]["code"] == -32700,
          str(out_lines))
    check("server keeps processing after a malformed line",
          len(out_lines) >= 2 and out_lines[1].get("id") == 23 and "result" in out_lines[1],
          str(out_lines))

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {failures}", file=sys.stderr)
        return 1
    print(f"All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
