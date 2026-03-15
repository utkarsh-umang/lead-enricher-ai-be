# EF-7: Perplexity Search Node

**Epic**: Epic 3 — Perplexity Profile & Email Discovery
**Priority**: High
**Depends On**: EF-1, EF-2, EF-3

## Description

Create `email_finder/discovery/perplexity_search.py` that uses Perplexity to search the internet for the lead's email, profiles, and domain. The prompt is dynamically constructed — it only asks for what's missing.

## Reuses

- `PerplexityService` from `llm_utils/gpt_utils.py`

## Implementation

```python
async def perplexity_search(lead: LeadInput, config: Config) -> NodeResult:
    """
    Search internet via Perplexity for lead's email and profiles.
    Only searches for fields NOT already present on the lead.
    """
```

### Smart Prompt Construction

Build the prompt based on what's missing:

```python
# Always ask for
ask_for = ["professional email address"]

# Only ask for what's missing
if not lead.linkedin_url:
    ask_for.append("LinkedIn profile URL")
if not lead.company_domain and not lead.website:
    ask_for.append("company website or domain")
if not lead.facebook_url:
    ask_for.append("Facebook page")
if not lead.youtube_url:
    ask_for.append("YouTube channel")
if not lead.twitter_url:
    ask_for.append("Twitter/X profile")

# Build context from what we DO know
context_parts = [f"{lead.full_name}"]
if lead.company_name:
    context_parts.append(f"at {lead.company_name}")
if lead.podcast_name:
    context_parts.append(f"host/guest of {lead.podcast_name} podcast")
if lead.linkedin_url:
    context_parts.append(f"LinkedIn: {lead.linkedin_url}")

prompt = f"Find the {', '.join(ask_for)} for {' '.join(context_parts)}. Return only verified, factual information with sources."
```

### Perplexity Call

Use existing `PerplexityService.process_content()`:
- Model: default Perplexity model
- Temperature: 0.1 (factual, low creativity)
- Max tokens: 500

## Acceptance Criteria

- [ ] Given lead with only name+company, prompt asks for all fields
- [ ] Given lead with LinkedIn already set, prompt skips LinkedIn but asks for email/domain/other socials
- [ ] Returns NodeResult with discovered data in `data` dict
- [ ] Handles Perplexity errors gracefully (returns NodeResult with error)
- [ ] Response is parsed into structured data (see EF-8)
