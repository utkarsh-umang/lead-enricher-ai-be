# EF-15: Batch Processing with Mailin Integration

**Epic**: Epic 8 — Orchestration
**Priority**: Highest
**Depends On**: EF-12, EF-13, EF-14

## Description

Implement the primary notebook function `find_emails_batch()` that processes multiple leads and runs a single Mailin batch verification at the end.

## Implementation

```python
async def find_emails_batch(
    leads: list[LeadInput],
    config: Config = None
) -> list[EmailFinderResult]:
    """
    Primary function for notebook usage.

    Three phases:
    1. Discovery: Run each lead through find_email() waterfall
    2. Verification: Batch all candidates through Mailin
    3. Resolution: Map Mailin results back, set final statuses
    """
```

### Phase 1: Discovery (per lead, sequential)

```python
results = []
for lead in leads:
    result = await find_email(lead, config)
    results.append(result)
    # Log progress: f"Processed {i+1}/{len(leads)}: {lead.full_name}"
```

### Phase 2: Batch Verification (one Mailin run)

```python
# Collect ALL candidate emails across all leads
all_candidates = set()
for result in results:
    if result.email:
        all_candidates.add(result.email)
    all_candidates.update(result._all_candidates)

# Single Mailin bulk verification
verification_map = await mailin_batch_verify(list(all_candidates), config)
```

### Phase 3: Resolution (map results back)

```python
for result in results:
    if result.email in verification_map:
        mailin_status = verification_map[result.email]

        if mailin_status == "valid":
            result.status = "verified"
            result.confidence = max(result.confidence, 0.9)
        elif mailin_status == "invalid":
            result.status = "invalid"
            result.confidence = 0.0
            # Check if any alternative candidates are valid
            for alt in result._all_candidates:
                if verification_map.get(alt) == "valid":
                    result.email = alt
                    result.status = "verified"
                    break
        elif mailin_status == "catch_all":
            result.status = "catch_all"
            result.confidence = min(result.confidence, 0.5)

# Handle catch-all domain resolution (from EF-13)
resolve_catch_all_domains(verification_map, lead_patterns)
```

### Progress Reporting

Since this runs in a notebook, print progress:
```
[1/50] John Smith - Searching... Found domain: acme.com
[2/50] Jane Doe - Searching... No domain found, trying browser...
...
[Mailin] Uploading 342 candidates for verification...
[Mailin] Verification complete. 45 valid, 280 invalid, 17 catch-all.
[Results] 50 leads processed: 35 verified, 5 catch-all, 10 not found.
```

## Notebook Usage

```python
from email_finder import find_emails_batch
from email_finder.models import LeadInput

leads = [
    LeadInput(full_name="John Smith", company_name="Acme RE", podcast_name="The Acme Show"),
    LeadInput(full_name="Jane Doe", company_name="Beta Corp", existing_email="jane@beta.com"),
    # ... loaded from Google Sheet
]

results = await find_emails_batch(leads)

# results[0].email, results[0].status, results[0].confidence
# Easy to write back to sheet as a list of dicts
```

## Acceptance Criteria

- [ ] Processes list of leads sequentially through discovery
- [ ] Collects all candidate emails into one set
- [ ] Runs exactly ONE Mailin batch verification for all candidates
- [ ] Maps Mailin results back to correct leads
- [ ] Handles catch-all domains (from EF-13)
- [ ] Falls back to alternative candidates when primary is invalid
- [ ] Prints progress to notebook output
- [ ] Returns list of EmailFinderResult in same order as input leads
