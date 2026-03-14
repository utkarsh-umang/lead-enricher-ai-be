"""
Batch email-finding orchestrator with Mailin integration.

Primary notebook entry point: ``find_emails_batch(leads, config)``

Three phases:
  1. Discovery  — run each lead through the waterfall (EF-14).
  2. Verification — one Mailin bulk-verify call for all candidates (EF-12).
  3. Resolution — map Mailin statuses back; handle catch-all (EF-13).
"""

from __future__ import annotations

import logging
from typing import Optional

from email_finder.config import Config, get_config
from email_finder.models import EmailFinderResult, LeadInput
from email_finder.finder import find_email
from email_finder.verification.mailin_automator import mailin_batch_verify

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_candidates(result: EmailFinderResult) -> list[str]:
    """Return the full candidate list stored in verification_details."""
    return result.verification_details.get("all_candidates", [])


def _lead_patterns(
    leads: list[LeadInput],
    results: list[EmailFinderResult],
) -> dict[str, list[str]]:
    """Build the lead_patterns dict required by resolve_catch_all_domains."""
    return {
        lead.full_name: _all_candidates(result)
        for lead, result in zip(leads, results)
    }


def _print(msg: str) -> None:
    """Print to stdout — visible in Jupyter notebooks."""
    print(msg)


# ---------------------------------------------------------------------------
# Phase 3 helpers
# ---------------------------------------------------------------------------

def _resolve_result(
    result: EmailFinderResult,
    verification_map: dict[str, str],
) -> EmailFinderResult:
    """
    Apply Mailin statuses to a single result, falling back to alternative
    candidates when the primary email is invalid.
    """
    primary = (result.email or "").lower()
    mailin_status = verification_map.get(primary)

    if mailin_status == "valid":
        result.status = "verified"
        result.confidence = max(result.confidence, 0.9)

    elif mailin_status == "invalid":
        result.status = "invalid"
        result.confidence = 0.0
        # Try alternatives in priority order
        for alt in _all_candidates(result):
            if verification_map.get(alt.lower()) == "valid":
                result.email = alt.lower()
                result.status = "verified"
                result.confidence = 0.85
                break

    elif mailin_status == "catch_all":
        result.status = "catch_all"
        result.confidence = min(result.confidence, 0.5)

    elif primary and mailin_status is None:
        # Candidate was not in the verification map — treat as unknown
        result.status = "unverified"

    return result


def _apply_catch_all_resolution(
    leads: list[LeadInput],
    results: list[EmailFinderResult],
    verification_map: dict[str, str],
) -> list[EmailFinderResult]:
    """
    Run EF-13 catch-all resolution and update results in-place.
    Only affects leads whose primary status is "catch_all".
    """
    from email_finder.verification.mailin_automator import resolve_catch_all_domains

    patterns = _lead_patterns(leads, results)
    resolved = resolve_catch_all_domains(verification_map, patterns)

    for lead, result in zip(leads, results):
        if result.status != "catch_all":
            continue
        resolution = resolved.get(lead.full_name)
        if not resolution:
            continue
        result.email = resolution["email"]
        result.confidence = resolution["confidence"]
        result.verification_details["is_catch_all"] = resolution["is_catch_all"]

    return results


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def find_emails_batch(
    leads: list[LeadInput],
    config: Optional[Config] = None,
) -> list[EmailFinderResult]:
    """
    Process a list of leads through discovery + Mailin batch verification.

    Args:
        leads:  List of LeadInput objects (loaded from sheet, CSV, etc.).
        config: Optional Config; loaded from env if not provided.

    Returns:
        List of EmailFinderResult in the same order as *leads*.

    Notebook usage::

        results = await find_emails_batch(leads)
        # results[i].email, results[i].status, results[i].confidence
    """
    if config is None:
        config = get_config()

    total = len(leads)
    _print(f"Starting email discovery for {total} lead(s) …\n")

    # -----------------------------------------------------------------------
    # Phase 1: Discovery (sequential)
    # -----------------------------------------------------------------------
    results: list[EmailFinderResult] = []

    for i, lead in enumerate(leads, 1):
        _print(f"[{i}/{total}] {lead.full_name} — searching …")
        try:
            result = await find_email(lead, config)
        except Exception as exc:
            logger.error("find_email failed for %s: %s", lead.full_name, exc)
            result = EmailFinderResult(
                email=None,
                status="not_found",
                confidence=0.0,
                source="error",
                discovery_log=[{"node": "orchestrator", "error": str(exc)}],
            )

        # Progress detail
        if result.email:
            _print(f"  → candidate: {result.email}")
        elif result.status == "not_found":
            _print(f"  → no candidates found")

        results.append(result)

    # -----------------------------------------------------------------------
    # Phase 2: Collect all candidates → one Mailin batch
    # -----------------------------------------------------------------------
    all_candidates_set: set[str] = set()
    for result in results:
        if result.email:
            all_candidates_set.add(result.email.lower())
        for c in _all_candidates(result):
            all_candidates_set.add(c.lower())

    all_candidates_list = sorted(all_candidates_set)
    _print(f"\n[Mailin] Uploading {len(all_candidates_list)} candidate(s) for verification …")

    try:
        verification_map: dict[str, str] = await mailin_batch_verify(
            all_candidates_list, config
        )
    except Exception as exc:
        logger.error("Mailin batch verification failed: %s", exc)
        _print(f"[Mailin] Verification failed: {exc} — returning unverified results.")
        verification_map = {}

    # Summary counts
    status_counts: dict[str, int] = {}
    for status in verification_map.values():
        status_counts[status] = status_counts.get(status, 0) + 1
    summary_parts = ", ".join(f"{v} {k}" for k, v in status_counts.items())
    _print(f"[Mailin] Verification complete. {summary_parts or 'no results'}.")

    # -----------------------------------------------------------------------
    # Phase 3: Resolution
    # -----------------------------------------------------------------------
    for result in results:
        _resolve_result(result, verification_map)

    results = _apply_catch_all_resolution(leads, results, verification_map)

    # Final summary
    final_counts: dict[str, int] = {}
    for r in results:
        final_counts[r.status] = final_counts.get(r.status, 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in final_counts.items())
    _print(f"\n[Results] {total} lead(s) processed: {summary}.")

    return results
