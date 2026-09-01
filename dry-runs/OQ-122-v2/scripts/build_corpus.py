#!/usr/bin/env python3
"""Build the queryable corpus (data/corpus.json) from the raw eCFR
structure + full-text XML fetched by fetch_ecfr.py.

Responsibilities:
  1. Parse the DIV5/DIV8 XML into one record per section: citation,
     heading, plain text, ordered paragraph list.
  2. Walk the structure JSON to recover the full hierarchy path
     (title > chapter > subchapter > part) each section lives under.
  3. Extract cross-references out of each section's text (other sections
     in this part, other CFR parts, and U.S.C. statute cites) and resolve
     the ones that point inside this corpus; leave the ones that don't
     honestly marked as external/unresolved rather than pretending to
     have fetched them.
  4. Record corpus-level metadata (source URLs, snapshot date, authority,
     source note) so the server can answer "how current is this?"
     honestly instead of silently claiming to be up to date.
"""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"

# --- cross-reference patterns, calibrated against the actual text of
# 16 CFR part 312 (see part312_raw.xml) rather than invented in the abstract.

# "§ 312.5", "§§ 312.2 through 312.8, and 312.10", "§ 312.5(c)(3) and (4)"
# Captures a whole run of "§/§§ ... " up to the point a citation is fully
# specified; paragraph-level suffixes like (c)(3) are kept as part of the
# raw text but not separately resolved (we resolve at section granularity).
# The separator between numbers can be a bare comma, "and"/"or", "through",
# or a comma *plus* "and"/"or" (e.g. ", and 312.10") - real text uses all of
# these forms, so the alternation has to allow the combined case too.
SECTION_REF_RE = re.compile(
    r"§§?\s*(?P<parts>\d+\.\d+[A-Za-z]?(?:\([^)]+\))*"
    r"(?:\s*(?:,\s*(?:and|or)?|and|or|through)\s*\d+\.\d+[A-Za-z]?(?:\([^)]+\))*)*)"
)
# Walks a matched "parts" body left to right, pairing each number with
# whichever separator word (if any) preceded it, so "through" spans can be
# expanded into every section in between rather than just the two endpoints.
SECTION_TOKEN_RE = re.compile(
    r"(?:(?P<sep>through|and|or)\s+)?(?P<num>\d+\.\d+[A-Za-z]?)(?:\([^)]+\))*"
)


def expand_section_range(parts_str: str):
    """Return every section number referenced in a body like
    '312.2 through 312.8, and 312.10' -> ['312.2', ..., '312.8', '312.10']."""
    numbers = []
    prev = None
    for m in SECTION_TOKEN_RE.finditer(parts_str):
        num = m.group("num")
        sep = m.group("sep")
        if sep == "through" and prev is not None:
            prev_prefix, prev_suffix = prev.rsplit(".", 1)
            cur_prefix, cur_suffix = num.rsplit(".", 1)
            if prev_prefix == cur_prefix and prev_suffix.isdigit() and cur_suffix.isdigit():
                # `prev` was already appended as a standalone token on the
                # previous iteration; drop it before re-adding the full
                # range so the range start isn't duplicated.
                if numbers and numbers[-1] == prev:
                    numbers.pop()
                for n in range(int(prev_suffix), int(cur_suffix) + 1):
                    numbers.append(f"{prev_prefix}.{n}")
            else:
                numbers.append(num)
        else:
            numbers.append(num)
        prev = num
    return numbers

# "15 U.S.C. 6501", "15 U.S.C. 57a(a)(1)(B)", "15 U.S.C. 6501 through 6506"
USC_RE = re.compile(
    r"(?P<title>\d+)\s+U\.S\.C\.\s+(?P<section>\d+[A-Za-z]?(?:\([^)]+\))*"
    r"(?:\s+through\s+\d+[A-Za-z]?)?)"
)

# "section 551(1) of title 5, United States Code"
USC_WORDED_RE = re.compile(
    r"section\s+(?P<section>\d+[A-Za-z]?(?:\([^)]+\))*)\s+of\s+title\s+"
    r"(?P<title>\d+),?\s+United States Code",
    re.IGNORECASE,
)

