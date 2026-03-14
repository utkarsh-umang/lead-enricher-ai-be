"""
Name-email matcher — core string matching utilities and enhanced name matching.

Ported from the Google Apps Script `qualifyPodcastLeads` helper functions
(EF-4) and extended with name-variation generation and confidence scoring
(EF-5).
"""

from __future__ import annotations

import re
from typing import Optional

from email_finder.config import Config
from email_finder.models import LeadInput, NodeResult

# ---------------------------------------------------------------------------
# Accent / transliteration map (mirrors the Google Script `accents` object)
# ---------------------------------------------------------------------------
_ACCENT_MAP: dict[str, str] = {
    "á": "a", "à": "a", "â": "a", "ä": "a", "ã": "a", "å": "a", "ā": "a",
    "é": "e", "è": "e", "ê": "e", "ë": "e", "ē": "e", "ė": "e", "ę": "e",
    "í": "i", "ì": "i", "î": "i", "ï": "i", "ī": "i",
    "ó": "o", "ò": "o", "ô": "o", "ö": "o", "õ": "o", "ø": "o", "ō": "o",
    "ú": "u", "ù": "u", "û": "u", "ü": "u", "ū": "u",
    "ñ": "n", "ń": "n", "ç": "c", "ć": "c", "ß": "ss", "ÿ": "y", "ý": "y",
}

_STOP_WORDS = frozenset([
    "with", "and", "the", "of", "for", "on", "a", "an", "in", "to",
    "podcast", "show", "radio", "live",
])

_PATH_SKIP = frozenset(["show", "pod", "podcast", "episode"])

_HOSTING_PLATFORMS = [
    "libsyn.com", "podbean.com", "buzzsprout.com", "spreaker.com",
    "anchor.fm", "transistor.fm", "simplecast.com", "captivate.fm",
    "blubrry.com", "podomatic.com", "soundcloud.com", "megaphone.fm",
    "spotify.com",
]


# ---------------------------------------------------------------------------
# Public utilities
# ---------------------------------------------------------------------------

def transliterate(text: str) -> str:
    """Replace accented characters with their ASCII equivalents."""
    result = []
    for ch in text:
        result.append(_ACCENT_MAP.get(ch, ch))
    return "".join(result)


def normalize(text: str) -> str:
    """Transliterate, lowercase, and strip all non-alphanumeric characters."""
    return re.sub(r"[^a-z0-9]", "", transliterate(text.lower()))


def longest_common_substring(s1: str, s2: str) -> str:
    """Return the longest common substring of *s1* and *s2* (DP approach)."""
    if not s1 or not s2:
        return ""

    len1, len2 = len(s1), len(s2)
    # matrix[i][j] = length of LCS ending at s1[i-1], s2[j-1]
    matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    longest = ""

    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            if s1[i - 1] == s2[j - 1]:
                matrix[i][j] = matrix[i - 1][j - 1] + 1
                if matrix[i][j] > len(longest):
                    longest = s1[i - matrix[i][j]: i]

    return longest


def split_email(email: str) -> Optional[tuple[str, str]]:
    """
    Split an email address into (local_part, domain).
    Returns None if the address is malformed.
    """
    parts = email.split("@")
    if len(parts) != 2:
        return None
    return normalize(parts[0]), parts[1].lower()


def is_blacklisted_domain(domain: str, config: Config) -> bool:
    """Return True if *domain* is in the config blacklist."""
    return domain.lower() in config.blacklisted_domains


def extract_domain_brand(domain: str) -> str:
    """Return the normalized brand token from a domain (part before first dot)."""
    return normalize(domain.split(".")[0])


def get_meaningful_tokens(text: str) -> list[str]:
    """Tokenize *text*, normalize each token, and drop stop words."""
    tokens = []
    for token in text.lower().split():
        norm = normalize(token)
        if len(norm) > 2 and norm not in _STOP_WORDS:
            tokens.append(norm)
    return tokens


