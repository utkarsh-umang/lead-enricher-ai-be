# EF-5: Enhanced Name-Email Matching Logic

**Epic**: Epic 2 — Name-Email Ownership Matcher
**Priority**: High
**Depends On**: EF-4

## Description

Build on top of the ported utilities (EF-4) to create enhanced name-aware email matching. This goes beyond the Google Script's LCS approach by generating explicit name variations and scoring matches.

## Functions to Implement

### `generate_name_variations(full_name: str) -> list[str]`

Parse full_name into first/last, then generate expected email local parts:

```
Input: "John Smith"
Output: [
    "john.smith",    # first.last
    "johnsmith",     # firstlast
    "jsmith",        # flast
    "johnS",         # firstl (lowercase)
    "john",          # first
    "smith",         # last
    "smith.john",    # last.first
    "j.smith",       # f.last
    "john_smith",    # first_last
    "john-smith",    # first-last
    "smithj",        # lastf
]
```

Handle edge cases:
- Hyphenated names: "Mary-Jane Watson" → includes "maryjane", "mj", "mary-jane"
- Middle names: "John Michael Smith" → uses first + last, ignores middle
- Single name: "Madonna" → just "madonna"

### `match_email_to_name(email, full_name, company_name=None, podcast_name=None) -> dict`

Returns:
```python
{
    "confidence": 0.85,          # 0.0 - 1.0
    "match_type": "name_exact",  # "name_exact" | "name_lcs" | "brand_match" | "no_match"
    "matched_variation": "j.smith",
    "details": "local part 'j.smith' exact match with name variation"
}
```

Scoring logic:
- Exact match (local part == name variation): confidence 0.9-1.0
- LCS match (LCS length >= threshold relative to variation): confidence 0.6-0.8
- Brand match only (domain matches company/podcast, but name doesn't match): confidence 0.3-0.5
- No match: confidence 0.0

## Acceptance Criteria

- [ ] `generate_name_variations("John Smith")` returns at least 10 variations
- [ ] `match_email_to_name("j.smith@acmere.com", "John Smith", "Acme Real Estate")` returns confidence > 0.8
- [ ] `match_email_to_name("info@acmere.com", "John Smith", "Acme Real Estate")` returns confidence < 0.5 (brand match only)
- [ ] `match_email_to_name("random@gmail.com", "John Smith")` returns confidence 0.0
- [ ] Handles accented names correctly (e.g., "José García")
