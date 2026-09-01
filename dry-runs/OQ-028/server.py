"""
Minimal MCP server (stdio, JSON-RPC 2.0) exposing one tool:
query_client_brain.

Implements the subset of the Model Context Protocol needed for a host to
discover and call the tool: `initialize`, `tools/list`, `tools/call`.
Deliberately dependency-free (stdlib only) so it runs anywhere Python 3
runs, with no network install required.

Run:
    python server.py --db mini_brain.db

Then feed it newline-delimited JSON-RPC requests on stdin (see
test_server.py for real, executed examples, and README.md for a
copy-pasteable manual session).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from brain import query_client_brain

TOOL_SCHEMA_PATH = Path(__file__).parent / "schema" / "query_client_brain.tool.json"
PROTOCOL_VERSION = "2024-11-05"


def load_tool_definition() -> dict:
    with open(TOOL_SCHEMA_PATH, "r", encoding="utf-8") as f:
        tool = json.load(f)
    # MCP's tools/list wants {name, description, inputSchema} -- drop our
    # extra outputSchema field for that listing, but keep it available to
    # callers who read the schema file directly.
    return {
        "name": tool["name"],
        "description": tool["description"],
        "inputSchema": tool["inputSchema"],
    }


def handle_request(conn: sqlite3.Connection, req: dict) -> Optional[dict]:
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo": {"name": "mini-brain-mcp", "version": "0.1.0"},
            "capabilities": {"tools": {}},
        }
    elif method == "notifications/initialized":
        return None  # notification, no response
    elif method == "tools/list":
        result = {"tools": [load_tool_definition()]}
    elif method == "tools/call":
        name = params.get("name")
        if name != "query_client_brain":
            return _error(req_id, -32601, f"Unknown tool: {name}")
        args = params.get("arguments") or {}
        try:
            output = query_client_brain(
                conn,
                requester_user_id=args["requester_user_id"],
                client_id=args["client_id"],
                query=args["query"],
                include_firm_wide=args.get("include_firm_wide", True),
                max_results=args.get("max_results", 10),
            )
        except KeyError as e:
            return _error(req_id, -32602, f"Missing required argument: {e}")
        except ValueError as e:
            return _error(req_id, -32602, f"Invalid argument: {e}")
        # A denial (bad grant, conflict wall, etc.) is a valid structured
        # result, not a protocol-level error -- the caller's agent needs to
        # see *why* it was denied, so isError stays False.
        result = {
            "content": [{"type": "text", "text": json.dumps(output)}],
            "isError": False,
        }
    else:
        return _error(req_id, -32601, f"Unknown method: {method}")

    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="mini_brain.db")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            print(json.dumps(_error(None, -32700, f"Parse error: {e}")), flush=True)
            continue
        resp = handle_request(conn, req)
        if resp is not None:
            print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    main()
