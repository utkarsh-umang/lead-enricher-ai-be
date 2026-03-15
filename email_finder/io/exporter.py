"""
EF-18: CSV Output Splitter — Found vs Not Found.

Takes ``EmailFinderResult`` list from ``find_emails_batch()`` and writes two CSVs:
  - enriched.csv          — leads where an email was found/verified
  - still_needs_enrichment.csv — leads where no email could be determined
"""

from __future__ import annotations

import datetime
import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd

from email_finder.models import EmailFinderResult, LeadInput

logger = logging.getLogger(__name__)

# Statuses that mean "we found something usable"
_FOUND_STATUSES = {"verified", "unverified", "catch_all"}
_NOT_FOUND_STATUSES = {"not_found", "invalid"}


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------

def _enriched_row(lead: LeadInput, result: EmailFinderResult) -> dict:
    return {
        "full_name": lead.full_name,
        "company_name": lead.company_name or "",
        "company_domain": lead.company_domain or "",
        "email": result.email or "",
        "email_status": result.status,
        "email_confidence": round(result.confidence, 4),
        "email_source": result.source,
        "podcast_name": lead.podcast_name or "",
        "website": lead.website or "",
        "linkedin_url": lead.linkedin_url or "",
        "twitter_url": lead.twitter_url or "",
        "facebook_url": lead.facebook_url or "",
        "youtube_url": lead.youtube_url or "",
        "instagram_url": lead.instagram_url or "",
    }


def _failure_reason(result: EmailFinderResult) -> str:
    """Derive a human-readable failure reason from the discovery log."""
    log = result.discovery_log or []
    nodes_run = [e.get("node", "") for e in log]

    if not nodes_run:
        return "no discovery attempted"

    # Check whether any node found a domain
    domain_found = any(
        e.get("result", {}).get("data_keys") and
        any(k in ("company_domain", "website") for k in e["result"].get("data_keys", []))
        for e in log
    )

    if "pattern_gen" in nodes_run and not result.email:
        return "all patterns invalid"
    if not domain_found:
        return "no domain found"
    return "all strategies exhausted"


def _nodes_tried(result: EmailFinderResult) -> str:
    log = result.discovery_log or []
    return ", ".join(e.get("node", "") for e in log)


def _discovered_fields(result: EmailFinderResult) -> dict:
    """Pull any domain/social data surfaced in the discovery log."""
    discovered: dict = {
        "discovered_domain": "",
        "discovered_linkedin": "",
        "discovered_socials": "",
    }
    socials: list[str] = []
    for entry in (result.discovery_log or []):
        data_keys = entry.get("result", {}).get("data_keys", [])
        # We can't recover the actual values from log entries (only keys are stored),
        # but verification_details may carry them.
    # Pull from verification_details if available
    vd = result.verification_details or {}
    discovered["discovered_domain"] = vd.get("company_domain", "")
    discovered["discovered_linkedin"] = vd.get("linkedin_url", "")
    discovered["discovered_socials"] = vd.get("social_urls", "")
    return discovered


def _still_needs_row(lead: LeadInput, result: EmailFinderResult) -> dict:
    disc = _discovered_fields(result)
    return {
        "full_name": lead.full_name,
        "company_name": lead.company_name or "",
        "company_domain": lead.company_domain or "",
        "existing_email": lead.existing_email or "",
        "failure_reason": _failure_reason(result),
        "nodes_tried": _nodes_tried(result),
        "podcast_name": lead.podcast_name or "",
        "website": lead.website or "",
        "linkedin_url": lead.linkedin_url or "",
        "twitter_url": lead.twitter_url or "",
        "facebook_url": lead.facebook_url or "",
        "youtube_url": lead.youtube_url or "",
        "instagram_url": lead.instagram_url or "",
        "discovered_domain": disc["discovered_domain"],
        "discovered_linkedin": disc["discovered_linkedin"],
        "discovered_socials": disc["discovered_socials"],
    }


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def _print_summary(
    leads: list[LeadInput],
    results: list[EmailFinderResult],
    enriched_path: str,
    needs_path: str,
    enriched_rows: list[dict],
    needs_rows: list[dict],
) -> None:
    total = len(results)
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1

    enriched_count = len(enriched_rows)
    needs_count = len(needs_rows)
    enriched_pct = round(enriched_count / total * 100) if total else 0
    needs_pct = 100 - enriched_pct

    print("\n=== Email Finder Results ===")
    print(f"Total leads processed: {total}")
    print(f"Enriched (email found): {enriched_count} ({enriched_pct}%)")
    for status in ("verified", "catch_all", "unverified"):
        count = by_status.get(status, 0)
        if count:
            print(f"  - {status.replace('_', '-').capitalize()}: {count}")
    print(f"Still needs enrichment: {needs_count} ({needs_pct}%)")
    for status in ("not_found", "invalid"):
        count = by_status.get(status, 0)
        if count:
            label = "No email found" if status == "not_found" else "Invalid email"
            print(f"  - {label}: {count}")

    print(f"\nFiles written:")
    print(f"  - {enriched_path} ({enriched_count} rows)")
    print(f"  - {needs_path} ({needs_count} rows)")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_results(
    leads: list[LeadInput],
    results: list[EmailFinderResult],
    output_dir: str = "./output",
    prefix: Optional[str] = None,
) -> dict[str, str]:
    """
    Split results into two CSVs based on whether an email was found.

    Args:
        leads:      Original LeadInput list (same order as results).
        results:    Corresponding EmailFinderResult list.
        output_dir: Directory to write output CSVs (created if needed).
        prefix:     Optional filename prefix; defaults to today's date (YYYY-MM-DD).

    Returns:
        {"enriched": "/abs/path/enriched.csv",
         "needs_enrichment": "/abs/path/still_needs_enrichment.csv"}
    """
    if len(leads) != len(results):
        raise ValueError(
            f"leads ({len(leads)}) and results ({len(results)}) must have the same length."
        )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    date_str = prefix or datetime.date.today().isoformat()

    enriched_rows: list[dict] = []
    needs_rows: list[dict] = []

    for lead, result in zip(leads, results):
        if result.status in _FOUND_STATUSES:
            enriched_rows.append(_enriched_row(lead, result))
        else:
            needs_rows.append(_still_needs_row(lead, result))

    enriched_path = str(out / f"{date_str}_enriched.csv")
    needs_path = str(out / f"{date_str}_still_needs_enrichment.csv")

    pd.DataFrame(enriched_rows).to_csv(enriched_path, index=False)
    pd.DataFrame(needs_rows).to_csv(needs_path, index=False)

    logger.info("Exported %d enriched and %d needs-enrichment rows.", len(enriched_rows), len(needs_rows))
    _print_summary(leads, results, enriched_path, needs_path, enriched_rows, needs_rows)

    return {"enriched": enriched_path, "needs_enrichment": needs_path}
