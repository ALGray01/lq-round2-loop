"""Confirms the server fails honestly (a clean MCP tool error) rather than
silently misbehaving when data/corpus.json is absent. The reserve-phase
verification-skeptic audit checked this by temporarily renaming the real
committed data/corpus.json away, observed a correct FileNotFoundError
surfaced as isError=True, and restored it - this persists that same check
as a repeatable test, but against an isolated copy of the server in a
scratch directory instead of touching the real repo's data file, so
running this test can never leave the real corpus missing if interrupted.

Run: python -m pytest tests/test_missing_corpus.py -v
"""
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_missing_corpus_file_fails_honestly():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        server_dir = tmp_path / "server"
        server_dir.mkdir()
        # (tmp_path / "data") deliberately NOT created - CORPUS_PATH
        # resolves to <server's parent>/data/corpus.json, so this
        # reproduces "corpus.json missing" without touching the real one.
        shutil.copy(REPO_ROOT / "server" / "statutes_mcp.py", server_dir / "statutes_mcp.py")

        async def call_it():
            params = StdioServerParameters(
                command=sys.executable, args=[str(server_dir / "statutes_mcp.py")]
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool("get_citation", {"citation": "312.5"})

        result = asyncio.run(call_it())
        assert result.isError is True, (
            "expected an honest MCP tool error when data/corpus.json is missing, "
            f"got isError={result.isError}"
        )
