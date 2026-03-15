# EF-14: Single Lead Waterfall Logic

**Epic**: Epic 8 — Orchestration
**Priority**: Highest
**Depends On**: EF-6, EF-7, EF-9, EF-10, EF-11

## Description

Implement the core waterfall logic in `email_finder/finder.py` that processes a single lead through Flow A or Flow B, collecting email candidates along the way.

## Implementation

```python
async def find_email(lead: LeadInput, config: Config = None) -> EmailFinderResult:
    """
    Process a single lead through the email finding waterfall.
    Does NOT run Mailin verification (that's the batch step in EF-15).

    Returns EmailFinderResult with best candidate email and discovery log.
    """
```

### Flow A: Lead HAS existing_email (hosts)

```python
async def _flow_a_verify(lead: LeadInput, config: Config) -> EmailFinderResult:
    log = []

    # Step 1: Name-email ownership matching
    match_result = verify_email_ownership(lead, config)
    log.append({"node": "name_matcher", "result": match_result})

    # Step 2: Perplexity cross-reference (also discovers domain/profiles)
    perplexity_result = await perplexity_search(lead, config)
    log.append({"node": "perplexity", "result": perplexity_result})

    # Merge discovered data into lead context for downstream use
    # (e.g., if perplexity found domain, pattern gen can use it)

    # Step 3: If ownership confidence is low, also run Flow B for alternatives
    if match_result.confidence < config.name_match_threshold:
        alt_result = await _flow_b_find(lead_with_discoveries, config)
        # Collect alternative candidates alongside existing email

    # Collect existing_email for Mailin batch verification
    return EmailFinderResult(
        email=lead.existing_email,
        status="pending_verification",  # Will be updated after Mailin batch
        confidence=match_result.confidence,
        source="existing",
        discovery_log=log
    )
```

### Flow B: Lead has NO email (guests, or hosts with invalid email)

```python
async def _flow_b_find(lead: LeadInput, config: Config) -> EmailFinderResult:
    log = []
    candidates = []

    # Step 1: Perplexity search (cheapest — find email, domain, profiles)
    perplexity_result = await perplexity_search(lead, config)
    log.append({"node": "perplexity", "result": perplexity_result})
    if perplexity_result.found_email:
        candidates.append(perplexity_result.found_email)
    # Merge discovered domain/profiles into lead context

    # Step 2: Website scraping (if domain known/discovered)
    if lead_context.company_domain:
        scrape_result = await scrape_website_for_emails(lead_context, config)
        log.append({"node": "website_scraper", "result": scrape_result})
        candidates.extend(scrape_result.found_emails)

    # Step 3: Pattern generation (if domain known/discovered)
    if lead_context.company_domain:
        pattern_result = await generate_patterns(lead_context, config)
        log.append({"node": "pattern_gen", "result": pattern_result})
        candidates.extend(pattern_result.found_emails)

    # Step 4: Browser discovery (last resort — high cost)
    if not candidates:  # Only if nothing found yet
        browser_result = await browser_discover_email(lead_context, config)
        log.append({"node": "browser_discovery", "result": browser_result})
        candidates.extend(browser_result.found_emails)

    return EmailFinderResult(
        email=candidates[0] if candidates else None,
        status="pending_verification" if candidates else "not_found",
        source=log[-1]["node"] if candidates else "",
        discovery_log=log,
        _all_candidates=candidates  # Internal: for Mailin batch
    )
```

### Discovery Data Propagation

As each node runs, merge its discoveries into a working context:
- Perplexity finds `company_domain` → website_scraper and pattern_generator can use it
- Perplexity finds `facebook_url` → browser_discovery scrapes it directly
- Website scraper finds emails → added to candidates

## Acceptance Criteria

- [ ] Lead with existing_email goes through Flow A
- [ ] Lead without email goes through Flow B
- [ ] Flow A with low confidence also triggers Flow B for alternatives
- [ ] Discovered data (domain, social URLs) propagates to downstream nodes
- [ ] Browser discovery only runs if earlier nodes found nothing
- [ ] Discovery log tracks every node's action and result
- [ ] All candidate emails collected for Mailin batch step
