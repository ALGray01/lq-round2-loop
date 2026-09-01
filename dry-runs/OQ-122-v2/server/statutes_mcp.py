#!/usr/bin/env python3
"""MCP server over a cached slice of the eCFR: 16 CFR Part 312 (the
Children's Online Privacy Protection Rule, "COPPA Rule").

Everything the server answers comes from data/corpus.json, built offline by
scripts/fetch_ecfr.py + scripts/build_corpus.py from the real, public eCFR
versioner API. The server itself does no network access at query time - it
is a read-only index over a point-in-time snapshot, which is the honest way
to make "is this current?" answerable at all (see check_currency below)
instead of silently implying freshness.

Tools:
  - get_citation(citation): retrieve-by-citation, the base case the brief
    asks for. Accepts "16 CFR 312.5", "312.5", "§ 312.5", "312.5(c)" etc.
  - list_structure(): the hierarchy (title > chapter > subchapter > part >
    sections), so a caller can browse instead of already knowing a citation.
  - search_text(query): full-text keyword search across the corpus.
  - find_sections_citing(citation): reverse cross-reference lookup - "which
    sections in this part cite X?" This is the one real structured query
    beyond plain citation lookup: it answers something no single section's
    text can answer by itself, by using the cross-reference index built at
    corpus-build time.
  - get_cross_references(citation): forward cross-reference lookup for one
    section, honestly split into resolved-in-corpus, resolved-in-companion
    (the 16 CFR Part 312's own enabling statute, 15 U.S.C. 6501-6506 - see
    get_usc_citation below), and external/unresolved (other U.S.C. titles,
    other CFR parts, named-Act section numbers) rather than pretending
    every reference was chased down.
  - get_usc_citation(citation): retrieve-by-citation for the companion
    U.S.C. corpus (15 U.S.C. 6501-6506, COPPA's enabling statute) built
    from GovInfo's citation link service - closes the regulation<->statute
    cross-reference loop for the one statute this Part actually implements,
    while staying honest that other cited titles (the FTC Act, the APA)
    are genuinely out of scope and not silently faked.
  - check_currency(): re-queries the live eCFR titles endpoint and reports
    whether the cached snapshot is still the latest issued text - the
    "currency" half of the brief, solved by an active check rather than an
    assumption baked in at build time.
"""
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CORPUS_PATH = DATA_DIR / "corpus.json"
USC_CORPUS_PATH = DATA_DIR / "usc_corpus.json"

mcp = FastMCP("statutes-ecfr-16-cfr-312")

_corpus = None
_usc_corpus = None


def load_corpus():
    global _corpus
    if _corpus is None:
        _corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return _corpus


def load_usc_corpus():
    global _usc_corpus
    if _usc_corpus is None:
        _usc_corpus = json.loads(USC_CORPUS_PATH.read_text(encoding="utf-8"))
    return _usc_corpus


def _section_index():
    corpus = load_corpus()
    return {s["identifier"]: s for s in corpus["sections"]}


def _usc_section_index():
    usc = load_usc_corpus()
    return {s["identifier"]: s for s in usc["sections"]}


CITATION_EXTRACT_RE = re.compile(r"(\d+\.\d+[A-Za-z]?)")

# No real citation is anywhere near this long; a caller sending something
# much bigger (accidentally or adversarially) gets a clean rejection
# instead of the oversized input being echoed back whole in an error
# message and search/regex work being done over it.
MAX_CITATION_LEN = 200


def normalize_citation(citation: str) -> Optional[str]:
    """Pull a bare section identifier like '312.5' out of any of the
    citation forms a caller might pass in ('16 CFR 312.5', '§ 312.5',
    '312.5(c)(1)', '312.5'). Returns None if nothing section-shaped is
    found, or if the input is unreasonably long for a citation."""
    if len(citation) > MAX_CITATION_LEN:
        return None
    m = CITATION_EXTRACT_RE.search(citation)
    return m.group(1) if m else None


MAX_SAFE_REPR_OUTPUT_LEN = 250  # bounds the *rendered* repr, not the input


