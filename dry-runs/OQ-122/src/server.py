"""
MCP server exposing a small, real slice of 21 CFR (Part 11 and Part 1
Subpart J) for retrieval-by-citation and structured queries over the
citation graph and hierarchy.

Data comes from data/corpus.db, built by ingest.py from the live eCFR API.
This server does not itself hit the network for retrieval/query tools --
it reads the local snapshot -- but check_currency() does call the live API
so staleness is something you can actually detect, not just assume away.

Run:
    python src/server.py            (stdio MCP server)
"""
import json
import re
import sqlite3
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "corpus.db"
API = "https://www.ecfr.gov/api/versioner/v1"

mcp = FastMCP("cfr-statutes")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_citation(raw: str) -> str:
    """Best-effort normalization of a user-supplied citation string to the
    canonical form stored in the corpus (e.g. '21 CFR 11.10').

    Accepts: '11.10', '§ 11.10', '21 CFR 11.10', '21 CFR § 11.10',
    '21 CFR Part 11', 'Part 1 Subpart J', '21 CFR Part 1 Subpart J'.
    """
    s = raw.strip()
    s = s.replace("§", "")
    s = re.sub(r"(?i)^Section\s+", "", s)
    s = re.sub(r"(?i)^Sec\.\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()

    m = re.match(r"^(?:21\s*CFR\s*)?Part\s+(\d+)(?:\s*,?\s*Subpart\s+([A-Za-z]))?$", s, re.I)
    if m:
        part, subpart = m.group(1), m.group(2)
        out = f"21 CFR Part {part}"
        if subpart:
            out += f" Subpart {subpart.upper()}"
        return out

    m = re.match(r"^(?:21\s*CFR\s*)?(\d+\.\d+)$", s, re.I)
    if m:
        return f"21 CFR {m.group(1)}"

    return s  # already canonical, or unrecognized -- let the lookup fail honestly


def section_url(identifier: str) -> str:
    return f"https://www.ecfr.gov/current/title-21/section-{identifier}"


def part_url(citation: str) -> str:
    m = re.search(r"Part (\d+)", citation)
    return f"https://www.ecfr.gov/current/title-21/part-{m.group(1)}" if m else "https://www.ecfr.gov/current/title-21"


@mcp.tool()
def get_by_citation(citation: str) -> dict:
    """Retrieve a section, part, or subpart by its legal citation.

    Accepts formats like '21 CFR 11.10', '11.10', '21 CFR Part 1 Subpart J'.
    Returns full section text plus hierarchy position and the last date the
    section was substantively amended, according to the ingested snapshot.
    If the citation isn't in this corpus (e.g. a different CFR part), says
    so explicitly instead of guessing or returning a nearest match.
    """
    norm = normalize_citation(citation)
    conn = db()
    try:
        row = conn.execute(
            "SELECT * FROM sections WHERE citation = ? OR identifier = ?", (norm, norm)
        ).fetchone()
        if row:
            return {
                "found": True,
                "type": "section",
                "citation": row["citation"],
                "heading": row["heading"],
                "text": row["text"],
                "parent": row["parent_citation"],
                "last_amended": row["last_amended"],
                "source_url": section_url(row["identifier"]),
            }

        node = conn.execute("SELECT * FROM nodes WHERE citation = ?", (norm,)).fetchone()
        if node:
            children = conn.execute(
                "SELECT citation, type, heading FROM nodes WHERE parent_citation = ? ORDER BY citation",
                (norm,),
            ).fetchall()
            return {
                "found": True,
                "type": node["type"].lower(),
                "citation": node["citation"],
                "heading": node["heading"],
                "children": [dict(c) for c in children],
                "source_url": part_url(norm),
            }

        return {
            "found": False,
            "requested": citation,
            "normalized_as": norm,
            "reason": "Not present in the ingested corpus (21 CFR Part 11 and "
                      "21 CFR Part 1 Subpart J only). This is a scope limit of "
                      "this demo, not a claim that the citation doesn't exist.",
        }
    finally:
        conn.close()


@mcp.tool()
def get_cross_references(citation: str) -> dict:
    """Structured query over the citation graph for one section: what it
    cites (outbound) and what cites it (inbound), each tagged resolved
    (target is present in this ingested corpus) or unresolved (target is
    outside the ingested corpus -- e.g. a different CFR part or a U.S.C.
    statute section -- and was NOT fetched or verified, only detected as a
    reference in the text).
    """
    norm = normalize_citation(citation)
    conn = db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM sections WHERE citation = ?", (norm,)
        ).fetchone()
        if not exists:
            is_part_node = conn.execute(
                "SELECT 1 FROM nodes WHERE citation = ?", (norm,)
            ).fetchone()
            reason = (
                "This citation is a part/subpart, not a section -- the citation "
                "graph is tracked at section granularity. Use list_hierarchy to "
                "find the sections under it, then query those individually."
                if is_part_node else
                "Not present in the ingested corpus (21 CFR Part 11 and "
                "21 CFR Part 1 Subpart J only)."
            )
            return {"found": False, "requested": citation, "normalized_as": norm, "reason": reason}

        outbound = conn.execute(
            "SELECT raw_text, target_type, target_citation, resolved FROM citations "
            "WHERE from_citation = ? ORDER BY id",
            (norm,),
        ).fetchall()
        inbound = conn.execute(
            "SELECT from_citation, raw_text FROM citations "
            "WHERE target_citation = ? AND resolved = 1 ORDER BY from_citation",
            (norm,),
        ).fetchall()

        return {
            "found": True,
            "citation": norm,
            "cites": [dict(r) for r in outbound],
            "cited_by": [dict(r) for r in inbound],
            "note": "cited_by only reflects citations this corpus could resolve as "
                    "pointing back at this section -- it is not a full Shepard's/KeyCite "
                    "style citator across all of federal law.",
        }
    finally:
        conn.close()


