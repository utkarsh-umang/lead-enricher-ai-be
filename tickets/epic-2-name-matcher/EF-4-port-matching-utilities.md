# EF-4: Port Core Matching Utilities from Google Script

**Epic**: Epic 2 — Name-Email Ownership Matcher
**Priority**: High
**Depends On**: EF-1, EF-2

## Description

Port the Google Apps Script's core string matching utilities to Python in `email_finder/verification/name_email_matcher.py`. These are the building blocks for email ownership verification.

## Functions to Port

### From Google Script → Python

| Google Script Function | Python Function | Purpose |
|----------------------|----------------|---------|
| `normalize(text)` | `normalize(text: str) -> str` | Transliterate + lowercase + strip non-alphanumeric |
| `transliterate(text)` | `transliterate(text: str) -> str` | Accent map (á→a, é→e, ñ→n, ß→ss, etc.) |
| `longestCommonSubstring(str1, str2)` | `longest_common_substring(s1: str, s2: str) -> str` | Dynamic programming LCS |
| `splitEmail(email)` | `split_email(email: str) -> tuple[str, str]` | Returns (local_part, domain) |
| `isBlacklistedDomain(domain)` | `is_blacklisted_domain(domain: str, config: Config) -> bool` | Check against podcast hosting platforms |
| `extractDomainBrand(domain)` | `extract_domain_brand(domain: str) -> str` | Get brand from domain (before first dot) |
| `extractBrandCandidates(podcastName, website)` | `extract_brand_candidates(podcast_name: str, website: str) -> list[dict]` | Extract brand strings from podcast name + website |
| `getMeaningfulTokens(text)` | `get_meaningful_tokens(text: str) -> list[str]` | Tokenize, remove stop words |
| `extractWebsiteBrand(url)` | `extract_website_brand(url: str) -> str` | Brand from website URL (handles hosting platforms) |
| `extractBaseDomain(url)` | `extract_base_domain(url: str) -> str` | Base domain from URL |
| `extractSubdomain(url)` | `extract_subdomain(url: str) -> str` | Subdomain from URL |
| `extractPathIdentifier(url)` | `extract_path_identifier(url: str) -> str` | Brand from URL path |
| `isHostingPlatformDomain(domain)` | `is_hosting_platform_domain(domain: str) -> bool` | Check podcast hosting platforms |

## Acceptance Criteria

- [ ] All functions ported with identical behavior to Google Script
- [ ] `normalize("José García")` returns `"josegarcia"`
- [ ] `longest_common_substring("johnsmith", "jsmith")` returns `"smith"`
- [ ] `split_email("john@acme.com")` returns `("john", "acme.com")`
- [ ] `is_blacklisted_domain("spreaker.com")` returns `True`
- [ ] `extract_brand_candidates("The Acme Show", "https://acmeshow.com")` returns candidates with "acme" and "acmeshow"
