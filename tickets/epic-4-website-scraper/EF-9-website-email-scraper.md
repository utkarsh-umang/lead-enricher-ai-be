# EF-9: Website Email Scraper Node

**Epic**: Epic 4 — Website Email Extraction
**Priority**: Medium
**Depends On**: EF-1, EF-2

## Description

Create `email_finder/discovery/website_scraper.py` that scrapes company/podcast websites to find email addresses on contact and about pages.

## Reuses

- `get_about_us_link()` from `scraper/homepage_scraper.py`
- `scrape_about_us_content()` from `scraper/about_us_scraper.py`
- `normalize_url()`, `is_valid_url()` from `utils/helpers.py`

## Implementation

```python
async def scrape_website_for_emails(lead: LeadInput, config: Config) -> NodeResult:
    """
    Scrape lead's company/podcast website for email addresses.
    Skips if no domain/website available.
    """
```

### Logic

1. Determine URL to scrape:
   - Use `lead.website` if available
   - Else construct from `lead.company_domain`
   - If neither → return NodeResult with error "no domain available"

2. Find relevant pages:
   - Use existing `get_about_us_link()` for About page
   - Also look for Contact page: check `/contact`, `/contact-us`, `/get-in-touch`
   - Scrape homepage too as fallback

3. For each page found:
   - Fetch content (reuse existing scraper utilities)
   - Extract emails via regex: `r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'`

4. Filter results:
   - Remove emails with generic prefixes (from `config.generic_email_prefixes`)
   - Remove emails from blacklisted domains (podcast hosting)
   - Remove duplicates

5. Return remaining emails in `NodeResult.found_emails`

## Acceptance Criteria

- [ ] Scrapes About and Contact pages from a given domain
- [ ] Extracts valid email addresses via regex
- [ ] Filters out generic emails (info@, support@, etc.)
- [ ] Filters out blacklisted domains
- [ ] Returns empty result (not error) when no emails found
- [ ] Skips gracefully when no domain/website available
- [ ] Handles connection errors without crashing
