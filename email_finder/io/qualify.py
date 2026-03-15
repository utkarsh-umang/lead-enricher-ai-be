"""
Email qualification — thin wrapper over name_email_matcher (EF-4/EF-5/EF-6).

Decides whether a lead's existing_email is worth keeping as a Flow A candidate,
or should be discarded so the finder runs Flow B (full discovery) instead.

Three-tier rule (same as the Google Apps Script qualifyPodcastLeads):
  1. Hosting-platform domain → always DROP  (spreaker, buzzsprout, podbean, etc.)
  2. Personal email provider → always KEEP  (gmail, me.com, outlook, etc.)
  3. Custom/company domain   → LCS brand check: keep only if the email local
     part or domain brand shares ≥ 4 chars with any brand candidate derived
     from the podcast name + website (e.g. myrockerbeez.com fails for
     "A Mommy And A Mic").
"""

from __future__ import annotations

from typing import Optional

from email_finder.models import LeadInput
from email_finder.verification.name_email_matcher import (
    extract_brand_candidates,
    is_hosting_platform_domain,
    longest_common_substring,
    normalize,
    split_email,
)

_MIN_LCS = 4

# Common personal email providers — the host's personal address is always valid
_PERSONAL_DOMAINS: frozenset[str] = frozenset({
    "gmail.com", "yahoo.com", "yahoo.co.uk", "hotmail.com", "hotmail.co.uk",
    "outlook.com", "live.com", "icloud.com", "me.com", "mac.com",
    "aol.com", "protonmail.com", "pm.me", "hey.com", "fastmail.com",
    "zoho.com", "ymail.com", "msn.com",
})


def is_email_qualified(
    email: str,
    podcast_name: str,
    website: str = "",
) -> tuple[bool, str]:
    """
    Return (qualified, reason) for an email against a podcast lead.

    Args:
        email:        Candidate email address.
        podcast_name: Lead's full_name / podcast name.
        website:      Lead's website URL (optional but improves matching).

    Returns:
        (True, "")           — keep the email (use Flow A)
        (False, "<reason>")  — discard the email (use Flow B)
    """
    parsed = split_email(email.strip().lower())
    if parsed is None:
        return False, "malformed email address"

    local_norm, domain = parsed

    # 1. Hosting-platform blacklist (is_hosting_platform_domain covers the same set)
    if is_hosting_platform_domain(domain):
        return False, f"domain '{domain}' is a podcast hosting platform"

    # 2. Personal provider fast-pass
    if domain in _PERSONAL_DOMAINS:
        return True, ""

    # 3. Brand LCS check for custom/company domains
    candidates = extract_brand_candidates(podcast_name, website or "")
    domain_brand = normalize(domain.split(".")[0])

    best_lcs = 0
    for c in candidates:
        value = c["value"]
        best_lcs = max(
            best_lcs,
            len(longest_common_substring(value, local_norm)),
            len(longest_common_substring(value, domain_brand)),
        )

    if best_lcs < _MIN_LCS:
        candidate_values = [c["value"] for c in candidates]
        return False, (
            f"domain '{domain}' is not a personal provider and "
            f"LCS={best_lcs} < {_MIN_LCS} "
            f"(doesn't match brand candidates {candidate_values})"
        )

    return True, ""


def qualify_lead_email(lead: LeadInput) -> tuple[LeadInput, Optional[str]]:
    """
    Qualify the lead's existing_email.

    If the email fails qualification, returns a copy of the lead with
    ``existing_email=None`` so the finder runs Flow B instead of Flow A.

    Returns:
        (lead_or_copy, discard_reason)   — discard_reason is None when kept.
    """
    if not lead.existing_email:
        return lead, None

    qualified, reason = is_email_qualified(
        lead.existing_email,
        lead.full_name,
        lead.website or "",
    )
    if qualified:
        return lead, None

    return lead.model_copy(update={"existing_email": None}), reason