# "section 6502(a) of this Act", "section 18(a)(1)(B) of the Federal Trade
# Commission Act (15 U.S.C. 57a(a)(1)(B))", "sections 6503 and 6505 of the
# Children's Online Privacy Protection Act of 1998"
# The act name is captured separately (not just matched) because "this Act"
# and "the Children's Online Privacy Protection Act" both mean COPPA itself
# - whose own enabling-statute section numbers happen to equal their U.S.C.
# section numbers directly (confirmed by reading the real text: "section
# 6502(a) of this Act" and "15 U.S.C. 6502" are the same section) - while
# "the Federal Trade Commission Act" is a genuinely different statute whose
# section numbers do NOT map directly (its "section 18" is 15 U.S.C. 57a,
# not 15 U.S.C. 18). Only the COPPA-self-reference case can be safely
# resolved against the companion corpus; any other named Act cannot be,
# without ingesting that Act's own text too.
NAMED_ACT_RE = re.compile(
    r"sections?\s+(?P<sections>[\d()a-zA-Z,\s]+?)\s+of\s+(?P<act>this Act\b|the [A-Z][^.(]+?Act(?: of \d{4})?)"
)
NAMED_ACT_NUMBER_RE = re.compile(r"\d{3,5}")
COPPA_SELF_REFERENCE_NAMES = ("this act", "children's online privacy protection act")


def is_coppa_self_reference(act_name: str) -> bool:
    lowered = act_name.lower()
    return any(name in lowered for name in COPPA_SELF_REFERENCE_NAMES)

SELF_REF_RE = re.compile(r"\bthis (part|section|subpart|paragraph)\b", re.IGNORECASE)

# The CFR's standard definitions convention: a paragraph that opens with the
# term itself followed by "means" or "includes", e.g. "Child means an
# individual under the age of 13." / "Parent includes a legal guardian."
# Calibrated against every paragraph in the real § 312.2 (see
# data/raw/title16_part312_*.xml) - all 15 defined terms there follow this
# shape, including two ("Parent", multi-word terms) that would be missed by
# a naive "first word only" rule.
DEFINITION_RE = re.compile(
    r"^(?P<term>[A-Z][^.]*?)\s+(?:means|includes)\b\s*(?P<definition>.*)$", re.DOTALL
)


def load_manifest():
    return json.loads((RAW_DIR / "manifest.json").read_text(encoding="utf-8"))


def strip_ns(tag: str) -> str:
    return tag.split("}")[-1]


def element_text(el) -> str:
    """Flatten an element's text (including nested <I>/<E> emphasis tags)
    into plain text, the way a human reading the rendered regulation would
    see it. Formatting is discarded; wording is preserved exactly."""
    return "".join(el.itertext())