def is_hosting_platform_domain(domain: str) -> bool:
    """Return True if *domain* belongs to a known podcast hosting platform."""
    domain_lower = domain.lower()
    return any(platform in domain_lower for platform in _HOSTING_PLATFORMS)


def extract_base_domain(url: str) -> str:
    """Extract the base domain (e.g. 'acme.com') from a URL."""
    try:
        host = (
            url.lower()
            .replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
            .lstrip("www.")
        )
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) > 2 else host
    except Exception:
        return ""


def extract_subdomain(url: str) -> str:
    """Extract the subdomain portion from a URL (empty string if none)."""
    try:
        host = (
            url.lower()
            .replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
            .lstrip("www.")
        )
        parts = host.split(".")
        return ".".join(parts[:-2]) if len(parts) > 2 else ""
    except Exception:
        return ""


def extract_path_identifier(url: str) -> str:
    """
    Walk URL path segments from the end and return the first meaningful one
    (normalized, skipping generic podcast path words).
    """
    try:
        segments = (
            url.lower()
            .replace("https://", "")
            .replace("http://", "")
            .split("/")
        )
        for segment in reversed(segments):
            clean = re.sub(r"[^a-z0-9-]", "", segment)
            if len(clean) > 3 and clean not in _PATH_SKIP:
                return clean.replace("-", "")
        return ""
    except Exception:
        return ""


def extract_website_brand(url: str) -> str:
    """
    Derive a normalized brand token from a website URL.

    For hosting-platform URLs, falls back to subdomain then path identifier.
    For regular domains, uses the first label of the domain.
    """
    if not url:
        return ""

    domain = extract_base_domain(url)

    if is_hosting_platform_domain(domain):
        subdomain = extract_subdomain(url)
        if subdomain:
            return normalize(subdomain)
        path_id = extract_path_identifier(url)
        if path_id:
            return normalize(path_id)
        return ""

    return normalize(domain.split(".")[0]) if domain else ""


# ---------------------------------------------------------------------------
# EF-5: Name-variation generation and confidence-scored matching
# ---------------------------------------------------------------------------

# Variations considered "full name" → higher confidence on exact match
_FULL_NAME_VARIATION_INDICES = {0, 1, 6, 8, 9}  # first.last, firstlast, last.first, first_last, first-last


def _parse_name(full_name: str) -> dict:
    """
    Break *full_name* into structured components used by variation generation.
    Handles middle names (ignored) and hyphenated first names.
    """
    tokens = full_name.strip().split()
    if not tokens:
        return {}

    if len(tokens) == 1:
        word = tokens[0]
        sub = [p for p in re.split(r"-", word) if p]
        return {
            "first_raw": word,
            "last_raw": "",
            "first_norm": normalize(word),
            "last_norm": "",
            "first_initial": normalize(sub[0])[0] if sub and normalize(sub[0]) else "",
            "last_initial": "",
            "hyphenated_initials": "".join(normalize(p)[0] for p in sub if normalize(p)),
            "is_hyphenated": "-" in word,
        }

    first_raw = tokens[0]
    last_raw = tokens[-1]  # middle names ignored
    first_sub = [p for p in re.split(r"-", first_raw) if p]
    first_norm = normalize(first_raw)
    last_norm = normalize(last_raw)

    return {
        "first_raw": first_raw,
        "last_raw": last_raw,
        "first_norm": first_norm,
        "last_norm": last_norm,
        "first_initial": normalize(first_sub[0])[0] if first_sub and normalize(first_sub[0]) else (first_norm[0] if first_norm else ""),
        "last_initial": last_norm[0] if last_norm else "",
        "hyphenated_initials": "".join(normalize(p)[0] for p in first_sub if normalize(p)),
        "is_hyphenated": "-" in first_raw,
    }


