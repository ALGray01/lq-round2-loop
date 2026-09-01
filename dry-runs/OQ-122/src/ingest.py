"""
Ingest 21 CFR Part 11 (Electronic Records; Electronic Signatures) and
21 CFR Part 1 Subpart J (Establishment, Maintenance, and Availability of
Records) from the official eCFR API into a local SQLite corpus.

Part 1 Subpart J is included alongside Part 11 specifically because Part 11
cross-references it repeatedly (see 21 CFR 11.1(f)) -- ingesting both lets
the cross-reference graph actually resolve some citations instead of every
reference being reported as external, which would be closer to "papering
over" the problem than solving it.

Source of truth: https://www.ecfr.gov/api  (no auth required, official GPO/
NARA data). Re-running this script re-fetches the current text and records
a fresh snapshot date/amendment metadata -- it does not assume yesterday's
copy is still current.
"""
import html
import json
import re
import sqlite3
import sys
import urllib.request
from datetime import date, datetime, timezone

API = "https://www.ecfr.gov/api/versioner/v1"
DB_PATH = "data/corpus.db"

# (title, part, subpart) slices that make up the ingested corpus.
CORPUS_SLICES = [
    ("21", "11", None),
    ("21", "1", "J"),
]


def http_get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "oq-122-mcp-statutes/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_latest_issue_date() -> str:
    titles = json.loads(http_get(f"{API}/titles.json"))
    for t in titles["titles"]:
        if str(t["number"]) == "21":
            return t["up_to_date_as_of"], t["latest_amended_on"], t["latest_issue_date"]
    raise RuntimeError("title 21 not found in eCFR titles list")


def parse_hierarchy_metadata(raw: str) -> dict:
    # Attribute value arrives already XML-unescaped once by the parser, so
    # &amp;quot; -> &quot;. Unescape a second time to recover the JSON text.
    return json.loads(html.unescape(raw))


def elem_text(elem) -> str:
    """Concatenate all text within an element (paragraphs, lists, etc.),
    excluding nested SECTION/SUBPART/PART child divisions (handled separately)
    and excluding HEAD (the section's own heading, e.g. "§ 11.1 Scope.", is
    returned separately by head_text() -- leaving it in here caused every
    section's own citation-shaped heading to be regex-matched as a
    self-citation to itself)."""
    parts = []

    def walk(e):
        tag = e.tag
        if tag.startswith("DIV") or tag == "HEAD":
            return  # nested division / heading, handled by caller separately
        if e.text:
            parts.append(e.text)
        for child in e:
            walk(child)
            if child.tail:
                parts.append(child.tail)

    if elem.text:
        parts.append(elem.text)
    for child in elem:
        if child.tag == "HEAD":
            if child.tail:
                parts.append(child.tail)
            continue
        walk(child)
        if child.tail:
            parts.append(child.tail)
    text = "".join(parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def head_text(elem) -> str:
    head = elem.find("HEAD")
    if head is None:
        return ""
    return "".join(head.itertext()).strip()


CITATION_KEY = {"PART": "part", "SUBPART": "subpart", "SECTION": "section", "SUBJGRP": "subjgrp"}


def walk_divisions(elem, parent_citation, nodes, sections, source_part_label):
    for child in list(elem):
        tag = child.tag
        if not tag.startswith("DIV"):
            continue
        div_type = child.get("TYPE", "")
        meta_raw = child.get("hierarchy_metadata")
        meta = parse_hierarchy_metadata(meta_raw) if meta_raw else {}
        citation = meta.get("citation", "")
        heading = head_text(child)
        nodes.append({
            "citation": citation,
            "type": div_type,
            "heading": heading,
            "parent_citation": parent_citation,
            "source_part_label": source_part_label,
        })
        if div_type == "SECTION":
            identifier = child.get("N", "")
            sections.append({
                "citation": citation,
                "identifier": identifier,
                "heading": heading,
                "text": elem_text(child),
                "parent_citation": parent_citation,
                "source_part_label": source_part_label,
            })
        # Recurse regardless of type (PART -> SUBPART -> SUBJGRP -> SECTION)
        walk_divisions(child, citation or parent_citation, nodes, sections, source_part_label)


def fetch_slice(as_of_date, title, part, subpart):
    url = f"{API}/full/{as_of_date}/title-{title}.xml?part={part}"
    if subpart:
        url += f"&subpart={subpart}"
    xml_bytes = http_get(url)
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_bytes)
    label = f"title-{title} part-{part}" + (f" subpart-{subpart}" if subpart else "")
    nodes, sections = [], []
    # root itself is a DIV (PART or SUBPART) -- record it, then recurse into it
    meta_raw = root.get("hierarchy_metadata")
    meta = parse_hierarchy_metadata(meta_raw) if meta_raw else {}
    root_citation = meta.get("citation", "")
    nodes.append({
        "citation": root_citation,
        "type": root.get("TYPE", ""),
        "heading": head_text(root),
        "parent_citation": None,
        "source_part_label": label,
    })
    walk_divisions(root, root_citation, nodes, sections, label)
    return nodes, sections


