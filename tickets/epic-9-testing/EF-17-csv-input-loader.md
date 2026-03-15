# EF-17: CSV / Google Sheet Input Loader

**Epic**: Epic 9 — End-to-End Testing Pipeline
**Priority**: High
**Depends On**: EF-2 (models)

## Description

Create a test notebook and utility that loads leads from the "Needs_Enrichment" sheet (output of the existing Google Script) or a CSV export of it, and converts rows into `LeadInput` objects.

## Implementation

Create `email_finder/io/loader.py`:

```python
import pandas as pd
from email_finder.models import LeadInput

def load_leads_from_csv(file_path: str, column_mapping: dict = None) -> list[LeadInput]:
    """
    Load leads from a CSV file (exported from Google Sheet's Needs_Enrichment tab).

    Args:
        file_path: Path to CSV file
        column_mapping: Optional dict mapping CSV column names to LeadInput fields.
                        e.g. {"Podcast Name": "podcast_name", "Podcast Website": "website"}

    Returns:
        List of LeadInput objects
    """

def load_leads_from_google_sheet(spreadsheet_url: str, sheet_name: str = "Needs_Enrichment") -> list[LeadInput]:
    """
    Load leads directly from the Needs_Enrichment tab of a Google Sheet.
    Uses existing GoogleSheetService from google_utils/google_sheet.py.
    """
```

### Default Column Mapping

Based on the Google Script's column structure:

```python
DEFAULT_COLUMN_MAPPING = {
    # Map Google Sheet column names → LeadInput fields
    "Podcast Name": "podcast_name",
    "Podcast Website": "website",
    "Podcast Email": "existing_email",
    "Host Name": "full_name",           # or "Guest Name" for guests
    "Company": "company_name",
    "LinkedIn": "linkedin_url",
    "Twitter": "twitter_url",
    "Facebook": "facebook_url",
    "YouTube": "youtube_url",
    "Instagram": "instagram_url",
    "Website": "website",
    "Domain": "company_domain",
}
```

User can override with their own mapping if columns differ.

### Handling Multiple Emails

The Google Script's "Podcast Email" column may contain comma-separated emails. The loader should:
- Split on comma
- Store first email as `existing_email`
- Log if multiple emails found (for reference)

## Acceptance Criteria

- [ ] Loads CSV into list of LeadInput objects
- [ ] Loads directly from Google Sheet Needs_Enrichment tab
- [ ] Custom column mapping works
- [ ] Handles missing columns gracefully (sets field to None)
- [ ] Handles comma-separated emails
- [ ] Skips empty rows
- [ ] Reports count: "Loaded 47 leads from Needs_Enrichment"
