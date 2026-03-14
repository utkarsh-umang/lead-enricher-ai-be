"""
email_finder — top-level package for discovering and verifying email addresses.
"""

from email_finder.batch import find_emails_batch
from email_finder.finder import find_email
from email_finder.models import EmailFinderResult, LeadInput

__all__ = ["find_emails_batch", "find_email", "LeadInput", "EmailFinderResult"]
