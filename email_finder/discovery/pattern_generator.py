"""
Email pattern generator discovery node.

Generates common professional email address patterns from a lead's name and
company domain. These are unverified guesses — deliverability verification is
not part of this pipeline.
"""

from __future__ import annotations

import re

from email_finder.config import Config
from email_finder.models import LeadInput, NodeResult
from email_finder.verification.name_email_matcher import normalize

# Suffixes to strip before name parsing
_SUFFIXES = frozenset(["jr", "sr", "ii", "iii", "iv", "phd", "md", "esq"])


# ---------------------------------------------------------------------------
# Name parsing
# ---------------------------------------------------------------------------

def parse_name(full_name: str) -> dict:
    """
    Parse a full name into components used for pattern generation.

    Returns:
        {
            "first":         str,        # normalized first name (e.g. "john")
            "last":          str | None, # normalized last name
            "first_initial": str,        # first letter of first name
            "last_initial":  str | None, # first letter of last name
            "first_raw":     str,        # original (lowered) first token, may contain hyphen
        }

    Rules:
    - Middle names are ignored (only first and last tokens kept)
    - Suffixes (Jr., Sr., II, PhD, …) are stripped
    - Hyphenated first names: "Mary-Jane" → first="maryjane", also preserves raw "mary-jane"
    - Single names: "Madonna" → first="madonna", last=None
    """
    # Normalise casing, strip punctuation except hyphens (preserve in names)
    tokens = re.sub(r"[^\w\s-]", "", full_name.strip()).split()
    if not tokens:
        return {"first": "", "last": None, "first_initial": "", "last_initial": None, "first_raw": ""}

    # Strip trailing suffixes
    while tokens and normalize(tokens[-1].replace("-", "")) in _SUFFIXES:
        tokens.pop()

    if not tokens:
        return {"first": "", "last": None, "first_initial": "", "last_initial": None, "first_raw": ""}

    first_raw = tokens[0].lower()
    first_norm = normalize(first_raw)          # strips hyphens + accents
    first_initial = first_norm[0] if first_norm else ""

    if len(tokens) == 1:
        return {
            "first": first_norm,
            "last": None,
            "first_initial": first_initial,
            "last_initial": None,
            "first_raw": first_raw,
        }

    last_raw = tokens[-1].lower()              # tokens[-1] = last (middle ignored)
    last_norm = normalize(last_raw)
    last_initial = last_norm[0] if last_norm else ""

    return {
        "first": first_norm,
        "last": last_norm,
        "first_initial": first_initial,
        "last_initial": last_initial,
        "first_raw": first_raw,                # may contain "-" for hyphenated names
    }


# ---------------------------------------------------------------------------
# Pattern generation
# ---------------------------------------------------------------------------

def generate_email_patterns(full_name: str, domain: str) -> list[str]:
    """
    Generate common professional email patterns for *full_name* at *domain*.

    Returns candidates in priority order (most common format first).
    """
    p = parse_name(full_name)
    first = p["first"]
    last = p["last"]
    fi = p["first_initial"]
    li = p["last_initial"]
    first_raw = p["first_raw"]              # may contain hyphen

    if not first:
        return []

    d = domain.lstrip("@")

    if not last:
        # Single name — only one sensible pattern
        return [f"{first}@{d}"]

    patterns: list[str] = [
        f"{first}.{last}@{d}",         # 1. first.last      (most common)
        f"{first}{last}@{d}",          # 2. firstlast
        f"{fi}{last}@{d}",             # 3. flast
        f"{first}@{d}",                # 4. first
        f"{last}.{first}@{d}",         # 5. last.first
        f"{first}{li}@{d}",            # 6. firstl
        f"{fi}.{last}@{d}",            # 7. f.last
        f"{first}_{last}@{d}",         # 8. first_last
        f"{first}-{last}@{d}",         # 9. first-last
        f"{last}@{d}",                 # 10. last
    ]

    # Extra variants for hyphenated first names
    if "-" in first_raw:
        sub_parts = [normalize(p) for p in first_raw.split("-") if normalize(p)]
        if len(sub_parts) >= 2:
            hyphen_first = sub_parts[0]
            patterns.append(f"{first_raw}.{last}@{d}")          # mary-jane.watson@
            patterns.append(f"{hyphen_first}.{last}@{d}")       # mary.watson@
            patterns.append(f"{hyphen_first}@{d}")              # mary@

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for pat in patterns:
        if pat not in seen:
            seen.add(pat)
            result.append(pat)

    return result


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

async def generate_patterns(lead: LeadInput, config: Config) -> NodeResult:
    """
    Generate email pattern candidates for the lead.

    Requires a domain (from ``lead.company_domain`` or derived from
    ``lead.website``).  Returns ``NodeResult.found_emails`` with up to
    ``config.max_patterns_per_lead`` candidates; these are unverified guesses.
    """
    # Resolve domain
    domain: str | None = lead.company_domain

    if not domain and lead.website:
        from urllib.parse import urlparse
        parsed = urlparse(lead.website if "://" in lead.website else f"https://{lead.website}")
        domain = parsed.netloc.lstrip("www.") or None

    if not domain:
        return NodeResult(error="no domain for pattern generation")

    patterns = generate_email_patterns(lead.full_name, domain)
    patterns = patterns[: config.max_patterns_per_lead]

    return NodeResult(
        found_emails=patterns,
        found_email=patterns[0] if patterns else None,
        data={"domain": domain, "pattern_count": len(patterns)},
    )
