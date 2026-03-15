# EF-13: Catch-All Domain Handling

**Epic**: Epic 7 — Mailin Batch Verification
**Priority**: Medium
**Depends On**: EF-12, EF-10

## Description

Add logic to detect and handle catch-all domains from Mailin verification results. When a domain accepts all emails (catch-all), all pattern-generated candidates will show as "valid" — we need to detect this and pick the best guess.

## Implementation

Add to `email_finder/verification/mailin_automator.py` or a shared utility:

```python
def resolve_catch_all_domains(
    verification_results: dict[str, str],
    lead_patterns: dict[str, list[str]]  # {lead_id: [pattern1, pattern2, ...]}
) -> dict[str, dict]:
    """
    Detect catch-all domains and resolve best email for each lead.

    Args:
        verification_results: {email: status} from Mailin
        lead_patterns: {lead_id: [list of generated patterns]}

    Returns:
        {lead_id: {"email": "best@domain.com", "is_catch_all": True/False}}
    """
```

### Detection Logic

For each lead's domain:
1. Count how many of their generated patterns returned "valid"
2. If ALL patterns are "valid" → likely catch-all domain
3. If only 1-2 are "valid" → genuine valid emails

### Resolution for Catch-All Domains

When catch-all detected:
- Mark status as `"catch_all"` (not `"verified"`)
- Pick the most common email format as best guess:
  1. `first.last@domain` (most common professionally)
  2. `firstlast@domain` (second most common)
  3. `flast@domain` (third)
- Set confidence to 0.5 (medium — it might work but not confirmed)

### Resolution for Normal Domains

When not catch-all:
- Pick the valid email(s)
- If exactly one valid → that's the email, confidence 0.9
- If multiple valid → pick by pattern priority order, confidence 0.85

## Acceptance Criteria

- [ ] Detects catch-all: 10/10 patterns valid for "acme.com" → flagged as catch-all
- [ ] Normal case: 1/10 patterns valid → picks that one, high confidence
- [ ] Catch-all resolution picks first.last@ format as default
- [ ] Returns proper `is_catch_all` flag for downstream status mapping
- [ ] Handles edge case: 0/10 patterns valid (no valid email found)
