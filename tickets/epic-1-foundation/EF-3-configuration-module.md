# EF-3: Configuration Module

**Epic**: Epic 1 — Foundation & Data Models
**Priority**: Highest
**Depends On**: EF-1

## Description

Create `email_finder/config.py` with a Config class that holds all configurable settings. Loads from environment variables with sensible defaults.

## Config Fields

```python
class Config(BaseModel):
    # Mailin credentials
    mailin_email: str              # MAILIN_EMAIL env var
    mailin_password: str           # MAILIN_PASSWORD env var

    # API keys
    perplexity_api_key: str        # PERPLEXITY_API_KEY env var (already exists)

    # Name matching thresholds
    name_match_threshold: float = 0.6
    lcs_min_length: int = 4

    # Email filtering
    generic_email_prefixes: list = [
        "info", "support", "hello", "contact", "admin",
        "team", "office", "sales", "help", "media"
    ]

    # Blacklisted domains (podcast hosting platforms)
    blacklisted_domains: list = [
        "spreaker.com", "anchor.fm", "spotify.com", "podcasters.spotify.com",
        "simplecast.com", "buzzsprout.com", "libsyn.com", "podbean.com",
        "transistor.fm", "redcircle.com", "megaphone.fm", "omny.fm"
    ]

    # Browser automation
    browser_timeout: int = 30          # seconds
    mailin_wait_timeout: int = 300     # seconds to wait for bulk verify

    # Pattern generation
    max_patterns_per_lead: int = 10
```

## Acceptance Criteria

- [ ] Config loads from env vars
- [ ] Can be overridden by passing explicit values
- [ ] Defaults are sensible and don't require env vars for optional settings
- [ ] Mailin credentials are required (raise error if missing)
