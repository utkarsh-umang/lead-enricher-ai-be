# EF-18: CSV Output Splitter — Found vs Not Found

**Epic**: Epic 9 — End-to-End Testing Pipeline
**Priority**: High
**Depends On**: EF-2 (models), EF-15 (batch processing)

## Description

Create a utility that takes the `EmailFinderResult` list from `find_emails_batch()` and splits it into two output CSVs:

1. **Enriched** — Leads where the system found/verified an email
2. **Still Needs Enrichment** — Leads where the system could not determine an email

## Implementation

Create `email_finder/io/exporter.py`:

```python
import pandas as pd
from email_finder.models import LeadInput, EmailFinderResult

def export_results(
    leads: list[LeadInput],
    results: list[EmailFinderResult],
    output_dir: str = "./output",
    prefix: str = ""
) -> dict[str, str]:
    """
    Split results into two CSVs based on whether email was found.

    Args:
        leads: Original LeadInput list
        results: Corresponding EmailFinderResult list
        output_dir: Directory to write CSVs
        prefix: Optional filename prefix (e.g., "2026-03-15_podcast_hosts")

    Returns:
        {"enriched": "/path/to/enriched.csv", "needs_enrichment": "/path/to/still_needs.csv"}
    """
```

### Enriched CSV (email found)

Includes leads where `result.status` is `"verified"`, `"unverified"`, or `"catch_all"`.

Columns:
```
full_name | company_name | company_domain | email | email_status | email_confidence | email_source | podcast_name | website | linkedin_url | twitter_url | facebook_url | youtube_url | instagram_url
```

- `email`: The found/verified email
- `email_status`: "verified" / "unverified" / "catch_all"
- `email_confidence`: 0.0-1.0
- `email_source`: Which node found it (e.g., "perplexity", "pattern_gen", "website_scrape")

### Still Needs Enrichment CSV (email NOT found)

Includes leads where `result.status` is `"not_found"` or `"invalid"`.

Columns:
```
full_name | company_name | company_domain | existing_email | failure_reason | nodes_tried | podcast_name | website | linkedin_url | twitter_url | facebook_url | youtube_url | instagram_url | discovered_domain | discovered_linkedin | discovered_socials
```

- `existing_email`: Original email if any (was invalid)
- `failure_reason`: Why it failed (e.g., "no domain found", "all patterns invalid", "all strategies exhausted")
- `nodes_tried`: Comma-separated list of nodes that ran
- `discovered_*`: Any data discovered during the process (even though email wasn't found, discovered LinkedIn/domain is still useful)

### Summary Report

Print after export:
```
=== Email Finder Results ===
Total leads processed: 50
Enriched (email found): 35 (70%)
  - Verified: 28
  - Catch-all: 5
  - Unverified: 2
Still needs enrichment: 15 (30%)
  - No domain found: 8
  - All patterns invalid: 4
  - All strategies exhausted: 3

Files written:
  - output/2026-03-15_enriched.csv (35 rows)
  - output/2026-03-15_still_needs_enrichment.csv (15 rows)
```

## Acceptance Criteria

- [ ] Splits results into two CSVs correctly based on status
- [ ] Enriched CSV has email + status + confidence + source columns
- [ ] Still Needs CSV has failure reason + nodes tried + any discovered data
- [ ] Prints summary with counts and percentages
- [ ] Output directory created if it doesn't exist
- [ ] Handles empty results (all found or all not found)
- [ ] Filename includes prefix/date for organization