def parse_sections(xml_path: Path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    part_head = None
    authority = None
    source_note = None
    for child in root:
        tag = strip_ns(child.tag)
        if tag == "HEAD" and part_head is None:
            part_head = element_text(child).strip()
        elif tag == "AUTH":
            authority = element_text(child).replace("Authority:", "").strip()
        elif tag == "SOURCE":
            source_note = element_text(child).replace("Source:", "").strip()

    sections = []
    for div8 in root.iter():
        if strip_ns(div8.tag) != "DIV8" or div8.attrib.get("TYPE") != "SECTION":
            continue
        identifier = div8.attrib["N"]
        meta_raw = div8.attrib.get("hierarchy_metadata", "{}")
        try:
            meta = json.loads(meta_raw)
        except json.JSONDecodeError:
            meta = {}
        citation = meta.get("citation", f"CFR {identifier}")

        heading = None
        paragraphs = []
        for el in div8:
            tag = strip_ns(el.tag)
            if tag == "HEAD" and heading is None:
                heading = element_text(el).strip()
            elif tag == "P":
                text = element_text(el).strip()
                if text:
                    paragraphs.append(text)

        full_text = "\n".join(paragraphs)
        sections.append(
            {
                "identifier": identifier,
                "citation": citation,
                "heading": heading,
                "paragraphs": paragraphs,
                "text": full_text,
            }
        )
    return part_head, authority, source_note, sections


def find_hierarchy_path(structure, part_number: str):
    """Return the ancestor chain (title/chapter/subchapter/...) above the
    given part, as recorded in the eCFR structure tree, plus the part
    node itself."""

    def walk(node, trail):
        if node.get("type") == "part" and node.get("identifier") == part_number:
            return trail + [node]
        for child in node.get("children", []) or []:
            result = walk(child, trail + [node])
            if result:
                return result
        return None

    result = walk(structure, [])
    if not result:
        raise RuntimeError(f"part {part_number} not found in structure tree")
    return [
        {"type": n["type"], "identifier": n.get("identifier"), "label": n.get("label")}
        for n in result
    ]


def extract_definitions(sections):
    """Pull out every defined term across the corpus using the CFR's
    standard "Term means ..." / "Term includes ..." convention, tagged
    with the section it came from. Only paragraphs that actually match are
    kept - most sections have none, and that's expected (this isn't every
    paragraph, just the definitions ones)."""
    definitions = []
    for s in sections:
        for para in s["paragraphs"]:
            m = DEFINITION_RE.match(para.strip())
            if not m:
                continue
            term = m.group("term").strip()
            # Guard against matching mid-sentence prose that happens to
            # contain " means "/" includes " far into a long paragraph
            # (real definitions state the term in the first few words).
            if len(term) > 80:
                continue
            definitions.append(
                {
                    "term": term,
                    "definition": para.strip(),
                    "citation": s["citation"],
                }
            )
    return definitions


USC_COMPANION_TARGET_RE = re.compile(r"^(?P<title>\d+) U\.S\.C\. (?P<section>\d+[A-Za-z]?)")


def load_usc_companion_index():
    """If data/usc_corpus.json exists (built by scripts/fetch_usc.py +
    scripts/build_usc_corpus.py), return a {(title, section): corpus_id}
    lookup so `usc`-type cross-references can be marked as resolved
    *in that companion corpus* - deliberately not folded into this CFR
    corpus's own `resolved` field, since the statute text lives in a
    separate file, not inside this one."""
    usc_path = DATA_DIR / "usc_corpus.json"
    if not usc_path.exists():
        return {}
    usc = json.loads(usc_path.read_text(encoding="utf-8"))
    return {
        (str(usc["title"]), s["identifier"]): usc["corpus_id"] for s in usc["sections"]
    }


def resolve_usc_against_companion(sections, usc_index: dict):
    """Mutates each `usc`-type cross-reference in place, adding
    companion_resolved/companion_corpus fields. Also applies to
    `named_act_section` references that extract_cross_references already
    determined are COPPA self-references with a real U.S.C.-shaped
    target_citation (see is_coppa_self_reference) - everything else
    (target_citation is None, e.g. the FTC Act) is left untouched. No-op
    (fields left False/None) if the companion USC corpus isn't present or
    doesn't cover the cited section - callers should never assume these
    fields exist without checking them."""
    for s in sections:
        for r in s["cross_references"]:
            if r["type"] not in ("usc", "named_act_section") or r["target_citation"] is None:
                continue
            m = USC_COMPANION_TARGET_RE.match(r["target_citation"])
            key = (m.group("title"), m.group("section")) if m else None
            corpus_id = usc_index.get(key) if key else None
            r["companion_resolved"] = corpus_id is not None
            r["companion_corpus"] = corpus_id


def extract_cross_references(text: str, part_number: str, known_sections: set):
    refs = []

    for m in SECTION_REF_RE.finditer(text):
        raw = m.group(0)
        for num in expand_section_range(m.group("parts")):
            candidate_citation = f"16 CFR {num}"
            in_this_part = num.split(".")[0] == part_number
            resolved = in_this_part and num in known_sections
            refs.append(
                {
                    "type": "internal_section" if in_this_part else "other_cfr_part",
                    "raw_text": raw.strip(),
                    "target_citation": candidate_citation,
                    "resolved": resolved,
                }
            )

    for m in USC_RE.finditer(text):
        refs.append(
            {
                "type": "usc",
                "raw_text": m.group(0),
                "target_citation": f"{m.group('title')} U.S.C. {m.group('section')}",
                "resolved": False,
            }
        )

    for m in USC_WORDED_RE.finditer(text):
        refs.append(
            {
                "type": "usc",
                "raw_text": m.group(0),
                "target_citation": f"{m.group('title')} U.S.C. {m.group('section')}",
                "resolved": False,
            }
        )

    for m in NAMED_ACT_RE.finditer(text):
        act_name = m.group("act")
        self_ref = is_coppa_self_reference(act_name)
        # Only extract 3-5 digit numbers as candidate U.S.C. section
        # numbers - e.g. "18(a)(1)(B)" (the FTC Act's own section 18)
        # correctly yields no such number, so it can never be mistaken
        # for a U.S.C. section regardless of which Act it's under.
        numbers = NAMED_ACT_NUMBER_RE.findall(m.group("sections"))
        if not numbers:
            refs.append(
                {
                    "type": "named_act_section",
                    "raw_text": m.group(0),
                    "target_citation": None,
                    "resolved": False,
                }
            )
            continue
        for num in numbers:
            refs.append(
                {
                    "type": "named_act_section",
                    "raw_text": m.group(0),
                    "target_citation": f"15 U.S.C. {num}" if self_ref else None,
                    "resolved": False,
                }
            )

    for m in SELF_REF_RE.finditer(text):
        refs.append(
            {
                "type": "self_reference",
                "raw_text": m.group(0),
                "target_citation": None,
                "resolved": True,
            }
        )

    return refs


def main():
    manifest = load_manifest()
    xml_path = RAW_DIR / manifest["xml_file"]
    structure_path = RAW_DIR / manifest["structure_file"]

    part_head, authority, source_note, sections = parse_sections(xml_path)
    structure = json.loads(structure_path.read_text(encoding="utf-8"))
    hierarchy = find_hierarchy_path(structure, str(manifest["part"]))

    known_sections = {s["identifier"] for s in sections}
    for s in sections:
        s["cross_references"] = extract_cross_references(
            s["text"], str(manifest["part"]), known_sections
        )

    usc_index = load_usc_companion_index()
    resolve_usc_against_companion(sections, usc_index)

    definitions = extract_definitions(sections)

    corpus = {
        "corpus_id": f"ecfr-title{manifest['title']}-part{manifest['part']}",
        "jurisdiction": "United States (federal)",
        "hierarchy": hierarchy,
        "part_heading": part_head,
        "authority": authority,
        "source_note": source_note,
        "snapshot_date": manifest["date"],
        "fetched_at": manifest["fetched_at"],
        "source_urls": manifest["source_urls"],
        "title": manifest["title"],
        "part": manifest["part"],
        "sections": sections,
        "definitions": definitions,
    }

    out_path = DATA_DIR / "corpus.json"
    out_path.write_text(json.dumps(corpus, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_path} with {len(sections)} sections")

    total_refs = sum(len(s["cross_references"]) for s in sections)
    resolved = sum(1 for s in sections for r in s["cross_references"] if r["resolved"])
    print(f"cross-references extracted: {total_refs} (resolved in-corpus: {resolved})")
    usc_companion_resolved = sum(
        1 for s in sections for r in s["cross_references"]
        if r["type"] == "usc" and r.get("companion_resolved")
    )
    usc_total = sum(1 for s in sections for r in s["cross_references"] if r["type"] == "usc")
    print(f"usc cross-references: {usc_total} (resolved via companion usc_corpus.json: {usc_companion_resolved})")
    print(f"definitions extracted: {len(definitions)}")


if __name__ == "__main__":
    main()
