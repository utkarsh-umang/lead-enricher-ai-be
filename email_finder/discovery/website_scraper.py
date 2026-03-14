"""
Website email scraper discovery node.

Scrapes a lead's company / podcast website (homepage, About, and Contact pages)
to extract email addresses.  Reuses existing scraper utilities from
`scraper/homepage_scraper.py`, `scraper/about_us_scraper.py`, and
`utils/helpers.py`.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from email_finder.config import Config
from email_finder.models import LeadInput, NodeResult

logger = logging.getLogger(__name__)

_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

_CONTACT_PATHS = ["/contact", "/contact-us", "/get-in-touch"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_text(url: str) -> str | None:
    """Fetch a URL and return its visible text content, or None on error."""
    try:
        import requests
        from bs4 import BeautifulSoup

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        return soup.get_text(separator=" ")
    except Exception as exc:
        logger.debug("Could not fetch %s: %s", url, exc)
        return None


def _find_contact_url(base_url: str) -> str | None:
    """Try common contact page paths and return the first that responds 200."""
    try:
        import requests

        for path in _CONTACT_PATHS:
            url = urljoin(base_url, path)
            try:
                resp = requests.head(url, timeout=8, allow_redirects=True)
                if resp.status_code == 200:
                    return url
            except Exception:
                continue
    except Exception as exc:
        logger.debug("Contact page probe failed: %s", exc)
    return None


def _extract_emails_from_text(text: str) -> list[str]:
    return [m.lower() for m in _RE_EMAIL.findall(text)]


def _filter_emails(emails: list[str], config: Config) -> list[str]:
    """Remove generic-prefix and blacklisted-domain emails, deduplicate."""
    seen: set[str] = set()
    result: list[str] = []
    for email in emails:
        if email in seen:
            continue
        seen.add(email)
        local, _, domain = email.partition("@")
        if local in config.generic_email_prefixes:
            continue
        if domain in config.blacklisted_domains:
            continue
        result.append(email)
    return result


# ---------------------------------------------------------------------------
# Public node
# ---------------------------------------------------------------------------

async def scrape_website_for_emails(lead: LeadInput, config: Config) -> NodeResult:
    """
    Scrape the lead's company/podcast website for email addresses.

    Pages scraped (in order): homepage, About page, Contact page.
    Emails are filtered to remove generic prefixes and blacklisted domains.

    Returns:
        NodeResult with found_emails populated (may be empty list — not an error).
        Sets NodeResult.error only when no domain/website is available or an
        unexpected exception is raised.
    """
    try:
        from utils.helpers import normalize_url, is_valid_url
        from scraper.homepage_scraper import get_about_us_link
    except ImportError as exc:
        return NodeResult(error=f"Import error: {exc}")

    # --- 1. Resolve base URL ---
    raw_url = lead.website or (f"https://{lead.company_domain}" if lead.company_domain else None)
    if not raw_url:
        return NodeResult(error="no domain available")

    if not is_valid_url(raw_url):
        return NodeResult(error=f"invalid URL: {raw_url}")

    base_url: str = normalize_url(raw_url)

    # --- 2. Collect pages to scrape ---
    pages_to_scrape: list[str] = [base_url]

    about_url = get_about_us_link(base_url)
    if about_url:
        pages_to_scrape.append(about_url)

    contact_url = _find_contact_url(base_url)
    if contact_url:
        pages_to_scrape.append(contact_url)

    # --- 3. Scrape each page and collect raw emails ---
    raw_emails: list[str] = []
    pages_scraped: list[str] = []

    for url in pages_to_scrape:
        text = _fetch_text(url)
        if text:
            pages_scraped.append(url)
            raw_emails.extend(_extract_emails_from_text(text))

    # --- 4. Filter ---
    filtered = _filter_emails(raw_emails, config)

    return NodeResult(
        found_email=filtered[0] if filtered else None,
        found_emails=filtered,
        data={
            "pages_scraped": pages_scraped,
            "raw_email_count": len(raw_emails),
        },
    )
