"""
Data models for the email_finder package.

Defines Pydantic models that represent leads, discovered emails,
verification results, and any other shared data structures used across sub-modules.
"""

from typing import Optional
from pydantic import BaseModel, field_validator, ConfigDict


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


class DiscoveryContext(BaseModel):
    """
    Mutable context that accumulates discoveries as the waterfall progresses.

    Initialise from a LeadInput via ``DiscoveryContext.from_lead(lead)``.
    After each node runs, call ``ctx.merge_node_result(result)`` to fold in
    newly found domain, social URLs, and candidate emails.
    Use ``ctx.to_lead(base_lead)`` to get an enriched LeadInput for the next
    node call.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Discovered / enriched fields (None = not yet known)
    company_domain: Optional[str] = None
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    facebook_url: Optional[str] = None
    youtube_url: Optional[str] = None
    instagram_url: Optional[str] = None

    # Accumulated candidate emails from all nodes (ordered, deduped)
    candidate_emails: list[str] = []

    # Names of nodes that have completed (in order)
    nodes_completed: list[str] = []

    # ----------------------------------------------------------------
    # Factory
    # ----------------------------------------------------------------

    @classmethod
    def from_lead(cls, lead: "LeadInput") -> "DiscoveryContext":
        """Initialise from a lead's existing data."""
        return cls(
            company_domain=lead.company_domain,
            website=lead.website,
            linkedin_url=lead.linkedin_url,
            twitter_url=lead.twitter_url,
            facebook_url=lead.facebook_url,
            youtube_url=lead.youtube_url,
            instagram_url=lead.instagram_url,
        )

    # ----------------------------------------------------------------
    # Merge
    # ----------------------------------------------------------------

    def merge_node_result(self, node_name: str, result: NodeResult) -> None:
        """
        Fold a node's discoveries into the context.

        Rules:
        - Domain/social URL fields are only set when currently None
          (first-writer wins; don't overwrite confirmed data).
        - Candidate emails are always accumulated and deduplicated.
        """
        data = result.data

        if not self.company_domain and data.get("company_domain"):
            self.company_domain = data["company_domain"]
        if not self.website and data.get("website"):
            self.website = data["website"]
        if not self.linkedin_url and data.get("linkedin_url"):
            self.linkedin_url = data["linkedin_url"]
        if not self.twitter_url and data.get("twitter_url"):
            self.twitter_url = data["twitter_url"]
        if not self.facebook_url and data.get("facebook_url"):
            self.facebook_url = data["facebook_url"]
        if not self.youtube_url and data.get("youtube_url"):
            self.youtube_url = data["youtube_url"]
        if not self.instagram_url and data.get("instagram_url"):
            self.instagram_url = data["instagram_url"]

        # Accumulate candidate emails (deduped)
        existing = set(self.candidate_emails)
        new_emails: list[str] = []
        if result.found_email and result.found_email.lower() not in existing:
            new_emails.append(result.found_email.lower())
            existing.add(result.found_email.lower())
        for e in result.found_emails:
            el = e.lower()
            if el not in existing:
                new_emails.append(el)
                existing.add(el)
        self.candidate_emails.extend(new_emails)

        self.nodes_completed.append(node_name)

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    def has_domain(self) -> bool:
        """Return True if a company domain or website is known."""
        return bool(self.company_domain or self.website)

    def to_lead(self, base_lead: "LeadInput") -> "LeadInput":
        """
        Return a new LeadInput that merges the original lead with any data
        accumulated in this context.  Only fields currently None on the base
        lead are filled in from the context.
        """
        updates: dict = {}
        for field in (
            "company_domain", "website",
            "linkedin_url", "twitter_url", "facebook_url",
            "youtube_url", "instagram_url",
        ):
            if getattr(base_lead, field) is None:
                ctx_val = getattr(self, field)
                if ctx_val is not None:
                    updates[field] = ctx_val
        return base_lead if not updates else base_lead.model_copy(update=updates)
