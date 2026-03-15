# EF-2: Define Data Models

**Epic**: Epic 1 — Foundation & Data Models
**Priority**: Highest
**Depends On**: EF-1

## Description

Create `email_finder/models.py` with Pydantic models that define the input/output contract for the entire system.

## Models

```python
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
```

## Acceptance Criteria

- [ ] Models can be instantiated with valid data
- [ ] Pydantic validation rejects invalid data (e.g., empty full_name)
- [ ] Models serialize to dict correctly
- [ ] LeadInput accepts all social link fields as optional