def generate_name_variations(full_name: str) -> list[str]:
    """
    Generate a list of plausible email local-part patterns for *full_name*.

    Handles hyphenated first names, middle names (ignored), and accented
    characters (via normalize).  Returns a deduplicated, ordered list.
    """
    p = _parse_name(full_name)
    if not p:
        return []

    first = p["first_norm"]
    last = p["last_norm"]
    fi = p["first_initial"]
    li = p["last_initial"]

    if not last:
        return [first] if first else []

    variations: list[str] = [
        f"{first}.{last}",    # first.last
        f"{first}{last}",     # firstlast
        f"{fi}{last}",        # flast
        f"{first}{li}",       # firstl
        first,                # first
        last,                 # last
        f"{last}.{first}",    # last.first
        f"{fi}.{last}",       # f.last
        f"{first}_{last}",    # first_last
        f"{first}-{last}",    # first-last
        f"{last}{fi}",        # lastf
    ]

    if p["is_hyphenated"]:
        initials = p["hyphenated_initials"]
        if initials:
            variations.append(initials)          # e.g. "mj"
        raw_lower = p["first_raw"].lower()
        variations.append(raw_lower)             # e.g. "mary-jane"

    # Deduplicate preserving order, drop empty strings
    seen: set[str] = set()
    result: list[str] = []
    for v in variations:
        if v and v not in seen:
            seen.add(v)
            result.append(v)
    return result


def _brand_confidence(domain: str, company_name: Optional[str], podcast_name: Optional[str], lcs_min: int) -> float:
    """
    Return brand-match confidence (0.3–0.5) if the domain or local part
    matches a brand derived from *company_name* or *podcast_name*.
    Returns 0.0 if no brand match is found.
    """
    domain_brand = extract_domain_brand(domain)
    brand_sources: list[str] = []

    for name in filter(None, [company_name, podcast_name]):
        brand_sources.append(normalize(name))
        brand_sources.extend(get_meaningful_tokens(name))

    for brand in brand_sources:
        if not brand or len(brand) < lcs_min:
            continue
        lcs = longest_common_substring(domain_brand, brand)
        if len(lcs) >= lcs_min:
            return 0.4  # domain matches a brand → brand_match

    return 0.0


def match_email_to_name(
    email: str,
    full_name: str,
    company_name: Optional[str] = None,
    podcast_name: Optional[str] = None,
    config: Optional[Config] = None,
) -> dict:
    """
    Score how likely *email* belongs to *full_name*.

    Returns a dict with keys:
      - ``confidence``        float 0.0–1.0
      - ``match_type``        "name_exact" | "name_lcs" | "brand_match" | "no_match"
      - ``matched_variation`` the variation that triggered the match (or "")
      - ``details``           human-readable explanation
    """
    lcs_min: int = config.lcs_min_length if config else 4
    name_threshold: float = config.name_match_threshold if config else 0.6
    generic_prefixes: list = config.generic_email_prefixes if config else [
        "info", "support", "hello", "contact", "admin",
        "team", "office", "sales", "help", "media",
    ]

    no_match = {"confidence": 0.0, "match_type": "no_match", "matched_variation": "", "details": "no match found"}

    parsed = split_email(email.lower())
    if parsed is None:
        return no_match
    local_norm, domain = parsed  # local_norm already normalized by split_email

    variations = generate_name_variations(full_name)

    # --- 1. Exact name match (normalize both sides for fair comparison) ---
    for idx, variation in enumerate(variations):
        var_norm = normalize(variation)
        if var_norm and var_norm == local_norm:
            confidence = 0.95 if idx in _FULL_NAME_VARIATION_INDICES else 0.85
            return {
                "confidence": confidence,
                "match_type": "name_exact",
                "matched_variation": variation,
                "details": f"local part '{local_norm}' exact match with name variation '{variation}'",
            }

    # --- 2. LCS name match ---
    best_lcs_conf = 0.0
    best_lcs_var = ""
    best_lcs_str = ""
    for variation in variations:
        var_norm = normalize(variation)
        if not var_norm:
            continue
        lcs = longest_common_substring(local_norm, var_norm)
        if len(lcs) < lcs_min:
            continue
        ratio = len(lcs) / max(len(local_norm), len(var_norm))
        if ratio >= name_threshold:
            conf = 0.6 + 0.2 * ratio  # scales from 0.6 to ~0.8
            if conf > best_lcs_conf:
                best_lcs_conf = conf
                best_lcs_var = variation
                best_lcs_str = lcs

    if best_lcs_conf > 0.0:
        return {
            "confidence": round(best_lcs_conf, 4),
            "match_type": "name_lcs",
            "matched_variation": best_lcs_var,
            "details": f"LCS '{best_lcs_str}' between local '{local_norm}' and variation '{best_lcs_var}'",
        }

    # --- 3. Brand match (skip generic prefixes) ---
    if local_norm not in generic_prefixes:
        brand_conf = _brand_confidence(domain, company_name, podcast_name, lcs_min)
        if brand_conf > 0.0:
            return {
                "confidence": brand_conf,
                "match_type": "brand_match",
                "matched_variation": "",
                "details": f"domain '{domain}' matches brand from company/podcast name",
            }

    # Generic-prefix local → brand match at lower confidence
    if local_norm in generic_prefixes:
        brand_conf = _brand_confidence(domain, company_name, podcast_name, lcs_min)
        if brand_conf > 0.0:
            return {
                "confidence": 0.3,
                "match_type": "brand_match",
                "matched_variation": "",
                "details": f"generic prefix '{local_norm}' with domain brand match — low confidence",
            }

    return no_match


