# EF-19: End-to-End Test Notebook

**Epic**: Epic 9 — End-to-End Testing Pipeline
**Priority**: High
**Depends On**: EF-15 (batch processing), EF-17 (loader), EF-18 (exporter)

## Description

Create a Jupyter notebook that runs the full pipeline end-to-end: load leads from Google Sheet / CSV → run `find_emails_batch()` → export split CSVs. This is the primary way the user will interact with the system.

## Implementation

Create `email_finder/notebooks/test_email_finder.ipynb`:

### Cell 1: Setup & Config

```python
import sys
sys.path.append("..")  # or appropriate path

from email_finder import find_emails_batch
from email_finder.models import LeadInput
from email_finder.config import Config
from email_finder.io.loader import load_leads_from_csv, load_leads_from_google_sheet
from email_finder.io.exporter import export_results

config = Config()  # Loads from env
```

### Cell 2: Load Leads

```python
# Option A: From CSV
leads = load_leads_from_csv("path/to/needs_enrichment.csv")

# Option B: From Google Sheet
# leads = load_leads_from_google_sheet(
#     "https://docs.google.com/spreadsheets/d/...",
#     sheet_name="Needs_Enrichment"
# )

print(f"Loaded {len(leads)} leads")
leads[0]  # Preview first lead
```

### Cell 3: Run Pipeline

```python
results = await find_emails_batch(leads, config)
```

### Cell 4: Preview Results

```python
# Quick summary
for lead, result in zip(leads, results):
    status_emoji = {"verified": "Y", "catch_all": "~", "not_found": "X", "invalid": "X"}
    print(f"[{status_emoji.get(result.status, '?')}] {lead.full_name}: {result.email or 'N/A'} ({result.status})")
```

### Cell 5: Export

```python
files = export_results(leads, results, output_dir="./output", prefix="test_run")
print(f"Enriched: {files['enriched']}")
print(f"Still needs: {files['needs_enrichment']}")
```

### Cell 6: Debug (optional)

```python
# Inspect a specific lead's discovery log
idx = 3  # Change to inspect different leads
print(f"Lead: {leads[idx].full_name}")
for entry in results[idx].discovery_log:
    print(f"  [{entry['node']}] {entry['result']}")
```

## Test Scenarios to Cover

| Scenario | Input | Expected Output |
|----------|-------|----------------|
| Guest, no email, no domain | name + company only | System discovers domain via Perplexity → generates patterns → Mailin verifies |
| Host, email present, valid | name + company + email | Flow A confirms ownership, Mailin verifies deliverability → "verified" |
| Host, email present, invalid | name + email that Mailin rejects | Flow A → Mailin says invalid → Flow B finds alternative |
| Guest, has LinkedIn already | name + company + linkedin_url | Perplexity skips LinkedIn search, still finds domain → patterns |
| Lead with no data found | obscure name + company | All nodes fail → "not_found" in still_needs CSV |
| Catch-all domain | name + domain that accepts everything | Detected as catch-all, best pattern picked |

## Acceptance Criteria

- [ ] Notebook runs end-to-end without errors
- [ ] Loads leads from CSV successfully
- [ ] Loads leads from Google Sheet successfully
- [ ] Runs full pipeline with progress output
- [ ] Exports two CSVs (enriched + still_needs)
- [ ] Summary stats printed
- [ ] Discovery log inspectable for debugging
- [ ] Works with at least 10 real leads from Needs_Enrichment sheet
