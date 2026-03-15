# EF-16: Discovery Data Propagation Between Nodes

**Epic**: Epic 8 — Orchestration
**Priority**: High
**Depends On**: EF-14

## Description

Ensure that when a node discovers new data (domain, social URLs, etc.), that data is available to subsequent nodes in the waterfall. This is what makes the system smart — earlier cheap nodes feed data to later nodes.

## Implementation

Create a mutable `DiscoveryContext` that accumulates findings:

```python
class DiscoveryContext(BaseModel):
    """Mutable context that accumulates discoveries through the waterfall."""

    # Start with lead's original data
    company_domain: Optional[str] = None
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    facebook_url: Optional[str] = None
    youtube_url: Optional[str] = None
    instagram_url: Optional[str] = None

    # Accumulated candidate emails from all nodes
    candidate_emails: list[str] = []

    # Track which nodes have run
    nodes_completed: list[str] = []

    @classmethod
    def from_lead(cls, lead: LeadInput) -> "DiscoveryContext":
        """Initialize from lead's existing data."""
        return cls(
            company_domain=lead.company_domain,
            website=lead.website,
            linkedin_url=lead.linkedin_url,
            twitter_url=lead.twitter_url,
            facebook_url=lead.facebook_url,
            youtube_url=lead.youtube_url,
            instagram_url=lead.instagram_url,
        )

    def merge_node_result(self, result: NodeResult):
        """Merge a node's discoveries into the context."""
        data = result.data
        # Only update fields that were None (don't overwrite existing data)
        if not self.company_domain and data.get("company_domain"):
            self.company_domain = data["company_domain"]
        if not self.website and data.get("website"):
            self.website = data["website"]
        if not self.linkedin_url and data.get("linkedin_url"):
            self.linkedin_url = data["linkedin_url"]
        # ... same for other social URLs

        # Always accumulate candidate emails
        if result.found_email:
            self.candidate_emails.append(result.found_email)
        self.candidate_emails.extend(result.found_emails)

    def has_domain(self) -> bool:
        return self.company_domain is not None
```

### Usage in Waterfall

```python
ctx = DiscoveryContext.from_lead(lead)

# Node 1: Perplexity might find domain + LinkedIn
perplexity_result = await perplexity_search(lead, config)
ctx.merge_node_result(perplexity_result)

# Node 2: Website scraper now has domain (if Perplexity found it)
if ctx.has_domain():
    scrape_result = await scrape_website_for_emails(ctx, config)
    ctx.merge_node_result(scrape_result)

# Node 3: Pattern gen now has domain too
if ctx.has_domain():
    pattern_result = await generate_patterns_with_context(ctx, config)
    ctx.merge_node_result(pattern_result)

# Node 4: Browser discovery knows which social pages exist
browser_result = await browser_discover_email(ctx, config)
ctx.merge_node_result(browser_result)
```

### Key Data Flows

| Source Node | Discovers | Used By |
|-------------|-----------|---------|
| Perplexity | `company_domain` | Website scraper, Pattern generator |
| Perplexity | `linkedin_url` | Browser discovery (skips LinkedIn search) |
| Perplexity | `facebook_url` | Browser discovery (scrapes directly) |
| Perplexity | `email` | Added to candidates |
| Website scraper | `emails` | Added to candidates |
| Pattern generator | `email patterns` | Added to candidates → Mailin batch |
| Browser discovery | `emails` | Added to candidates |

## Acceptance Criteria

- [ ] DiscoveryContext initializes correctly from LeadInput
- [ ] Node results merge without overwriting existing data
- [ ] Domain discovered by Perplexity is used by pattern generator
- [ ] Social URLs discovered by Perplexity are used by browser discovery (skip search)
- [ ] All candidate emails accumulate correctly
- [ ] Works when lead starts with full data (nothing gets overwritten)
- [ ] Works when lead starts with nothing (everything gets discovered progressively)