def safe_repr(value: str) -> str:
    """repr() truncated to a sane length, so a caller's error message
    never echoes back an oversized/adversarial input in full.

    Truncating the input by character count before calling repr() isn't
    enough on its own: repr() escapes non-printable/non-ASCII characters
    (e.g. a zero-width space becomes the 6-character "\\u200b"), so a
    payload of unusual characters can still render several times longer
    than the input slice suggests. Bound the *rendered* string's length
    directly instead.
    """
    truncated_input = len(value) > MAX_CITATION_LEN
    r = repr(value[:MAX_CITATION_LEN] if truncated_input else value)
    if len(r) > MAX_SAFE_REPR_OUTPUT_LEN:
        r = r[:MAX_SAFE_REPR_OUTPUT_LEN] + "..."
        truncated_input = True
    return r + f" (truncated, {len(value)} chars total)" if truncated_input else r


@mcp.tool()
def get_citation(citation: str) -> dict:
    """Retrieve the full text of one section by citation.

    Accepts flexible input: "16 CFR 312.5", "312.5", "§ 312.5",
    "312.5(c)(1)" (paragraph suffixes are accepted but retrieval is at
    section granularity - the whole section is returned).
    """
    corpus = load_corpus()
    ident = normalize_citation(citation)
    if ident is None:
        return {
            "found": False,
            "error": f"could not parse a section identifier out of {safe_repr(citation)}",
        }
    section = _section_index().get(ident)
    if section is None:
        return {
            "found": False,
            "error": f"no section {ident} in this corpus ({corpus['corpus_id']}, "
            f"which only covers 16 CFR part {corpus['part']})",
        }
    return {
        "found": True,
        "citation": section["citation"],
        "heading": section["heading"],
        "hierarchy": corpus["hierarchy"],
        "text": section["text"],
        "paragraphs": section["paragraphs"],
        "snapshot_date": corpus["snapshot_date"],
        "source_url": corpus["source_urls"]["full_text"],
    }


@mcp.tool()
def list_structure() -> dict:
    """Return the corpus hierarchy (title > chapter > subchapter > part)
    and the list of every section in the part, for browsing when the
    caller does not already know a citation."""
    corpus = load_corpus()
    return {
        "corpus_id": corpus["corpus_id"],
        "jurisdiction": corpus["jurisdiction"],
        "hierarchy": corpus["hierarchy"],
        "part_heading": corpus["part_heading"],
        "authority": corpus["authority"],
        "snapshot_date": corpus["snapshot_date"],
        "sections": [
            {"identifier": s["identifier"], "citation": s["citation"], "heading": s["heading"]}
            for s in corpus["sections"]
        ],
    }


@mcp.tool()
def list_definitions() -> dict:
    """Every defined term in this part (from § 312.2's "Term means ..." /
    "Term includes ..." definitions), each tagged with its citation.
    Structured query: a caller asking "what does this regulation mean by
    X" needs the definition, not a keyword-search hit somewhere in a wall
    of text - this answers that directly."""
    corpus = load_corpus()
    return {"count": len(corpus["definitions"]), "definitions": corpus["definitions"]}


@mcp.tool()
def get_definition(term: str) -> dict:
    """Look up one defined term by name (case-insensitive, exact match on
    the defined term, e.g. "Operator", "Personal information")."""
    corpus = load_corpus()
    if len(term) > MAX_CITATION_LEN:
        return {"found": False, "error": "term is unreasonably long for a defined term"}
    needle = term.strip().lower()
    for d in corpus["definitions"]:
        if d["term"].lower() == needle:
            return {"found": True, **d}
    return {
        "found": False,
        "error": f"no defined term matches {safe_repr(term)}",
        "available_terms": [d["term"] for d in corpus["definitions"]],
    }


MAX_QUERY_LEN = 500  # search terms are naturally longer than citations, but still bounded


@mcp.tool()
def search_text(query: str, max_results: int = 10) -> dict:
    """Case-insensitive full-text search across every section's text.
    Structured query #1: keyword search scoped to this corpus, returning
    citation + a short snippet around each match rather than whole
    sections, so a caller can decide what to fetch in full next."""
    corpus = load_corpus()
    if len(query) > MAX_QUERY_LEN:
        return {
            "query": safe_repr(query),
            "error": f"query too long ({len(query)} chars, max {MAX_QUERY_LEN})",
            "results": [],
        }
    q = query.lower().strip()
    if not q or max_results <= 0:
        return {"query": query, "result_count": 0, "results": []}

    results = []
    for s in corpus["sections"]:
        text = s["text"]
        idx = text.lower().find(q)
        if idx == -1:
            continue
        start = max(0, idx - 80)
        end = min(len(text), idx + len(query) + 80)
        snippet = ("..." if start > 0 else "") + text[start:end].replace("\n", " ") + (
            "..." if end < len(text) else ""
        )
        results.append(
            {
                "citation": s["citation"],
                "heading": s["heading"],
                "snippet": snippet,
            }
        )
        if len(results) >= max_results:
            break

    return {"query": query, "result_count": len(results), "results": results}


