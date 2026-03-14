"""
Perplexity search discovery node.

Queries the Perplexity API to find a lead's professional email address and
any missing profile/social data. The prompt is constructed dynamically — it
only asks for fields that are not already present on the LeadInput.
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse, urlunparse

from email_finder.config import Config
from email_finder.models import LeadInput, NodeResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns used by parse_perplexity_response
# ---------------------------------------------------------------------------
_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_RE_URL   = re.compile(r"https?://[^\s\)\]\>\"\']+")

_SOCIAL_HOSTS = {
    "linkedin.com", "facebook.com", "youtube.com",
    "twitter.com", "x.com", "instagram.com",
}

# Phrases that signal a field was not found
_NOT_FOUND_PHRASES = [
    "could not find", "couldn't find", "no public", "unable to locate",
    "not available", "not found", "i was unable", "i could not",
]

_PERPLEXITY_MODEL = "sonar"
_TEMPERATURE = 0.1
_MAX_TOKENS = 500


def _normalize_url(url: str) -> str:
    """Strip query params, fragments, and trailing slashes from a URL."""
    parsed = urlparse(url)
    clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
    return clean


def _extract_domain(url: str) -> str:
    """Return the bare domain (no www) from a URL."""
    host = urlparse(url).netloc.lower()
    return host.lstrip("www.")


def _is_not_found(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _NOT_FOUND_PHRASES)


def parse_perplexity_response(response_text: str) -> dict:
    """
    Parse Perplexity's free-text response into structured data.

    Returns:
        {
            "emails":        list[str],
            "linkedin_url":  str | None,
            "facebook_url":  str | None,
            "youtube_url":   str | None,
            "twitter_url":   str | None,
            "website":       str | None,
            "company_domain": str | None,
        }

    Fields are set to None when the response signals the data was not found.
    """
    result: dict = {
        "emails": [],
        "linkedin_url": None,
        "facebook_url": None,
        "youtube_url": None,
        "twitter_url": None,
        "website": None,
        "company_domain": None,
    }

    if _is_not_found(response_text):
        # Response broadly says nothing was found — return all-empty
        return result

    # --- Emails ---
    emails = list(dict.fromkeys(  # deduplicate, preserve order
        m.lower() for m in _RE_EMAIL.findall(response_text)
    ))
    result["emails"] = emails

    # --- URLs ---
    raw_urls = _RE_URL.findall(response_text)
    non_social_urls: list[str] = []

    for raw_url in raw_urls:
        # Strip trailing punctuation that may have been captured
        raw_url = raw_url.rstrip(".,;:)")
        try:
            parsed = urlparse(raw_url)
        except Exception:
            continue

        if not parsed.scheme or not parsed.netloc:
            continue

        host = parsed.netloc.lower().lstrip("www.")
        url_norm = _normalize_url(raw_url)

        if "linkedin.com" in host:
            if "/in/" in parsed.path or "/company/" in parsed.path:
                if result["linkedin_url"] is None:
                    result["linkedin_url"] = url_norm

        elif "facebook.com" in host:
            if result["facebook_url"] is None:
                result["facebook_url"] = url_norm

        elif "youtube.com" in host:
            if result["youtube_url"] is None:
                result["youtube_url"] = url_norm

        elif "twitter.com" in host or "x.com" in host:
            if result["twitter_url"] is None:
                result["twitter_url"] = url_norm

        elif not any(s in host for s in _SOCIAL_HOSTS):
            non_social_urls.append(url_norm)

    # Pick the first non-social URL as the website
    if non_social_urls:
        website = non_social_urls[0]
        result["website"] = website
        result["company_domain"] = _extract_domain(website)

    return result


def _build_prompt(lead: LeadInput) -> str:
    """Construct a targeted Perplexity prompt based on what the lead is missing."""
    ask_for = ["professional email address"]

    if not lead.linkedin_url:
        ask_for.append("LinkedIn profile URL")
    if not lead.company_domain and not lead.website:
        ask_for.append("company website or domain")
    if not lead.facebook_url:
        ask_for.append("Facebook page")
    if not lead.youtube_url:
        ask_for.append("YouTube channel")
    if not lead.twitter_url:
        ask_for.append("Twitter/X profile")

    context_parts = [lead.full_name]
    if lead.company_name:
        context_parts.append(f"at {lead.company_name}")
    if lead.podcast_name:
        context_parts.append(f"host/guest of {lead.podcast_name} podcast")
    if lead.linkedin_url:
        context_parts.append(f"LinkedIn: {lead.linkedin_url}")

    return (
        f"Find the {', '.join(ask_for)} for {' '.join(context_parts)}. "
        "Return only verified, factual information with sources."
    )


async def perplexity_search(lead: LeadInput, config: Config) -> NodeResult:
    """
    Search the internet via Perplexity for the lead's email and profiles.

    Only searches for fields NOT already present on the lead. Returns a
    NodeResult whose ``data`` dict contains the raw Perplexity response text
    under the key ``"raw_response"`` for downstream parsing (EF-8).

    Args:
        lead:   LeadInput — name, company, and any already-known profile data.
        config: Config instance supplying the Perplexity API key.

    Returns:
        NodeResult with:
        - data["raw_response"]: raw text from Perplexity
        - data["prompt"]:       the prompt that was sent (useful for debugging)
        - error:                set if the API call failed
    """
    try:
        from llm_utils.gpt_utils import PerplexityService
    except ImportError as exc:
        return NodeResult(error=f"PerplexityService import failed: {exc}")

    prompt = _build_prompt(lead)

    try:
        service = PerplexityService(api_key=config.perplexity_api_key)
        response = service.process_content(
            content="",          # Perplexity searches the web; no local content needed
            prompt=prompt,
            model=_PERPLEXITY_MODEL,
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
        )
    except Exception as exc:
        logger.error("Perplexity API call failed: %s", exc)
        return NodeResult(error=f"Perplexity API error: {exc}")

    if not response.get("success"):
        error_msg = response.get("error", "unknown Perplexity error")
        logger.warning("Perplexity returned failure: %s", error_msg)
        return NodeResult(error=error_msg)

    raw_text: str = response.get("result", "")
    parsed = parse_perplexity_response(raw_text)

    found_emails = parsed.get("emails", [])
    return NodeResult(
        found_email=found_emails[0] if found_emails else None,
        found_emails=found_emails,
        data={
            "raw_response": raw_text,
            "prompt": prompt,
            **{k: v for k, v in parsed.items() if k != "emails"},
        },
    )
