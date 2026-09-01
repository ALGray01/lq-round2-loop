"""
End-to-end smoke test: launches server.py as a real MCP subprocess over
stdio, connects a real MCP client, and actually invokes every tool --
including deliberately-bad inputs -- to see real output, not just import
the functions in-process.

This is a smoke test for demo/verification purposes, not a hidden scorer:
it prints results and does simple assert checks on structural invariants
(e.g. "resolved refs must exist in corpus"), it does not decide pass/fail
for the whole submission.
"""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "corpus.db"


async def call(session, name, **kwargs):
    result = await session.call_tool(name, kwargs)
    text = result.content[0].text
    return json.loads(text)


async def main():
    params = StdioServerParameters(command=sys.executable, args=["src/server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools exposed:", [t.name for t in tools.tools])
            assert {"get_by_citation", "get_cross_references", "list_hierarchy",
                    "search_text", "check_currency"} <= {t.name for t in tools.tools}

            print("\n--- get_by_citation('11.10') ---")
            r = await call(session, "get_by_citation", citation="11.10")
            print(json.dumps(r, indent=2)[:600])
            assert r["found"] is True
            assert r["citation"] == "21 CFR 11.10"
            assert "closed systems" in r["heading"].lower()

            print("\n--- get_by_citation('21 CFR 999.99') [should be not found] ---")
            r = await call(session, "get_by_citation", citation="21 CFR 999.99")
            print(json.dumps(r, indent=2))
            assert r["found"] is False

            print("\n--- get_by_citation('21 CFR Part 11') [part node] ---")
            r = await call(session, "get_by_citation", citation="21 CFR Part 11")
            print(json.dumps(r, indent=2)[:600])
            assert r["found"] is True
            assert r["type"] == "part"

            print("\n--- get_cross_references('21 CFR 11.1') ---")
            r = await call(session, "get_cross_references", citation="21 CFR 11.1")
            print(json.dumps(r, indent=2)[:1500])
            assert r["found"] is True
            resolved_targets = {c["target_citation"] for c in r["cites"] if c["resolved"]}
            unresolved_targets = {c["target_citation"] for c in r["cites"] if not c["resolved"]}
            assert "21 CFR Part 1 Subpart J" in resolved_targets, "should resolve the subpart J cross-ref"
            assert "21 CFR Part 117" in unresolved_targets, "part 117 is out of corpus scope, must be unresolved"

            print("\n--- get_cross_references('21 CFR 1.326') [check inbound] ---")
            r = await call(session, "get_cross_references", citation="21 CFR 1.326")
            print(json.dumps(r, indent=2)[:800])
            inbound_from = {c["from_citation"] for c in r["cited_by"]}
            assert "21 CFR 11.1" in inbound_from, "11.1 cites the 1.326-1.368 range, should show up as inbound"

            print("\n--- list_hierarchy('') [top level] ---")
            r = await call(session, "list_hierarchy", parent_citation="")
            print(json.dumps(r, indent=2))
            assert len(r["children"]) >= 2

            print("\n--- list_hierarchy('21 CFR Part 11') ---")
            r = await call(session, "list_hierarchy", parent_citation="21 CFR Part 11")
            print(json.dumps(r, indent=2))
            assert any(c["type"] == "SUBPART" for c in r["children"])

            print("\n--- search_text('biometric') [prefix match on 'Biometrics'] ---")
            r = await call(session, "search_text", query="biometric")
            print(json.dumps(r, indent=2))
            hit_citations = {row["citation"] for row in r["results"]}
            assert "21 CFR 11.200" in hit_citations, "11.200 discusses biometric signature controls"

            print("\n--- search_text() [FTS-syntax injection attempt, should not error/crash] ---")
            r = await call(session, "search_text", query='OR "; DROP TABLE sections_fts; --')
            print(json.dumps(r, indent=2))
            assert r["results"] == []
            # confirm the table really is still intact after the injection attempt
            r2 = await call(session, "search_text", query="closed systems")
            assert any(row["citation"] == "21 CFR 11.10" for row in r2["results"]), \
                "sections_fts must still be queryable after the injection attempt"

            print("\n--- malformed MCP-layer input [should error cleanly, not crash] ---")
            r = await session.call_tool("search_text", {"query": "signature", "limit": "not-a-number"})
            print("bad limit type -> isError:", r.isError, r.content[0].text[:150])
            assert r.isError is True

            r = await session.call_tool("get_by_citation", {})
            print("missing required arg -> isError:", r.isError, r.content[0].text[:150])
            assert r.isError is True

            r = await session.call_tool("nonexistent_tool", {})
            print("unknown tool -> isError:", r.isError, r.content[0].text[:150])
            assert r.isError is True

            print("\n--- check_currency() [live API call] ---")
            r = await call(session, "check_currency")
            print(json.dumps(r, indent=2))
            assert r["checked_live"] is True
            assert r["stale"] is False, "just-ingested snapshot should not be stale"

            print("\n--- check_currency() [forced-stale path, must actually detect it] ---")
            # server.py opens a fresh sqlite connection per call, so mutating
            # the on-disk db here is visible to the already-running server
            # subprocess on the next call without restarting it.
            conn = sqlite3.connect(DB_PATH)
            original_date = conn.execute(
                "SELECT value FROM meta WHERE key='ecfr_latest_amended_on'"
            ).fetchone()[0]
            conn.execute(
                "UPDATE meta SET value='1999-01-01' WHERE key='ecfr_latest_amended_on'"
            )
            conn.commit()
            conn.close()
            try:
                r = await call(session, "check_currency")
                print(json.dumps(r, indent=2))
                assert r["checked_live"] is True
                assert r["stale"] is True, "corrupted snapshot date must be detected as stale"
                assert r["snapshot_latest_amended_on"] == "1999-01-01"
            finally:
                # restore, since data/corpus.db is a committed file
                conn = sqlite3.connect(DB_PATH)
                conn.execute(
                    "UPDATE meta SET value=? WHERE key='ecfr_latest_amended_on'", (original_date,)
                )
                conn.commit()
                conn.close()
            r = await call(session, "check_currency")
            assert r["stale"] is False, "restored snapshot date must read as current again"

            print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