# ---------------------------------------------------------------------------
# EF-6: Public interface
# ---------------------------------------------------------------------------

def verify_email_ownership(lead: "LeadInput", config: Optional[Config] = None) -> "NodeResult":  # noqa: F821
    """
    Check if lead.existing_email likely belongs to the lead.

    Uses name matching + brand matching from EF-4 and EF-5.

    Args:
        lead: LeadInput with existing_email set.
        config: Optional Config instance (loaded from env if None).

    Returns:
        NodeResult with:
        - confidence: 0.0–1.0 ownership score
        - data: {"match_type": ..., "matched_variation": ..., "details": ...}
        - error: set when email is absent or from a blacklisted domain
    """

    if not lead.existing_email:
        return NodeResult(confidence=0.0, error="no existing_email on lead")

    parsed = split_email(lead.existing_email)
    if parsed is None:
        return NodeResult(confidence=0.0, error="malformed email address")

    _, domain = parsed

    if is_blacklisted_domain(domain, config) if config else domain in [
        "spreaker.com", "anchor.fm", "spotify.com", "podcasters.spotify.com",
        "simplecast.com", "buzzsprout.com", "libsyn.com", "podbean.com",
        "transistor.fm", "redcircle.com", "megaphone.fm", "omny.fm",
    ]:
        return NodeResult(confidence=0.0, error="hosting platform email")

    result = match_email_to_name(
        email=lead.existing_email,
        full_name=lead.full_name,
        company_name=lead.company_name,
        podcast_name=lead.podcast_name,
        config=config,
    )

    return NodeResult(
        found_email=lead.existing_email,
        confidence=result["confidence"],
        data={
            "match_type": result["match_type"],
            "matched_variation": result["matched_variation"],
            "details": result["details"],
        },
    )


def extract_brand_candidates(podcast_name: str, website: str) -> list[dict]:
    """
    Build a list of brand candidate dicts (``{"value": str, "source": str}``)
    from the podcast name and website URL.

    Mirrors ``extractBrandCandidates`` from the Google Apps Script.
    """
    candidates: list[dict] = []

    # Full normalized podcast name
    podcast_norm = normalize(podcast_name)
    if len(podcast_norm) >= 4:
        candidates.append({"value": podcast_norm, "source": "podcast name"})

    # Individual meaningful tokens from podcast name
    for token in get_meaningful_tokens(podcast_name):
        if len(token) >= 4:
            candidates.append({"value": token, "source": "podcast token"})

    # Brand from website
    website_brand = extract_website_brand(website)
    if website_brand and len(website_brand) >= 4:
        candidates.append({"value": website_brand, "source": "website"})

    return candidates
