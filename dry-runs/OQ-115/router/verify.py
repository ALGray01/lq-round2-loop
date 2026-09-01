"""The verification pass for high-stakes requests.

This is deliberately simple, deterministic, pattern-based code -- NOT
another LLM call pretending to be a rubber stamp. (A second model call is
also made for high-stakes requests, as a substantive second opinion; see
router.py. This module is the mechanical safety net underneath it, and is
the part that is actually testable against known-bad input.)

It looks for concrete red flags in a drafted legal output:
  1. Malformed/implausible-looking citations (e.g. absurd volume numbers,
     impossible years).
  2. Unqualified absolute claims ("guaranteed", "100% certain", etc.)
     that a competent lawyer would hedge.
  3. A case-name-shaped citation with no reporter/year attached (looks
     like a citation but is missing the parts that would let anyone
     confirm it).

It is intentionally narrow: it catches surface-level red flags, not
substantive legal correctness. See README.md limitations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CURRENT_YEAR = 2026  # matches the assessment's stated "today"

# e.g. "410 U.S. 113" or "560 F.3d 1029" or "123 F. Supp. 2d 456"
_CITATION_RE = re.compile(
    r"\b(?P<volume>\d{1,5})\s+(?P<reporter>[A-Z][A-Za-z.]*(?:\s?\d?d)?)\s+(?P<page>\d{1,5})\b"
)
_YEAR_RE = re.compile(r"\((?:[A-Za-z.\s]*?)(?P<year>1[789]\d{2}|20\d{2})\)")

_ABSOLUTE_CLAIM_PATTERNS = (
    r"\bguarantee(?:d|s)?\b",
    r"\b100%\s*certain\b",
    r"\bwill definitely win\b",
    r"\bcannot lose\b",
    r"\bthere is no risk\b",
)

_HEDGE_WORD_RE = re.compile(r"\b(not|cannot|can't|no|never|without|unable to)\b")

# Phrases that contain a "hedge word" (e.g. "no") but actually REINFORCE
# certainty rather than qualify it -- "no doubt we guarantee X" is not
# hedged, it's doubled down. Without this, the naive hedge-word lookback
# would wrongly wave these through as if they were qualified. If one of
# these appears between the hedge word and the claim, the hedge doesn't
# count.
_CERTAINTY_REINFORCING_RE = re.compile(r"\b(doubt|question)\b")

# A bare "Name v. Name" with no reporter/year following within ~60 chars.
_CASE_NAME_RE = re.compile(r"\b[A-Z][A-Za-z.']+ v\.? [A-Z][A-Za-z.']+\b")


@dataclass
class VerificationResult:
    passed: bool
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "findings": self.findings}


def _check_citations(text: str) -> list[str]:
    findings = []
    for m in _CITATION_RE.finditer(text):
        volume = int(m.group("volume"))
        page = int(m.group("page"))
        if volume == 0 or page == 0:
            findings.append(f"citation has zero volume/page: {m.group(0)!r}")
        if volume > 2000:
            findings.append(f"citation volume implausibly large: {m.group(0)!r}")
    for m in _YEAR_RE.finditer(text):
        year = int(m.group("year"))
        if year > CURRENT_YEAR:
            findings.append(f"citation year is in the future ({year}): {m.group(0)!r}")
    return findings


def _check_dangling_case_names(text: str) -> list[str]:
    findings = []
    for m in _CASE_NAME_RE.finditer(text):
        tail = text[m.end(): m.end() + 60]
        if not _YEAR_RE.search(tail) and not _CITATION_RE.search(tail):
            findings.append(
                f"case name with no reporter/year nearby (possibly incomplete "
                f"or fabricated citation): {m.group(0)!r}"
            )
    return findings


def _check_absolute_claims(text: str) -> list[str]:
    findings = []
    lower = text.lower()
    for pattern in _ABSOLUTE_CLAIM_PATTERNS:
        for m in re.finditer(pattern, lower):
            # A hedge word shortly before the match (e.g. "we CANNOT
            # guarantee...", "there is NO guarantee...") flips the claim
            # from unqualified to appropriately hedged -- exactly the kind
            # of language a lawyer SHOULD use. Without this check, careful
            # hedging would be flagged as if it were the overclaim it's
            # actually disclaiming.
            preceding = lower[max(0, m.start() - 20): m.start()]
            hedge_match = _HEDGE_WORD_RE.search(preceding)
            is_hedged = hedge_match and not _CERTAINTY_REINFORCING_RE.search(
                preceding[hedge_match.end():]
            )
            if is_hedged:
                continue
            findings.append(f"unqualified absolute claim matched pattern: {pattern!r}")
    return findings


def verify_output(text: str) -> VerificationResult:
    findings: list[str] = []
    findings += _check_citations(text)
    findings += _check_dangling_case_names(text)
    findings += _check_absolute_claims(text)
    return VerificationResult(passed=(len(findings) == 0), findings=findings)
