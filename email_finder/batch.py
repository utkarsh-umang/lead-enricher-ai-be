"""
Batch email-finding orchestrator.

Primary notebook entry point: ``find_emails_batch(leads, config)``

Runs each lead through the discovery waterfall and returns the discovered
candidates. Deliverability verification has been removed from the pipeline —
results are returned with status ``"unverified"`` (a candidate was found) or
``"not_found"``. Any verification is expected to happen as a separate step.
"""

from __future__ import annotations

import logging
from typing import Optional

from email_finder.config import Config, get_config
from email_finder.models import EmailFinderResult, LeadInput
from email_finder.finder import find_email

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_candidates(result: EmailFinderResult) -> list[str]:
    """Return the full candidate list stored in verification_details."""
    return result.verification_details.get("all_candidates", [])


def _print(msg: str) -> None:
    """Print to stdout — visible in Jupyter notebooks."""
    print(msg)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

async def discover_leads(
    leads: list[LeadInput],
    config: Optional[Config] = None,
) -> list[EmailFinderResult]:
    """
    Run each lead through the discovery waterfall.

    Returns a list of EmailFinderResult with ``status`` in
    ``{"unverified", "not_found"}``. All candidate emails are in
    ``result.verification_details["all_candidates"]``.
    """
    if config is None:
        config = get_config()

    total = len(leads)
    _print(f"Starting email discovery for {total} lead(s) …\n")

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

        if result.email:
            _print(f"  → candidate: {result.email}")
        elif result.status == "not_found":
            _print(f"  → no candidates found")

        results.append(result)

    return results


def collect_candidates(results: list[EmailFinderResult]) -> list[str]:
    """Return a deduplicated sorted list of all candidate emails across all results."""
    all_candidates_set: set[str] = set()
    for result in results:
        if result.email:
            all_candidates_set.add(result.email.lower())
        for c in _all_candidates(result):
            all_candidates_set.add(c.lower())
    return sorted(all_candidates_set)


# ---------------------------------------------------------------------------
# All-in-one entry point (kept for backwards compat)
# ---------------------------------------------------------------------------

async def find_emails_batch(
    leads: list[LeadInput],
    config: Optional[Config] = None,
) -> list[EmailFinderResult]:
    """
    Process a list of leads through the discovery waterfall.

    Verification has been removed — every result with an email carries
    status ``"unverified"``.

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

    results = await discover_leads(leads, config)

    final_counts: dict[str, int] = {}
    for r in results:
        final_counts[r.status] = final_counts.get(r.status, 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in final_counts.items())
    _print(f"\n[Results] {len(leads)} lead(s) processed: {summary}.")

    return results
