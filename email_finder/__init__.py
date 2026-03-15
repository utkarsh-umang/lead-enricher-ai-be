"""
email_finder — top-level package for discovering and verifying email addresses.
"""

from email_finder.batch import find_emails_batch
from email_finder.finder import find_email
from email_finder.models import EmailFinderResult, LeadInput
from email_finder.io.loader import load_leads_from_csv, load_leads_from_google_sheet
from email_finder.io.exporter import export_results

__all__ = [
    "find_emails_batch",
    "find_email",
    "LeadInput",
    "EmailFinderResult",
    "load_leads_from_csv",
    "load_leads_from_google_sheet",
    "export_results",
]
