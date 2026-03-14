"""
Data models for the email_finder package.

Defines Pydantic models that represent leads, discovered emails,
verification results, and any other shared data structures used across sub-modules.
"""

from typing import Optional
from pydantic import BaseModel, field_validator


class LeadInput(BaseModel):
    full_name: str                        # Required
    company_name: Optional[str] = None    # Usually present
    company_domain: Optional[str] = None  # Sometimes present
    existing_email: Optional[str] = None  # Present for hosts, absent for guests
    podcast_name: Optional[str] = None    # From Podscan
    website: Optional[str] = None         # Podcast/company website if known
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    facebook_url: Optional[str] = None
    youtube_url: Optional[str] = None
    instagram_url: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def full_name_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("full_name must not be empty")
        return v


class EmailFinderResult(BaseModel):
    email: Optional[str] = None
    status: str  # "verified" | "unverified" | "catch_all" | "invalid" | "not_found"
    confidence: float = 0.0
    source: str = ""  # Which strategy found/confirmed it
    verification_details: dict = {}
    discovery_log: list = []  # [{node, action, result, timestamp}]


class NodeResult(BaseModel):
    found_email: Optional[str] = None
    found_emails: list[str] = []   # Multiple candidates
    confidence: float = 0.0
    data: dict = {}                # Extra discovered data (domain, social urls, etc.)
    error: Optional[str] = None