@mcp.tool()
def find_sections_citing(citation: str) -> dict:
    """Structured query #2: reverse cross-reference lookup. Given a
    citation (e.g. "312.5" or "16 CFR 312.4"), return every section in this
    corpus whose text cites it - the kind of question that requires an
    index built over the whole corpus, not just one section's text, and is
    exactly the cross-reference problem the brief calls out."""
    corpus = load_corpus()
    ident = normalize_citation(citation)
    if ident is None:
        return {"found": False, "error": f"could not parse a section identifier out of {safe_repr(citation)}"}

    target = f"16 CFR {ident}"
    citing = []
    for s in corpus["sections"]:
        if s["identifier"] == ident:
            continue
        hits = [r for r in s["cross_references"] if r.get("target_citation") == target and r["resolved"]]
        if hits:
            citing.append(
                {
                    "citation": s["citation"],
                    "heading": s["heading"],
                    "via": sorted({h["raw_text"] for h in hits}),
                }
            )
    return {"target": target, "cited_by_count": len(citing), "cited_by": citing}


@mcp.tool()
def get_cross_references(citation: str) -> dict:
    """Forward cross-reference lookup for one section: every reference the
    text makes, split honestly into what this corpus can resolve
    (other sections of this same part), what the companion U.S. Code
    corpus can resolve (15 U.S.C. 6501-6506, this part's own enabling
    statute - see get_usc_citation), and what neither can (other U.S.C.
    titles, named-Act section numbers, other CFR parts/titles) - those
    are returned with their raw citation text so a caller knows exactly
    what wasn't chased down, rather than the gap being silently dropped."""
    corpus = load_corpus()
    ident = normalize_citation(citation)
    if ident is None:
        return {"found": False, "error": f"could not parse a section identifier out of {safe_repr(citation)}"}
    section = _section_index().get(ident)
    if section is None:
        return {"found": False, "error": f"no section {ident} in this corpus"}

    refs = section["cross_references"]
    companion_resolved = [r for r in refs if r.get("companion_resolved")]
    resolved = [
        r for r in refs
        if r["resolved"] and r["type"] != "self_reference" and not r.get("companion_resolved")
    ]
    external = [
        r for r in refs
        if not r["resolved"] and r["type"] != "self_reference" and not r.get("companion_resolved")
    ]
    self_refs = [r for r in refs if r["type"] == "self_reference"]

    return {
        "citation": section["citation"],
        "resolved_in_corpus": resolved,
        "resolved_in_companion_usc_corpus": companion_resolved,
        "external_unresolved": external,
        "self_references": self_refs,
        "note": (
            "resolved_in_companion_usc_corpus cites (15 U.S.C. 6501-6506, "
            "this part's own enabling statute) can be fetched in full via "
            "get_usc_citation. external_unresolved cites (other U.S.C. "
            "titles/sections, named Acts, other CFR parts) are outside "
            "this project's scope entirely and were not fetched; raw_text "
            "is the literal citation text found in the section so a "
            "human/agent can look it up."
        ),
    }


USC_HAS_TITLE_MARKER_RE = re.compile(r"U\.S\.C\.|United States Code|\btitle\b", re.IGNORECASE)
# Matches a title number directly tied to a recognized marker, in any of
# the common orders real citations use: "15 U.S.C." / "15 United States
# Code" (t1), or "title 15" / "Title 15," (t2, the worded form's usual
# order - see USC_WORDED_RE in scripts/build_corpus.py for the same
# pattern on the ingestion side).
USC_STATED_TITLE_RE = re.compile(
    r"(?:(?P<t1>\d{1,3})\s*(?:U\.S\.C\.|United States Code))"
    r"|(?:\btitle\s*(?P<t2>\d{1,3})\b)",
    re.IGNORECASE,
)
USC_BARE_SECTION_RE = re.compile(r"(\d{3,5})")
COMPANION_USC_TITLE = "15"


