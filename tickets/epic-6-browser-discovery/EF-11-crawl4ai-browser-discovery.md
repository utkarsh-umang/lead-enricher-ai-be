# EF-11: Crawl4AI Browser Discovery Node

**Epic**: Epic 6 — Browser Automation Discovery
**Priority**: Medium
**Depends On**: EF-1, EF-2, EF-3

## Description

Create `email_finder/discovery/browser_discovery.py` that uses Crawl4AI (Playwright-based) to find and scrape social media pages for contact emails. This is the last resort node in the waterfall — high cost but can find emails not available via other methods.

## Smart Skip Logic

Only searches for platforms NOT already known on the lead:

| Lead Has | Action |
|----------|--------|
| `facebook_url` set | Skip Google search for Facebook. Scrape the known URL directly. |
| `youtube_url` set | Skip Google search for YouTube. Scrape the known URL directly. |
| `linkedin_url` set | Skip LinkedIn entirely (can't scrape without login). |
| No social URLs | Google search for each platform. |

## Implementation

```python
async def browser_discover_email(lead: LeadInput, config: Config) -> NodeResult:
    """
    Use Crawl4AI to find and scrape social pages for contact emails.

    Strategy:
    1. For missing platforms → Google search: "{name} {company} site:facebook.com"
    2. For known/found pages → Navigate and scrape About/Contact sections
    3. Extract emails from page content
    """
```

### Google Search Scraping

```python
async def google_search_for_profile(query: str, site: str) -> Optional[str]:
    """
    Use Crawl4AI to:
    1. Navigate to Google search
    2. Enter query: "{name} {company} site:{site}"
    3. Extract first relevant result URL
    """
```

### Social Page Email Extraction

```python
async def scrape_social_page_for_email(url: str) -> list[str]:
    """
    Navigate to social page, find About/Contact section,
    extract emails via regex.

    Handles:
    - Facebook: About section, Contact Info
    - YouTube: About tab, channel description
    """
```

### Crawl4AI Usage

- Use `AsyncWebCrawler` from Crawl4AI
- Set browser timeout from config
- Handle anti-bot measures (Crawl4AI has built-in handling)
- Clean up browser session after use

## Acceptance Criteria

- [ ] Given lead with `facebook_url` set → scrapes it directly, no Google search
- [ ] Given lead with no social URLs → searches Google for Facebook and YouTube
- [ ] Extracts emails from Facebook About section
- [ ] Extracts emails from YouTube channel About tab
- [ ] Handles pages with no email gracefully
- [ ] Respects browser_timeout config
- [ ] Properly cleans up browser sessions