def fetch_amendment_dates(title, part):
    data = json.loads(http_get(f"{API}/versions/title-{title}.json?part={part}"))
    latest = {}
    for v in data.get("content_versions", []):
        if v.get("type") != "section":
            continue
        ident = v["identifier"]
        d = v.get("amendment_date") or v.get("date")
        if ident not in latest or d > latest[ident]:
            latest[ident] = d
    return latest


def init_db(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS nodes (
        citation TEXT PRIMARY KEY,
        type TEXT,
        heading TEXT,
        parent_citation TEXT,
        source_part_label TEXT
    );
    CREATE TABLE IF NOT EXISTS sections (
        citation TEXT PRIMARY KEY,
        identifier TEXT,
        heading TEXT,
        text TEXT,
        parent_citation TEXT,
        source_part_label TEXT,
        last_amended TEXT
    );
    CREATE TABLE IF NOT EXISTS citations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_citation TEXT,
        raw_text TEXT,
        target_type TEXT,
        target_citation TEXT,
        resolved INTEGER
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
        citation UNINDEXED, heading, text
    );
    """)


def normalize_section_identifier(part, section_num):
    return f"{part}.{section_num}"


def extract_citations(section_citation, text, known_sections):
    """Regex-based cross-reference extraction. Deliberately conservative:
    every match is tagged resolved=1 only if the target is actually present
    in the ingested corpus; otherwise resolved=0 (external) so the caller
    never gets a false impression that a citation was checked/followed."""
    out = []

    # 1. "X.Y" section refs following a section-mark, possibly a list joined
    #    by "and"/","/"through": e.g. "§§ 1.326 through 1.368", "§ 11.2".
    for m in re.finditer(r"§§?\s*([0-9]+(?:\.[0-9]+)?(?:\s*(?:,|and|through)\s*[0-9]+(?:\.[0-9]+)?)*)", text):
        span = m.group(1)
        nums = re.findall(r"[0-9]+\.[0-9]+", span)
        if not nums:
            # bare part-less number like "11.2" missing -> try single number attached to "this part"
            continue
        for n in nums:
            target = f"21 CFR {n}"
            if target == section_citation:
                # Genuine intra-section pinpoint self-reference (e.g. 21 CFR
                # 1.352(e) says "the information in § 1.352(a), (b), (c), or
                # (d)"), not a cross-reference to another provision. A
                # second audit pass flagged this appearing in cites/cited_by
                # as effectively the same symptom as the heading-duplication
                # self-citation bug fixed earlier, even though the root
                # cause differs (real body text, not a parsing artifact) --
                # excluded here because it isn't a cross-reference to
                # *another* section, which is what this tool is for.
                continue
            resolved = 1 if n in known_sections else 0
            out.append((section_citation, m.group(0), "section", target, resolved))

    # 2a. Reverse word order: "subpart L of part N of this chapter" (e.g.
    #     21 CFR 11.1(l)-(p) all use this phrasing). Matched and blanked out
    #     of a working copy *before* #2b runs, so #2b's plainer "part N ...
    #     of this chapter" pattern doesn't also match the "part N" substring
    #     inside this same phrase and double-count it as a bare, subpart-less
    #     Part N reference.
    text_minus_2a = text
    for m in re.finditer(r"[Ss]ubpart\s+([A-Z])\s+of\s+[Pp]art\s+([0-9]+)\s+of this chapter", text):
        subpart, part_num = m.group(1), m.group(2)
        target = f"21 CFR Part {part_num} Subpart {subpart}"
        resolved = 1 if target in known_sections else 0
        out.append((section_citation, m.group(0), "cfr_part", target, resolved))
        text_minus_2a = text_minus_2a.replace(m.group(0), " " * len(m.group(0)), 1)

    # 2b. "part N[, subpart L] of this chapter" refs
    for m in re.finditer(r"[Pp]art\s+([0-9]+)(?:,\s*subpart\s+([A-Z]))?\s+of this chapter", text_minus_2a):
        part_num, subpart = m.group(1), m.group(2)
        target = f"21 CFR Part {part_num}" + (f" Subpart {subpart}" if subpart else "")
        resolved = 1 if target in known_sections else 0
        out.append((section_citation, m.group(0), "cfr_part", target, resolved))

    # 3. U.S.C. statute refs, e.g. "21 U.S.C. 321-393"
    for m in re.finditer(r"([0-9]+)\s+U\.S\.C\.\s*([0-9,\-\s]+?)(?=[.;)]|$)", text):
        target = f"{m.group(1)} U.S.C. {m.group(2).strip()}"
        out.append((section_citation, m.group(0), "usc_statute", target, 0))

    return out


def main():
    as_of, latest_amended_on, latest_issue_date = get_latest_issue_date()
    print(f"eCFR title 21 up_to_date_as_of={as_of} latest_amended_on={latest_amended_on}")

    all_nodes, all_sections = [], []
    for title, part, subpart in CORPUS_SLICES:
        nodes, sections = fetch_slice(as_of, title, part, subpart)
        amend = fetch_amendment_dates(title, part)
        for s in sections:
            s["last_amended"] = amend.get(s["identifier"])
        all_nodes.extend(nodes)
        all_sections.extend(sections)
        print(f"  fetched {len(sections)} sections from title {title} part {part}"
              + (f" subpart {subpart}" if subpart else ""))

    known_section_ids = {s["identifier"] for s in all_sections}
    known_part_citations = {n["citation"] for n in all_nodes if n["type"] in ("PART", "SUBPART")}
    known = known_section_ids | known_part_citations

    import os
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    conn.execute("DELETE FROM nodes")
    conn.execute("DELETE FROM sections")
    conn.execute("DELETE FROM citations")
    conn.execute("DELETE FROM sections_fts")

    for n in all_nodes:
        conn.execute(
            "INSERT OR REPLACE INTO nodes (citation, type, heading, parent_citation, source_part_label) "
            "VALUES (?, ?, ?, ?, ?)",
            (n["citation"], n["type"], n["heading"], n["parent_citation"], n["source_part_label"]),
        )

    for s in all_sections:
        conn.execute(
            "INSERT OR REPLACE INTO sections "
            "(citation, identifier, heading, text, parent_citation, source_part_label, last_amended) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (s["citation"], s["identifier"], s["heading"], s["text"], s["parent_citation"],
             s["source_part_label"], s["last_amended"]),
        )
        conn.execute(
            "INSERT INTO sections_fts (citation, heading, text) VALUES (?, ?, ?)",
            (s["citation"], s["heading"], s["text"]),
        )
        cites = extract_citations(s["citation"], s["text"], known)
        for c in cites:
            conn.execute(
                "INSERT INTO citations (from_citation, raw_text, target_type, target_citation, resolved) "
                "VALUES (?, ?, ?, ?, ?)",
                c,
            )

    meta = {
        "corpus": "21 CFR Part 11; 21 CFR Part 1 Subpart J",
        "source_api": API,
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "ecfr_up_to_date_as_of": as_of,
        "ecfr_latest_amended_on": latest_amended_on,
        "ecfr_latest_issue_date": latest_issue_date,
        "section_count": str(len(all_sections)),
    }
    for k, v in meta.items():
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (k, v))

    conn.commit()
    n_cit = conn.execute("SELECT COUNT(*) FROM citations").fetchone()[0]
    n_resolved = conn.execute("SELECT COUNT(*) FROM citations WHERE resolved=1").fetchone()[0]
    conn.close()
    print(f"Wrote {len(all_sections)} sections, {n_cit} extracted citations "
          f"({n_resolved} resolved within corpus, {n_cit - n_resolved} external/unresolved).")


if __name__ == "__main__":
    main()