def normalize_usc_citation(citation: str) -> Optional[str]:
    """Pull a bare section number like '6501' out of '15 U.S.C. 6501',
    'section 6501 of title 15, United States Code', '§ 6501', or '6501'
    itself. Returns None for unreasonably long input, nothing
    number-shaped, or - critically - a citation that names an explicit
    U.S.C. title other than 15 in EITHER the abbreviated ("N U.S.C.") or
    worded ("of title N, United States Code" / "Title N, section ...")
    form: this companion corpus only ever covers Title 15.

    A reserve-phase audit found and confirmed two rounds of this same
    cross-title collision: first with the abbreviated form ("20 U.S.C.
    6501" incorrectly returning Title 15's real text), fixed; then a
    fresh audit found the fix only covered that one phrasing - the worded
    form ("section 6502 of title 20, United States Code") bypassed it
    entirely and still returned Title 15's text. Rather than add another
    one-off pattern for that specific phrasing (whack-a-mole against
    however many more forms exist), this checks broadly for ANY
    recognized U.S.C./title marker word first, then requires every title
    number found near one to equal 15 - so an unanticipated phrasing that
    still names a real title fails closed (rejected) instead of silently
    falling through to the bare-number match."""
    if len(citation) > MAX_CITATION_LEN:
        return None
    if USC_HAS_TITLE_MARKER_RE.search(citation):
        stated_titles = {
            (m.group("t1") or m.group("t2")) for m in USC_STATED_TITLE_RE.finditer(citation)
        }
        if stated_titles != {COMPANION_USC_TITLE}:
            return None
    m = USC_BARE_SECTION_RE.search(citation)
    return m.group(1) if m else None


@mcp.tool()
def get_usc_citation(citation: str) -> dict:
    """Retrieve the full text of one section of the companion U.S. Code
    corpus: 15 U.S.C. 6501-6506, the Children's Online Privacy Protection
    Act - the statute 16 CFR Part 312 implements. Accepts "15 U.S.C.
    6501", "6501", or "§ 6501". This corpus was built from GovInfo's
    citation-based PDF link service (there is no clean per-section
    XML/JSON U.S. Code API this project could find), so the text may
    carry minor PDF-extraction artifacts and includes the official
    editorial "Statutory Notes" alongside the operative text - see
    scripts/build_usc_corpus.py for exactly how it was extracted and
    what was corrected by hand."""
    if not USC_CORPUS_PATH.exists():
        return {"found": False, "error": "companion USC corpus (data/usc_corpus.json) not built"}
    usc = load_usc_corpus()
    ident = normalize_usc_citation(citation)
    if ident is None:
        return {"found": False, "error": f"could not parse a U.S.C. section number out of {safe_repr(citation)}"}
    section = _usc_section_index().get(ident)
    if section is None:
        return {
            "found": False,
            "error": f"no section {ident} in this companion corpus ({usc['corpus_id']}, "
            f"which only covers 15 U.S.C. 6501-6506)",
        }
    return {
        "found": True,
        "citation": section["citation"],
        "heading": section["heading"],
        "text": section["text"],
        "source": usc["source"],
        "note": usc["note"],
    }


@mcp.tool()
def check_currency() -> dict:
    """Actively re-check the live eCFR titles endpoint to see whether the
    cached snapshot (data/corpus.json) is still the most recently issued
    text for this title, rather than assuming a point-in-time scrape stays
    valid forever. Requires network access; reports that honestly if it's
    unavailable instead of guessing."""
    corpus = load_corpus()
    title = corpus["title"]
    url = "https://www.ecfr.gov/api/versioner/v1/titles.json"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "OQ-122 statutes-mcp currency check"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "checked": False,
            "error": f"could not reach eCFR API: {exc}",
            "cached_snapshot_date": corpus["snapshot_date"],
        }

    live_entry = next((t for t in data["titles"] if t["number"] == title), None)
    if live_entry is None:
        return {"checked": False, "error": f"title {title} missing from live titles.json"}

    is_current = live_entry["latest_issue_date"] == corpus["snapshot_date"]
    return {
        "checked": True,
        "cached_snapshot_date": corpus["snapshot_date"],
        "live_latest_issue_date": live_entry["latest_issue_date"],
        "live_latest_amended_on": live_entry["latest_amended_on"],
        "up_to_date": is_current,
        "action_if_stale": (
            None
            if is_current
            else "re-run scripts/fetch_ecfr.py and scripts/build_corpus.py to refresh the cache"
        ),
    }


if __name__ == "__main__":
    mcp.run()
