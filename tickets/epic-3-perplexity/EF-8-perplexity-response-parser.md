# EF-8: Perplexity Response Parser

**Epic**: Epic 3 — Perplexity Profile & Email Discovery
**Priority**: High
**Depends On**: EF-7

## Description

Add structured parsing for Perplexity's free-text response to extract emails, URLs, and domains.

## Implementation

Add to `email_finder/discovery/perplexity_search.py`:

```python
def parse_perplexity_response(response_text: str) -> dict:
    """
    Parse Perplexity's free-text response into structured data.

    Returns:
        {
            "emails": ["john@acme.com"],
            "linkedin_url": "https://linkedin.com/in/johnsmith",
            "facebook_url": "https://facebook.com/johnsmith",
            "youtube_url": "https://youtube.com/@johnsmith",
            "twitter_url": "https://twitter.com/johnsmith",
            "website": "https://acme.com",
            "company_domain": "acme.com",
        }
    """
```

### Extraction Logic

1. **Emails**: Regex `r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'`
2. **LinkedIn URLs**: Match `linkedin.com/in/` or `linkedin.com/company/`
3. **Facebook URLs**: Match `facebook.com/` patterns
4. **YouTube URLs**: Match `youtube.com/` or `youtube.com/@` patterns
5. **Twitter URLs**: Match `twitter.com/` or `x.com/` patterns
6. **Website/Domain**: Match URLs that aren't social platforms, extract domain
7. **Graceful "not found"**: If response contains "could not find", "no public", "unable to locate" → return empty dict for that field

### URL Validation

- Validate extracted URLs are properly formatted
- Normalize LinkedIn URLs (remove query params, trailing slashes)
- Deduplicate

## Acceptance Criteria

- [ ] Extracts email from: "Their email is john@acme.com"
- [ ] Extracts LinkedIn from: "LinkedIn profile: https://linkedin.com/in/johnsmith"
- [ ] Handles "I couldn't find a public email" gracefully (returns None for email)
- [ ] Doesn't extract garbage from malformed responses
- [ ] Extracts domain from website URL
