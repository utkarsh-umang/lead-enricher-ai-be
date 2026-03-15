# EF-6: Top-Level Matcher Function

**Epic**: Epic 2 — Name-Email Ownership Matcher
**Priority**: High
**Depends On**: EF-4, EF-5

## Description

Create the public-facing function that combines all matching logic into a single call. This is what the orchestrator (Epic 8) will call.

## Function

```python
def verify_email_ownership(lead: LeadInput, config: Config = None) -> NodeResult:
    """
    Check if lead.existing_email likely belongs to the lead.
    Uses name matching + brand matching from EF-4 and EF-5.

    Args:
        lead: LeadInput with existing_email set
        config: Optional config overrides

    Returns:
        NodeResult with:
        - confidence: 0.0-1.0 ownership score
        - data: {"match_type": "...", "matched_variation": "...", "details": "..."}
    """
```

Logic:
1. If no `existing_email` → return NodeResult with confidence 0.0
2. Check if domain is blacklisted → return confidence 0.0, error "hosting platform email"
3. Run `match_email_to_name()` with all available context (name, company, podcast)
4. Return NodeResult with confidence and match details

## Acceptance Criteria

- [ ] Can be called standalone from notebook: `verify_email_ownership(lead)`
- [ ] Returns correct confidence for known good matches
- [ ] Returns 0.0 for blacklisted domains
- [ ] Returns 0.0 when no existing_email
- [ ] Match details included in NodeResult.data for debugging