@mcp.tool()
def list_hierarchy(parent_citation: str = "") -> dict:
    """List the child parts/subparts/sections directly under a given
    citation (e.g. '21 CFR Part 11' or '21 CFR Part 11 Subpart A'). Pass an
    empty string to list the top-level parts ingested in this corpus.
    """
    conn = db()
    try:
        parent = normalize_citation(parent_citation) if parent_citation else None
        if parent:
            rows = conn.execute(
                "SELECT citation, type, heading FROM nodes WHERE parent_citation = ? ORDER BY citation",
                (parent,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT citation, type, heading FROM nodes WHERE parent_citation IS NULL ORDER BY citation"
            ).fetchall()
        return {"parent": parent, "children": [dict(r) for r in rows]}
    finally:
        conn.close()


def _fts_query(user_query: str) -> str:
    """Build a safe, forgiving FTS5 MATCH expression from free text: each
    whitespace-separated word becomes a quoted prefix term, ANDed together.
    Quoting each term prevents FTS5 query-syntax injection (e.g. a user
    typing 'foo OR text:*' can't turn into an unintended boolean/column
    query -- it's just literal words to prefix-match)."""
    words = re.findall(r"\w+", user_query)
    if not words:
        return '""'
    return " AND ".join(f'"{w}"*' for w in words)


@mcp.tool()
def search_text(query: str, limit: int = 10) -> dict:
    """Full-text search over section headings and text (FTS5). Matches are
    prefix-based per word (e.g. 'biometric' matches 'Biometrics') and ANDed
    together. Returns matching sections with a short snippet showing the
    hit in context, ranked by relevance.
    """
    conn = db()
    try:
        match_expr = _fts_query(query)
        rows = conn.execute(
            "SELECT citation, heading, snippet(sections_fts, 2, '>>', '<<', '...', 12) AS snippet "
            "FROM sections_fts WHERE sections_fts MATCH ? ORDER BY rank LIMIT ?",
            (match_expr, max(1, min(limit, 50))),
        ).fetchall()
        return {"query": query, "results": [dict(r) for r in rows]}
    except sqlite3.OperationalError as e:
        return {"query": query, "results": [], "error": f"could not parse query: {e}"}
    finally:
        conn.close()


@mcp.tool()
def check_currency() -> dict:
    """Check whether the locally ingested snapshot is still current by
    calling the live eCFR API right now and comparing its 'latest_amended_on'
    date for Title 21 against what was recorded at ingest time. This is a
    real freshness check, not a static 'current as of' label frozen at build
    time -- if amendments have landed since ingestion, this will say so.
    """
    conn = db()
    try:
        meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}
    finally:
        conn.close()

    try:
        req = urllib.request.Request(
            f"{API}/titles.json", headers={"User-Agent": "oq-122-mcp-statutes/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            titles = json.loads(resp.read())
        live = next(t for t in titles["titles"] if str(t["number"]) == "21")
        stale = live["latest_amended_on"] != meta.get("ecfr_latest_amended_on")
        return {
            "checked_live": True,
            "ingested_at_utc": meta.get("ingested_at_utc"),
            "snapshot_latest_amended_on": meta.get("ecfr_latest_amended_on"),
            "live_latest_amended_on": live["latest_amended_on"],
            "stale": stale,
            "action_if_stale": "re-run `python src/ingest.py` to refresh the snapshot" if stale else None,
        }
    except Exception as e:
        return {
            "checked_live": False,
            "error": str(e),
            "ingested_at_utc": meta.get("ingested_at_utc"),
            "snapshot_latest_amended_on": meta.get("ecfr_latest_amended_on"),
            "note": "Could not reach the live eCFR API to verify currency right now; "
                    "falling back to reporting only the snapshot's own recorded date.",
        }


if __name__ == "__main__":
    mcp.run()
