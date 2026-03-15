"""
Single-lead email-finder waterfall orchestrator.

Entry point: ``find_email(lead, config)``

Two flows:
  Flow A — lead HAS existing_email (podcast hosts).
    1. Name-email ownership matching (EF-6).
    2. Perplexity cross-reference — also discovers domain / social URLs.
    3. If ownership confidence < threshold → also run Flow B for alternatives.

  Flow B — lead has NO email (guests, or hosts whose email failed ownership).
    1. Perplexity search.
    2. Website scraper (if domain known/discovered).
    3. Pattern generator (if domain known/discovered).
    4. Browser discovery (last resort — only if nothing found yet).

A ``DiscoveryContext`` (EF-16) accumulates findings from each node and
propagates them to subsequent nodes so that, e.g., a domain found by
Perplexity is automatically available to the website scraper and pattern
generator.

NOTE: Mailin batch verification is NOT run here — that's EF-15.
      This function returns status="pending_verification" for all candidates.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from email_finder.config import Config, get_config
from email_finder.models import DiscoveryContext, EmailFinderResult, LeadInput, NodeResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.datetime.utcnow().isoformat()


def _log_entry(node: str, result: NodeResult) -> dict:
    entry_result: dict = {
        "found_email": result.found_email,
        "found_emails": result.found_emails,
        "confidence": result.confidence,
        "error": result.error,
        "data_keys": list(result.data.keys()),
    }
    # Include Perplexity prompt + raw response for debugging
    if "raw_response" in result.data:
        entry_result["prompt"] = result.data.get("prompt", "")
        entry_result["raw_response"] = result.data["raw_response"]
    return {
        "node": node,
        "action": "run",
        "result": entry_result,
        "timestamp": _ts(),
    }


# ---------------------------------------------------------------------------
# Flow B — discover email from scratch
# ---------------------------------------------------------------------------

async def _flow_b_find(
    lead: LeadInput,
    config: Config,
    log: list,
    ctx: DiscoveryContext,
) -> DiscoveryContext:
    """
    Run discovery nodes in waterfall order.

    Mutates *log* and *ctx* in place; returns the same context (enriched).
    Each node receives the latest enriched lead via ``ctx.to_lead(lead)``.
    """
    from email_finder.discovery.perplexity_search import perplexity_search
    from email_finder.discovery.website_scraper import scrape_website_for_emails
    from email_finder.discovery.pattern_generator import generate_patterns
    from email_finder.discovery.browser_discovery import browser_discover_email

    # Step 1: Perplexity
    perplexity_result = await perplexity_search(ctx.to_lead(lead), config)
    log.append(_log_entry("perplexity", perplexity_result))
    ctx.merge_node_result("perplexity", perplexity_result)

    # Step 2: Website scraping (needs domain)
    if ctx.has_domain():
        scrape_result = await scrape_website_for_emails(ctx.to_lead(lead), config)
        log.append(_log_entry("website_scraper", scrape_result))
        ctx.merge_node_result("website_scraper", scrape_result)

    # Step 3: Pattern generation (needs domain)
    if ctx.has_domain():
        pattern_result = await generate_patterns(ctx.to_lead(lead), config)
        log.append(_log_entry("pattern_gen", pattern_result))
        ctx.merge_node_result("pattern_gen", pattern_result)

    # Step 4: Browser discovery — last resort, only if nothing found yet
    if not ctx.candidate_emails:
        browser_result = await browser_discover_email(ctx.to_lead(lead), config)
        log.append(_log_entry("browser_discovery", browser_result))
        ctx.merge_node_result("browser_discovery", browser_result)

    return ctx


# ---------------------------------------------------------------------------
# Flow A — verify existing email
# ---------------------------------------------------------------------------

async def _flow_a_verify(lead: LeadInput, config: Config) -> EmailFinderResult:
    from email_finder.verification.name_email_matcher import verify_email_ownership
    from email_finder.discovery.perplexity_search import perplexity_search

    ctx = DiscoveryContext.from_lead(lead)
    log: list = []

    # Step 1: Name-email ownership matching
    match_result = verify_email_ownership(lead, config)
    log.append({
        "node": "name_matcher",
        "action": "run",
        "result": {
            "confidence": match_result.confidence,
            "match_type": match_result.data.get("match_type"),
            "error": match_result.error,
        },
        "timestamp": _ts(),
    })
    ctx.nodes_completed.append("name_matcher")

    # Always include existing_email as first candidate
    if lead.existing_email:
        ctx.candidate_emails.append(lead.existing_email.lower())

    # Step 2: Perplexity cross-reference (enriches domain/profiles)
    perplexity_result = await perplexity_search(ctx.to_lead(lead), config)
    log.append(_log_entry("perplexity", perplexity_result))
    ctx.merge_node_result("perplexity", perplexity_result)

    # Step 3: If ownership confidence is below threshold, also run Flow B
    if match_result.confidence < config.name_match_threshold:
        logger.info(
            "Flow A confidence %.2f < threshold %.2f — running Flow B for alternatives.",
            match_result.confidence, config.name_match_threshold,
        )
        ctx = await _flow_b_find(lead, config, log, ctx)

    unique_candidates = list(dict.fromkeys(ctx.candidate_emails))  # stable-dedup
    best_email = unique_candidates[0] if unique_candidates else lead.existing_email

    return EmailFinderResult(
        email=best_email,
        status="pending_verification",
        confidence=match_result.confidence,
        source="existing",
        discovery_log=log,
        verification_details={
            "all_candidates": unique_candidates,
            "match_type": match_result.data.get("match_type", ""),
        },
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def find_email(
    lead: LeadInput,
    config: Optional[Config] = None,
) -> EmailFinderResult:
    """
    Process a single lead through the email-finding waterfall.

    Does NOT run Mailin verification — that is the batch step (EF-15).
    Returns ``EmailFinderResult`` with:
      - ``email``: best candidate
      - ``status``: ``"pending_verification"`` or ``"not_found"``
      - ``confidence``: ownership / match confidence
      - ``discovery_log``: ordered list of node results
      - ``verification_details["all_candidates"]``: full candidate list for
        the Mailin batch step
    """
    if config is None:
        config = get_config()

    if lead.existing_email:
        return await _flow_a_verify(lead, config)

    # Flow B
    ctx = DiscoveryContext.from_lead(lead)
    log: list = []
    ctx = await _flow_b_find(lead, config, log, ctx)

    unique_candidates = list(dict.fromkeys(ctx.candidate_emails))

    # Source = last node that contributed candidates
    source = ""
    for entry in reversed(log):
        if entry["result"].get("found_email") or entry["result"].get("found_emails"):
            source = entry["node"]
            break

    return EmailFinderResult(
        email=unique_candidates[0] if unique_candidates else None,
        status="pending_verification" if unique_candidates else "not_found",
        confidence=0.0,
        source=source,
        discovery_log=log,
        verification_details={"all_candidates": unique_candidates},
    )
