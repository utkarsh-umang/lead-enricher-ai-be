"""
EF-17: CSV / Google Sheet Input Loader.

Converts rows from the "Needs_Enrichment" tab (Google Sheet or CSV export)
into ``LeadInput`` objects ready for ``find_emails_batch()``.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from email_finder.models import LeadInput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default column mapping — Google Script output → LeadInput fields
# ---------------------------------------------------------------------------

DEFAULT_COLUMN_MAPPING: dict[str, str] = {
    # Name variants
    "Host Name": "full_name",
    "Guest Name": "full_name",
    "Name": "full_name",
    "Full Name": "full_name",
    # Company
    "Company": "company_name",
    "Company Name": "company_name",
    # Domain
    "Domain": "company_domain",
    "Company Domain": "company_domain",
    # Email
    "Podcast Email": "existing_email",
    "Email": "existing_email",
    "Existing Email": "existing_email",
    # Podcast
    "Podcast Name": "podcast_name",
    # Website
    "Podcast Website": "website",
    "Website": "website",
    # Social URLs
    "LinkedIn": "linkedin_url",
    "LinkedIn URL": "linkedin_url",
    "Twitter": "twitter_url",
    "Twitter URL": "twitter_url",
    "Facebook": "facebook_url",
    "Facebook URL": "facebook_url",
    "YouTube": "youtube_url",
    "YouTube URL": "youtube_url",
    "Instagram": "instagram_url",
    "Instagram URL": "instagram_url",
}

_LEAD_INPUT_FIELDS = set(LeadInput.model_fields.keys())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_mapping(df_columns: list[str], custom_mapping: Optional[dict]) -> dict[str, str]:
    """
    Merge DEFAULT_COLUMN_MAPPING with any user-supplied override, then filter
    to only columns that actually exist in the DataFrame.
    """
    mapping = {**DEFAULT_COLUMN_MAPPING, **(custom_mapping or {})}
    return {col: field for col, field in mapping.items() if col in df_columns}


def _row_to_lead(row: pd.Series, mapping: dict[str, str]) -> Optional[LeadInput]:
    """
    Convert a single DataFrame row to a LeadInput.

    Returns None when full_name is absent or empty (row is skipped).
    Multi-value emails (comma-separated) use only the first address.
    """
    kwargs: dict = {}
    for col, field in mapping.items():
        raw = row.get(col)
        if pd.isna(raw) or raw == "":
            continue
        value = str(raw).strip()
        if not value:
            continue

        # Handle comma-separated emails — keep only the first
        if field == "existing_email" and "," in value:
            emails = [e.strip() for e in value.split(",") if e.strip()]
            if len(emails) > 1:
                logger.debug("Multiple emails found (%s) — using first: %s", emails, emails[0])
            value = emails[0] if emails else ""
            if not value:
                continue

        # Only map to known LeadInput fields
        if field in _LEAD_INPUT_FIELDS:
            kwargs[field] = value

    if not kwargs.get("full_name"):
        return None

    try:
        return LeadInput(**kwargs)
    except Exception as exc:
        logger.warning("Skipping row — validation error: %s", exc)
        return None


def _df_to_leads(df: pd.DataFrame, mapping: dict[str, str]) -> list[LeadInput]:
    """Convert a DataFrame to a list of LeadInput objects, skipping invalid rows."""
    leads: list[LeadInput] = []
    for _, row in df.iterrows():
        lead = _row_to_lead(row, mapping)
        if lead is not None:
            leads.append(lead)
    return leads


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_leads_from_csv(
    file_path: str,
    column_mapping: Optional[dict[str, str]] = None,
) -> list[LeadInput]:
    """
    Load leads from a CSV file exported from Google Sheet's Needs_Enrichment tab.

    Args:
        file_path:      Path to the CSV file.
        column_mapping: Optional dict overriding or extending the default
                        column-name → LeadInput-field mapping.

    Returns:
        List of LeadInput objects (empty rows skipped).
    """
    df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
    # Replace the literal string "nan" that sometimes appears after read_csv
    df = df.replace("nan", "")

    mapping = _build_mapping(list(df.columns), column_mapping)
    leads = _df_to_leads(df, mapping)

    logger.info("Loaded %d leads from CSV: %s", len(leads), file_path)
    print(f"Loaded {len(leads)} leads from {file_path}")
    return leads


def load_leads_from_google_sheet(
    spreadsheet_url: str,
    sheet_name: str = "Needs_Enrichment",
    column_mapping: Optional[dict[str, str]] = None,
) -> list[LeadInput]:
    """
    Load leads directly from a Google Sheet tab.

    Uses ``GoogleSheetService`` from ``google_utils.google_sheet``.

    Args:
        spreadsheet_url: Full Google Sheets URL or spreadsheet ID.
        sheet_name:      Name of the tab to read (default: "Needs_Enrichment").
        column_mapping:  Optional column-name → LeadInput-field override mapping.

    Returns:
        List of LeadInput objects.
    """
    from google_utils.google_sheet import GoogleSheetService

    service = GoogleSheetService()
    spreadsheet_id = service.extract_spreadsheet_id(spreadsheet_url)

    success, result = service.get_sheet_data(spreadsheet_id, f"{sheet_name}!A:Z")
    if not success:
        raise RuntimeError(f"Failed to fetch sheet '{sheet_name}': {result}")

    df: pd.DataFrame = result
    df = df.fillna("").astype(str)
    df = df.replace("nan", "")

    mapping = _build_mapping(list(df.columns), column_mapping)
    leads = _df_to_leads(df, mapping)

    logger.info("Loaded %d leads from Google Sheet tab '%s'.", len(leads), sheet_name)
    print(f"Loaded {len(leads)} leads from '{sheet_name}'")
    return leads
