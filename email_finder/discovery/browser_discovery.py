"""
Browser-based email discovery node (Crawl4AI / Playwright).

Last-resort node in the email-finder waterfall. Uses Crawl4AI's
AsyncWebCrawler to:
  1. Google-search for missing social profiles (Facebook, YouTube).
  2. Navigate to known / found social pages and extract contact emails from
     About / Contact sections.

LinkedIn is intentionally skipped — it requires authenticated sessions which
are outside the scope of this scraper.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from email_finder.config import Config
from email_finder.models import LeadInput, NodeResult

logger = logging.getLogger(__name__)

_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Google search URL template
_GOOGLE_SEARCH = "https://www.google.com/search?q={query}"

# CSS selectors / URL fragments used when navigating social pages
_YOUTUBE_ABOUT_SUFFIX = "/about"
_FACEBOOK_ABOUT_SUFFIX = "/about"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_google_query(lead: LeadInput, site: str) -> str:
    parts = [lead.full_name]
    if lead.company_name:
        parts.append(lead.company_name)
    parts.append(f"site:{site}")
    return " ".join(parts)


async def _crawl(url: str, timeout: int) -> Optional[str]:
    """
    Fetch *url* with Crawl4AI and return the page's markdown/text content.
    Returns None on any error.
    """
    try:
        from crawl4ai import AsyncWebCrawler

        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url, page_timeout=timeout * 1000)
            if result and result.success:
                return result.markdown or result.cleaned_html or ""
        return None
    except Exception as exc:
        logger.debug("Crawl4AI failed for %s: %s", url, exc)
        return None


async def google_search_for_profile(query: str, site: str, timeout: int) -> Optional[str]:
    """
    Use Crawl4AI to run a Google search and return the first result URL that
    belongs to *site*.
    """
    search_url = _GOOGLE_SEARCH.format(query=re.sub(r"\s+", "+", query))
    content = await _crawl(search_url, timeout)
    if not content:
        return None

    # Extract URLs from the page content that match the target site
    url_pattern = re.compile(
        r"https?://(?:www\.)?" + re.escape(site) + r"/[^\s\)\]\>\"\']*"
    )
    matches = url_pattern.findall(content)
    if not matches:
        return None

    # Return the first match, strip trailing punctuation
    return matches[0].rstrip(".,;:)")


async def scrape_social_page_for_email(url: str, timeout: int) -> list[str]:
    """
    Navigate to a social page, attempt to reach its About/Contact section,
    and extract email addresses via regex.
    """
    urls_to_try: list[str] = [url]

    # For YouTube, also try the /about tab
    if "youtube.com" in url and not url.rstrip("/").endswith("/about"):
        urls_to_try.append(url.rstrip("/") + _YOUTUBE_ABOUT_SUFFIX)

    # For Facebook, also try the /about section
    if "facebook.com" in url and "/about" not in url:
        urls_to_try.append(url.rstrip("/") + _FACEBOOK_ABOUT_SUFFIX)

    emails: list[str] = []
    for page_url in urls_to_try:
        content = await _crawl(page_url, timeout)
        if content:
            found = [m.lower() for m in _RE_EMAIL.findall(content)]
            emails.extend(found)

    # Deduplicate
    seen: set[str] = set()
    result: list[str] = []
    for e in emails:
        if e not in seen:
            seen.add(e)
            result.append(e)
    return result


# ---------------------------------------------------------------------------
# Public node
# ---------------------------------------------------------------------------

async def browser_discover_email(lead: LeadInput, config: Config) -> NodeResult:
    """
    Use Crawl4AI to find and scrape social pages for contact emails.

    Smart-skip logic:
    - ``linkedin_url`` set → LinkedIn skipped entirely (requires login).
    - ``facebook_url`` set → skip Google search; scrape known URL directly.
    - ``youtube_url``  set → skip Google search; scrape known URL directly.
    - URL missing       → Google-search for the platform first.

    Returns NodeResult with found_emails populated (may be empty — not an error).
    """
    timeout = config.browser_timeout
    all_emails: list[str] = []
    sources: dict[str, str] = {}   # platform → url actually scraped

    # ---- Facebook ----
    fb_url = lead.facebook_url
    if not fb_url:
        query = _build_google_query(lead, "facebook.com")
        logger.debug("Searching Google for Facebook: %s", query)
        fb_url = await google_search_for_profile(query, "facebook.com", timeout)

    if fb_url:
        sources["facebook"] = fb_url
        emails = await scrape_social_page_for_email(fb_url, timeout)
        all_emails.extend(emails)

    # ---- YouTube ----
    yt_url = lead.youtube_url
    if not yt_url:
        query = _build_google_query(lead, "youtube.com")
        logger.debug("Searching Google for YouTube: %s", query)
        yt_url = await google_search_for_profile(query, "youtube.com", timeout)

    if yt_url:
        sources["youtube"] = yt_url
        emails = await scrape_social_page_for_email(yt_url, timeout)
        all_emails.extend(emails)

    # ---- LinkedIn: intentionally skipped ----
    if lead.linkedin_url:
        logger.debug("LinkedIn URL present but skipped (requires authenticated session).")

    # Deduplicate final list
    seen: set[str] = set()
    unique_emails: list[str] = []
    for e in all_emails:
        if e not in seen:
            seen.add(e)
            unique_emails.append(e)

    return NodeResult(
        found_email=unique_emails[0] if unique_emails else None,
        found_emails=unique_emails,
        data={"sources": sources},
    )
