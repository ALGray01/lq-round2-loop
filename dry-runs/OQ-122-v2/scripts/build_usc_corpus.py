#!/usr/bin/env python3
"""Build data/usc_corpus.json (15 U.S.C. 6501-6506, COPPA's enabling
statute) from the raw PDFs fetched by scripts/fetch_usc.py.

GovInfo's citation link service resolves to a rendered PDF of the printed
U.S. Code page(s) around the requested section - the same "Page 2243/
2244..." scanned-book layout as the physical volumes, which means:
  - Adjacent sections' PDF fetches overlap on shared pages (e.g. both the
    6501 and 6502 fetches include printed page 2244).
  - Each page can contain the tail of the section before it and/or the
    start of the section after it, not just one clean section.

This script deduplicates pages by their printed page number (parsed from
each page's own "Page NNNN ..." header line), concatenates the unique
pages in page-number order to reconstruct one continuous run of text
covering the whole cited range, then splits that continuous text on real
section-heading boundaries ("§ 6501. Definitions", etc.) rather than
trusting individual PDF-fetch boundaries - the actual section content for
a given citation can start on one page and run onto the next.
"""
import json
import re
from pathlib import Path

import pypdf

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "usc"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

PAGE_MARKER_RE = re.compile(r"^Page (\d+)\s*TITLE")
# A real section heading: "§ 6501. Definitions" / "§ 6502. Regulation of ..."
# - the section number must be one of ours, followed by a period and a
# capitalized heading, and (per the source) always starts a new line.
SECTION_HEADING_RE = re.compile(r"^§\s*(6501|6502|6503|6504|6505|6506)\.\s+(.+)$", re.MULTILINE)
# The printed Code inserts a new chapter's heading/table-of-contents
# directly after the last section of the prior chapter, with no numbered
# "§" heading of its own - e.g. "CHAPTER 91A—PROMOTING A SAFE INTERNET FOR
# CHILDREN" runs on immediately after § 6506's real text ends. Without
# stopping at this boundary, the last requested section's captured text
# silently swallows the next chapter's heading and table of contents.
CHAPTER_BOUNDARY_RE = re.compile(r"^CHAPTER \d+[A-Z]?—", re.MULTILINE)

TITLE = 15


def load_unique_pages():
    pages = {}  # page_number -> text
    for pdf_path in sorted(RAW_DIR.glob(f"usc{TITLE}_*.pdf")):
        reader = pypdf.PdfReader(pdf_path)
        for page in reader.pages:
            text = page.extract_text()
            m = PAGE_MARKER_RE.match(text)
            if not m:
                raise RuntimeError(f"could not find a page-number marker in {pdf_path}: {text[:80]!r}")
            page_num = int(m.group(1))
            pages.setdefault(page_num, text)
    return pages


def combined_text(pages: dict) -> str:
    ordered = [pages[n] for n in sorted(pages)]
    return "\n".join(ordered)


def split_sections(text: str):
    matches = list(SECTION_HEADING_RE.finditer(text))
    sections = []
    for i, m in enumerate(matches):
        number = m.group(1)
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chapter_boundary = CHAPTER_BOUNDARY_RE.search(text, start, end)
        if chapter_boundary:
            end = chapter_boundary.start()
        body = text[start:end]
        # Strip the repeated "Page NNNN TITLE 15—COMMERCE AND TRADE§ NNNN"
        # running header/footer that appears at each page break inside a
        # section's body (not just at the very start of a page's text).
        body = re.sub(r"Page \d+\s*TITLE 15[—-]COMMERCE AND TRADE\s*§\s*\d+", " ", body)
        body = re.sub(r"\n{2,}", "\n", body).strip()
        sections.append(
            {
                "identifier": number,
                "citation": f"{TITLE} U.S.C. {number}",
                "heading": heading,
                "text": body,
            }
        )
    return sections


# SECTION_HEADING_RE only captures the first printed line after "§ NNNN.",
# but the real printed heading for a few sections spans multiple lines
# before the operative text begins - and unlike the chapter-boundary case,
# there's no reliable *algorithmic* signal to detect where a heading ends
# and body text begins: bold-run font detection was tried (via PyMuPDF's
# per-span font metadata) and rejected, because subsection labels like
# "(a) Acts prohibited" are set in the exact same bold font as the section
# heading itself, with no intervening plain-font text - so "stop at the
# first non-bold span" over-captures past the real heading into the first
# one or two subsection labels. Given that, and that this is a bounded,
# one-time corpus (6 sections, verified by hand against the raw PDFs
# rather than assumed), these are manually-verified corrections, not a
# general algorithm - each is a regex anchored to the exact continuation
# text found in the real source, and raises loudly if that text isn't
# found (rather than silently mis-splitting) so a future re-fetch that
# changes the underlying text can't silently apply a stale correction.
HEADING_CONTINUATIONS = {
    "6502": re.compile(
        r"^and practices in connection with collection\s+"
        r"and use of personal information from and\s+"
        r"about children on the Internet\s+"
    ),
}


def apply_manual_heading_corrections(sections):
    for s in sections:
        pattern = HEADING_CONTINUATIONS.get(s["identifier"])
        if pattern is None:
            continue
        m = pattern.match(s["text"])
        if not m:
            raise RuntimeError(
                f"expected heading continuation not found at the start of section "
                f"{s['identifier']}'s text - the source PDF may have changed; "
                f"HEADING_CONTINUATIONS needs re-verifying by hand, not silently applied"
            )
        continuation = re.sub(r"\s+", " ", m.group(0)).strip()
        s["heading"] = f"{s['heading']} {continuation}"
        s["text"] = s["text"][m.end():].lstrip()


def main():
    pages = load_unique_pages()
    print(f"loaded {len(pages)} unique printed pages: {sorted(pages)}")

    text = combined_text(pages)
    sections = split_sections(text)
    apply_manual_heading_corrections(sections)

    found = {s["identifier"] for s in sections}
    expected = {"6501", "6502", "6503", "6504", "6505", "6506"}
    missing = expected - found
    if missing:
        raise RuntimeError(f"failed to extract sections: {sorted(missing)}")

    corpus = {
        "corpus_id": f"usc-title{TITLE}-6501-6506",
        "jurisdiction": "United States (federal)",
        "source": "GovInfo citation link service (https://www.govinfo.gov/link/uscode/)",
        "note": (
            "Extracted from rendered PDF pages of the printed U.S. Code "
            "(not a structured XML/JSON source - GovInfo's link service was "
            "the only citation-addressable official U.S. Code source found "
            "for this project). Text may contain minor OCR/extraction "
            "artifacts (e.g. hyphenation across line breaks) inherent to "
            "PDF text extraction; it is not a substitute for the official "
            "printed or XML U.S. Code for legal-certainty purposes."
        ),
        "title": TITLE,
        "sections": sections,
    }

    out_path = DATA_DIR / "usc_corpus.json"
    out_path.write_text(json.dumps(corpus, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_path} with {len(sections)} sections")
    for s in sections:
        print(f"  {s['citation']}: {s['heading']!r} ({len(s['text'])} chars)")


if __name__ == "__main__":
    main()
