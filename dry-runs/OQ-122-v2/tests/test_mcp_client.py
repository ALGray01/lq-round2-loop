#!/usr/bin/env python3
"""End-to-end check: drive server/statutes_mcp.py as a real MCP server
subprocess over the actual stdio transport, using the official mcp.client
SDK (not a hand-rolled stub). This is deliberately not a unit test that
imports the tool functions directly - it goes through the real protocol
(initialize -> list_tools -> call_tool) the same way Claude Desktop or any
other MCP host would, so a passing run is evidence the server actually
speaks MCP, not just that its Python functions return sane dicts.

Run: python tests/test_mcp_client.py
"""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = Path(__file__).resolve().parent.parent / "server" / "statutes_mcp.py"


def tool_json(call_tool_result):
    """FastMCP tools here return plain dict, so the SDK doesn't populate
    structuredContent (that needs a typed/pydantic return annotation) -
    the payload comes back as a JSON string in the first text content
    block instead. Parse it the way a real MCP host would."""
    return json.loads(call_tool_result.content[0].text)


async def run_checks():
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT)])
    failures = []

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = (await session.list_tools()).tools
            tool_names = {t.name for t in tools}
            expected = {
                "get_citation",
                "list_structure",
                "search_text",
                "find_sections_citing",
                "get_cross_references",
                "check_currency",
                "list_definitions",
                "get_definition",
                "get_usc_citation",
            }
            print("tools advertised over MCP:", sorted(tool_names))
            if not expected.issubset(tool_names):
                failures.append(f"missing tools: {expected - tool_names}")

            # 1. retrieve-by-citation, several input forms
            for cite in ["16 CFR 312.5", "312.5", "§ 312.2"]:
                res = await session.call_tool("get_citation", {"citation": cite})
                data = tool_json(res)
                print(f"get_citation({cite!r}) -> found={data.get('found')}")
                if not data.get("found"):
                    failures.append(f"get_citation failed to resolve {cite!r}")

            # 2. a citation that legitimately doesn't exist in this corpus
            res = await session.call_tool("get_citation", {"citation": "16 CFR 312.99"})
            data = tool_json(res)
            if data.get("found") is not False:
                failures.append("get_citation should report not-found for 312.99")
            print("get_citation(312.99) correctly not found:", data.get("error"))

            # 3. structured query: reverse cross-reference lookup
            res = await session.call_tool("find_sections_citing", {"citation": "312.5"})
            data = tool_json(res)
            print(f"find_sections_citing(312.5) -> cited_by_count={data.get('cited_by_count')}")
            if not data.get("cited_by_count", 0) > 0:
                failures.append("expected at least one section to cite 312.5")

            # 4. structured query: full text search
            res = await session.call_tool("search_text", {"query": "verifiable parental consent"})
            data = tool_json(res)
            print(f"search_text -> result_count={data.get('result_count')}")
            if not data.get("result_count", 0) > 0:
                failures.append("expected search hits for 'verifiable parental consent'")

            # 4b. adversarial: an oversized query must be rejected cleanly,
            # not echoed back in full (found by the reserve-phase attacker
            # audit - search_text was missing the length cap the other
            # citation/term-taking tools already had).
            huge_query = "A" * 1_000_000
            res = await session.call_tool("search_text", {"query": huge_query})
            raw_response_len = len(res.content[0].text)
            print(f"search_text(1M-char query) -> raw response length={raw_response_len}")
            if raw_response_len > 10_000:
                failures.append(
                    f"search_text echoed an oversized query back (response {raw_response_len} bytes)"
                )

            # 4c. adversarial: max_results <= 0 must return zero results,
            # not one (found by the round-2 attacker audit - the original
            # loop appended a result before checking the max_results cap).
            for bad_max in (0, -1, -999999999999):
                res = await session.call_tool(
                    "search_text", {"query": "operator", "max_results": bad_max}
                )
                data = tool_json(res)
                if data.get("result_count", -1) != 0:
                    failures.append(
                        f"search_text(max_results={bad_max}) should return 0 results, "
                        f"got {data.get('result_count')}"
                    )
            print("search_text with max_results<=0 correctly returns 0 results")

            # 5. cross-reference resolution honesty: resolved vs external
            res = await session.call_tool("get_cross_references", {"citation": "312.9"})
            data = tool_json(res)
            ext_types = {r["type"] for r in data.get("external_unresolved", [])}
            print(f"get_cross_references(312.9) external types: {ext_types}")
            if "usc" not in ext_types:
                failures.append("expected 312.9 to have an unresolved U.S.C. cross-reference")

            # 5b. USC companion corpus: 312.1 cites 15 U.S.C. 6501 (COPPA's
            # own enabling statute, which IS ingested) - that reference
            # should now resolve to the companion corpus, not sit in
            # external_unresolved.
            res = await session.call_tool("get_cross_references", {"citation": "312.1"})
            data = tool_json(res)
            companion = data.get("resolved_in_companion_usc_corpus", [])
            print(f"get_cross_references(312.1) companion-resolved count: {len(companion)}")
            if not any(r["target_citation"] == "15 U.S.C. 6501" for r in companion):
                failures.append("expected 312.1's cite to 15 U.S.C. 6501 to resolve via the companion USC corpus")
            if any(r["target_citation"] == "15 U.S.C. 6501" for r in data.get("external_unresolved", [])):
                failures.append("15 U.S.C. 6501 should not also appear in external_unresolved")

            # 5c. 312.9 cites 15 U.S.C. 57a (via the FTC Act) - a real USC
            # citation, but NOT one of the 6501-6506 range this project
            # ingested, so it must stay genuinely external. 312.9 ALSO cites
            # "section 6502(a) of this Act" and "sections 6503 and 6505 of
            # the Children's Online Privacy Protection Act" - COPPA
            # self-references, which DO correctly resolve via the companion
            # corpus (this section's cross-references are a real mix of
            # both cases, which is exactly why it's used as the test case).
            res = await session.call_tool("get_cross_references", {"citation": "312.9"})
            data = tool_json(res)
            companion = data.get("resolved_in_companion_usc_corpus", [])
            external = data.get("external_unresolved", [])
            if any(r.get("target_citation") == "15 U.S.C. 57a(a)(1)(B)" for r in companion):
                failures.append("312.9's U.S.C. 57a cite should NOT resolve via the companion corpus (out of range)")
            if not any(r.get("target_citation") == "15 U.S.C. 57a(a)(1)(B)" for r in external):
                failures.append("312.9's U.S.C. 57a cite should be in external_unresolved")
            if not any(r.get("target_citation") == "15 U.S.C. 6502" for r in companion):
                failures.append("312.9's 'section 6502(a) of this Act' should resolve via the companion corpus")
            if not any(r.get("target_citation") == "15 U.S.C. 6503" for r in companion):
                failures.append("312.9's 'sections 6503 and 6505...' (6503) should resolve via the companion corpus")

            # 5d. direct retrieval from the companion USC corpus, plus a
            # true-negative for a section number outside 6501-6506.
            res = await session.call_tool("get_usc_citation", {"citation": "15 U.S.C. 6501"})
            data = tool_json(res)
            print(f"get_usc_citation('15 U.S.C. 6501') -> found={data.get('found')}")
            if not data.get("found") or "child" not in data.get("text", "").lower():
                failures.append("get_usc_citation should retrieve real COPPA definitions text for 6501")

            res = await session.call_tool("get_usc_citation", {"citation": "9999"})
            data = tool_json(res)
            if data.get("found") is not False:
                failures.append("get_usc_citation should report not-found for a section outside 6501-6506")
            print("get_usc_citation(9999) correctly not found")

            # 5e-title. adversarial: a citation naming a DIFFERENT U.S.C.
            # title but the same in-range section number must be rejected,
            # not silently matched on bare section number (a fresh-context
            # audit found this exact cross-title collision working before
            # normalize_usc_citation validated the title).
            for bad_citation in ("20 U.S.C. 6501", "42 U.S.C. 6501", "5 U.S.C. 6501", "6501 U.S.C. 20"):
                res = await session.call_tool("get_usc_citation", {"citation": bad_citation})
                data = tool_json(res)
                if data.get("found") is not False:
                    failures.append(
                        f"get_usc_citation({bad_citation!r}) should reject a non-Title-15 citation, "
                        f"got found={data.get('found')}"
                    )
            print("get_usc_citation correctly rejects cross-title section-number collisions")

            # 5e-title-worded. Same collision, but via the WORDED citation
            # form ("of title N, United States Code") - a second audit
            # found this bypassed the abbreviated-form fix entirely.
            for bad_citation in (
                "section 6502 of title 20, United States Code",
                "20 United States Code 6502",
                "Title 20, section 6502",
            ):
                res = await session.call_tool("get_usc_citation", {"citation": bad_citation})
                data = tool_json(res)
                if data.get("found") is not False:
                    failures.append(
                        f"get_usc_citation({bad_citation!r}) should reject a non-Title-15 worded citation, "
                        f"got found={data.get('found')}"
                    )
            print("get_usc_citation correctly rejects worded-form cross-title collisions")

            # 5e. adversarial: oversized input must not be echoed back in
            # full (same length-cap pattern already applied elsewhere).
            res = await session.call_tool("get_usc_citation", {"citation": "A" * 200_000})
            raw_len = len(res.content[0].text)
            print(f"get_usc_citation(200k-char input) -> raw response length={raw_len}")
            if raw_len > 10_000:
                failures.append(f"get_usc_citation echoed oversized input back (response {raw_len} bytes)")

            # 6. currency check (live network call from inside the server process)
            res = await session.call_tool("check_currency", {})
            data = tool_json(res)
            print(f"check_currency -> checked={data.get('checked')} up_to_date={data.get('up_to_date')}")
            if not data.get("checked"):
                print("  (network unavailable during this run - not treated as a hard failure)")

            # 7a. definitions: list + exact lookup + case-insensitivity + a
            # true negative (a term that is not defined here)
            res = await session.call_tool("list_definitions", {})
            data = tool_json(res)
            print(f"list_definitions -> count={data.get('count')}")
            if data.get("count") != 18:
                failures.append(f"expected 18 definitions, got {data.get('count')}")

            res = await session.call_tool("get_definition", {"term": "operator"})
            data = tool_json(res)
            print(f"get_definition('operator') -> found={data.get('found')}")
            if not data.get("found") or "definition" not in data:
                failures.append("get_definition should resolve 'operator' case-insensitively")

            res = await session.call_tool("get_definition", {"term": "spaceship"})
            data = tool_json(res)
            if data.get("found") is not False:
                failures.append("get_definition should report not-found for an undefined term")
            print("get_definition('spaceship') correctly not found")

            # 7. hierarchy / structure listing
            res = await session.call_tool("list_structure", {})
            data = tool_json(res)
            print(f"list_structure -> {len(data.get('sections', []))} sections")
            if len(data.get("sections", [])) != 13:
                failures.append(f"expected 13 sections, got {len(data.get('sections', []))}")

    return failures


def main():
    failures = asyncio.run(run_checks())
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("\nAll MCP client checks passed.")


if __name__ == "__main__":
    main()
