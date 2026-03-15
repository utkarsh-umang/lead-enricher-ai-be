# Email Finder System — Execution Plan

## Context

Podscan list-building produces leads (hosts and guests) that need email finding and/or verification. A Google Sheets script handles basic substring matching, but leads it can't resolve go into "Needs Enrichment". This system handles that bucket — finding emails for guests, verifying ownership for hosts, and using a waterfall of strategies ordered by cost.

**Usage**: Python module called from Jupyter notebook. Input: lead dict → Output: email + status.

---

## Epic 1: Foundation & Data Models

Sets up the module structure, data contracts, and configuration. Everything else depends on this.

### EF-1: Project scaffolding
Create the `email_finder/` directory structure with all `__init__.py` files.
```
email_finder/
    __init__.py
    models.py
    config.py
    finder.py              (placeholder)
    verification/
        __init__.py
        name_email_matcher.py   (placeholder)
        mailin_automator.py     (placeholder)
    discovery/
        __init__.py
        perplexity_search.py    (placeholder)
        website_scraper.py      (placeholder)
        pattern_generator.py    (placeholder)
        browser_discovery.py    (placeholder)
```
**AC**: Module is importable from a notebook with `from email_finder import ...`

### EF-2: Define data models
Create `models.py` with Pydantic models:
```python
class LeadInput(BaseModel):
    full_name: str
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    existing_email: Optional[str] = None
    podcast_name: Optional[str] = None
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    facebook_url: Optional[str] = None
    youtube_url: Optional[str] = None
    instagram_url: Optional[str] = None

class EmailFinderResult(BaseModel):
    email: Optional[str] = None
    status: str  # "verified" | "unverified" | "catch_all" | "invalid" | "not_found"
    confidence: float = 0.0
    source: str = ""
    verification_details: dict = {}
    discovery_log: list = []

class NodeResult(BaseModel):
    found_email: Optional[str] = None
    found_emails: list[str] = []  # Multiple candidates
    confidence: float = 0.0
    data: dict = {}  # Extra discovered data (domain, social urls, etc.)
    error: Optional[str] = None
```
**AC**: Models can be instantiated, serialized to dict, validated by Pydantic.

### EF-3: Configuration module
Create `config.py`:
- Mailin credentials (email, password)
- Perplexity API key (from env)
- Thresholds: `name_match_threshold=0.6`, `lcs_min_length=4`
- Generic email prefixes to filter: `["info", "support", "hello", "contact", "admin", "team", "office", "sales"]`
- Email pattern priority order
- Browser timeout settings
- Mailin wait timeout

**AC**: Config loads from env vars with sensible defaults. Can be overridden per-call.

---

## Epic 2: Name-Email Ownership Matcher

Port the Google Script's LCS matching logic to Python and enhance it with name-aware pattern matching. This is used in Flow A (verify existing email belongs to lead).

### EF-4: Port core matching utilities from Google Script
Port to `verification/name_email_matcher.py`:
- `normalize(text)` — transliteration (accented chars → ASCII) + lowercase + strip non-alphanumeric
- `transliterate(text)` — accent map (á→a, é→e, ñ→n, etc.)
- `longest_common_substring(str1, str2)` — dynamic programming LCS
- `split_email(email)` — returns `{local, domain}`
- `is_blacklisted_domain(domain)` — podcast hosting platforms (spreaker, anchor, spotify, etc.)

**AC**: Unit test — `normalize("José García")` → `"josegarcia"`. LCS of `"johnsmith"` and `"jsmith"` returns `"smith"`.

### EF-5: Enhanced name-email matching logic
Add to `verification/name_email_matcher.py`:
- `generate_name_variations(full_name)` → list of expected local parts: `["firstname", "lastname", "first.last", "firstlast", "flast", "firstl", "f.last", "last.first", "first_last", "first-last"]`
- `match_email_to_name(email, full_name, company_name, podcast_name)` → confidence 0.0-1.0
  - Check email local part against name variations (exact match → 1.0, LCS match → 0.6-0.8)
  - Check email domain brand against company name (like Google Script does)
  - Check email domain brand against podcast name (ported from Google Script's `extractBrandCandidates`)
- `extract_domain_brand(domain)` — get brand portion of domain (before first dot)

**AC**: `match_email_to_name("j.smith@acmere.com", "John Smith", "Acme Real Estate")` returns confidence > 0.6

### EF-6: Top-level matcher function
Add public function:
```python
def verify_email_ownership(lead: LeadInput) -> NodeResult:
    """
    Check if lead.existing_email likely belongs to the lead.
    Uses name matching + brand matching.
    Returns NodeResult with confidence score.
    """
```
**AC**: Can be called standalone from notebook for testing. Returns confidence + match details.

---

## Epic 3: Perplexity Profile & Email Discovery

Use Perplexity to search the internet for the lead's profiles, email, and domain. Smart prompt construction — only searches for what's missing.

### EF-7: Perplexity search node
Create `discovery/perplexity_search.py`:
- Reuses `PerplexityService` from `llm_utils/gpt_utils.py`
- Builds prompt dynamically based on what fields are missing on the lead:
  - Always ask for: professional email
  - Only if missing: LinkedIn URL, company domain/website, Facebook, YouTube, Twitter
  - Include known info as context: "John Smith is the host of The Acme Show podcast at Acme Real Estate"
- Parse Perplexity's response to extract structured data (email, urls, domain)
- Return `NodeResult` with all discovered data

**AC**: Given a lead with `full_name="John Smith"` and `company_name="Acme RE"` but no LinkedIn, returns a NodeResult with discovered LinkedIn URL and/or email. If LinkedIn was already provided, the prompt doesn't ask for it.

### EF-8: Perplexity response parser
Add structured parsing for Perplexity's free-text response:
- Extract emails via regex
- Extract URLs and classify them (LinkedIn, Facebook, YouTube, Twitter, website)
- Extract domain from found website URLs
- Handle cases where Perplexity returns "I couldn't find..." gracefully

**AC**: Parser correctly extracts email and LinkedIn URL from a Perplexity response containing mixed text and links.

---

## Epic 4: Website Email Extraction

Scrape company/podcast websites to find email addresses on contact and about pages.

### EF-9: Website email scraper node
Create `discovery/website_scraper.py`:
- Reuses `get_about_us_link()` from `scraper/homepage_scraper.py`
- Reuses `scrape_about_us_content()` from `scraper/about_us_scraper.py`
- Reuses `normalize_url()` from `utils/helpers.py`
- New logic:
  - Find contact page (look for /contact, /contact-us, /about in addition to existing about-us logic)
  - Scrape page content
  - Extract emails via regex: `r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'`
  - Filter out generic prefixes (from config)
  - Filter out blacklisted domains (podcast hosting platforms)
  - Return remaining emails as candidates

**AC**: Given `company_domain="acmere.com"`, scrapes the site and returns non-generic email addresses found. Skips if no domain available.

---

## Epic 5: Email Pattern Generation

Generate common professional email patterns from name + domain. These become candidates for Mailin batch verification.

### EF-10: Pattern generator node
Create `discovery/pattern_generator.py`:
- Input: `full_name` + `company_domain` (required — skip if no domain)
- Parse full_name into first_name, last_name (handle middle names, suffixes)
- Generate patterns in priority order:
  ```
  first.last@domain     (most common)
  firstlast@domain
  flast@domain
  first@domain
  last.first@domain
  firstl@domain
  f.last@domain
  first_last@domain
  first-last@domain
  last@domain
  ```
- Return as `NodeResult.found_emails` (list of candidates)

**AC**: `generate_patterns("John Smith", "acme.com")` returns `["john.smith@acme.com", "johnsmith@acme.com", "jsmith@acme.com", ...]`. Handles edge cases: hyphenated names, single-word names.

---

## Epic 6: Browser Automation Discovery

Use Crawl4AI to find and scrape social media pages for contact emails. Smart skip — only searches for platforms not already known; directly scrapes known pages.

### EF-11: Crawl4AI browser discovery node
Create `discovery/browser_discovery.py`:
- Uses Crawl4AI (Playwright under the hood)
- Smart skip logic:
  - If `lead.facebook_url` exists → scrape it directly, don't Google search
  - If `lead.youtube_url` exists → scrape it directly, don't Google search
  - For missing platforms → Google search: `"{name} {company} site:facebook.com"`
- For each found/known page:
  - Navigate to About/Contact section
  - Extract emails via regex
  - Filter generic emails
- Return all found emails as candidates

**AC**: Given a lead with `youtube_url` set, it scrapes that URL directly. Given a lead with no social links, it searches Google first. Returns any emails found on those pages.

---

## Epic 7: Mailin Batch Verification

Automate the Mailin web platform via Crawl4AI to bulk-verify all candidate emails in one shot.

### EF-12: Mailin bulk CSV automation
Create `verification/mailin_automator.py`:
- `mailin_batch_verify(emails: list[str], config: Config) -> dict[str, str]`
- Steps:
  1. Write emails to temp CSV file
  2. Launch Crawl4AI browser
  3. Navigate to Mailin verification page
  4. Login with credentials from config
  5. Upload CSV via file input element
  6. Click "Verify Emails"
  7. Wait for processing (poll until complete, respect timeout)
  8. Scrape or download results
  9. Parse into `{email: "valid" | "invalid" | "catch_all"}` map
  10. Clean up temp files
- Error handling: timeout, login failure, upload failure

**AC**: Given a list of 20 emails, automates Mailin end-to-end and returns a status map. Handles the Mailin UI flow correctly.

### EF-13: Catch-all domain handling
Add logic to detect catch-all domains from Mailin results:
- If ALL patterns for a lead's domain return "valid" → likely catch-all
- Mark as `catch_all` status
- Pick most common pattern format (first.last@) as the best guess

**AC**: When 10 patterns for "acme.com" all return valid, correctly identifies catch-all and selects first.last@ pattern.

---

## Epic 8: Orchestration — The Finder

Wire everything together into the main `finder.py` with Flow A, Flow B, and batch verification.

### EF-14: Single lead waterfall logic
Implement in `finder.py`:
```python
async def find_email(lead: LeadInput, config: Config) -> EmailFinderResult:
```
- **Flow A** (has existing_email):
  1. Run name_email_matcher → get ownership confidence
  2. Run perplexity_search → cross-reference + discover missing data
  3. Collect existing_email for Mailin batch
  4. If low confidence → also run Flow B for alternatives
- **Flow B** (no email):
  1. Perplexity search → try to find email directly + discover domain/profiles
  2. Website scraper → find emails on contact pages (if domain known)
  3. Pattern generator → generate all candidates (if domain known)
  4. Browser discovery → scrape known/found social pages for emails
  5. Collect all candidates for Mailin batch

Each node enriches the lead's data (discovered domain, social links) for downstream nodes.

**AC**: Single lead processes through the correct flow. Discovery log tracks what each node did and found.

### EF-15: Batch processing with Mailin integration
Implement in `finder.py`:
```python
async def find_emails_batch(leads: list[LeadInput], config: Config) -> list[EmailFinderResult]:
```
- Phase 1: Run `find_email()` for each lead (discovery phase)
- Phase 2: Collect ALL candidate emails across all leads
- Phase 3: Run `mailin_batch_verify()` once for all candidates
- Phase 4: Map Mailin results back → update each lead's status
  - Hosts: confirm/deny existing email
  - Guests: pick first valid pattern as email
  - Handle catch-all domains

**AC**: 10 leads processed end-to-end. Mailin runs exactly once. Each lead gets a final EmailFinderResult with correct status.

### EF-16: Discovery data propagation between nodes
Ensure that when a node discovers new data (e.g., Perplexity finds domain), that data is available to subsequent nodes:
- Perplexity finds `company_domain` → pattern generator uses it
- Perplexity finds `facebook_url` → browser discovery scrapes it directly
- Website scraper finds email → goes into Mailin batch

Implement as a mutable context dict that accumulates discoveries through the waterfall.

**AC**: Lead starts with only name+company. Perplexity finds domain. Pattern generator uses that domain to create patterns. All happens in one `find_email()` call.

---

## Epic 9: End-to-End Testing Pipeline

Load leads from Google Sheet / CSV (Needs_Enrichment tab), run the full pipeline, and export two output CSVs: enriched (email found) and still-needs-enrichment (email not found).

### EF-17: CSV / Google Sheet input loader
Create `email_finder/io/loader.py`:
- `load_leads_from_csv(file_path, column_mapping)` → list of LeadInput
- `load_leads_from_google_sheet(spreadsheet_url, sheet_name)` → list of LeadInput
- Default column mapping for Podscan Needs_Enrichment format
- Handles comma-separated emails, missing columns, empty rows

**AC**: Loads 50 leads from a real Needs_Enrichment CSV. All fields mapped correctly.

### EF-18: CSV output splitter — found vs not found
Create `email_finder/io/exporter.py`:
- `export_results(leads, results, output_dir, prefix)` → two CSVs
- **Enriched CSV**: leads where email was found — includes email, status, confidence, source
- **Still Needs CSV**: leads where email not found — includes failure reason, nodes tried, any discovered data (domain, LinkedIn, etc.)
- Prints summary report with counts and percentages

**AC**: 50 results correctly split into two CSVs. Summary shows verified/catch-all/not-found breakdown.

### EF-19: End-to-end test notebook
Create `email_finder/notebooks/test_email_finder.ipynb`:
- Cell 1: Setup & config
- Cell 2: Load leads from CSV or Google Sheet
- Cell 3: Run `find_emails_batch()`
- Cell 4: Preview results
- Cell 5: Export to CSVs
- Cell 6: Debug — inspect individual lead discovery logs
- Covers test scenarios: guest (no email), host (email present), host (invalid email), lead with existing social links, obscure lead (all fail)

**AC**: Notebook runs end-to-end with 10+ real leads. Two CSVs exported. Summary printed.

---

## Execution Order

| Order | Epic | Tickets | Depends On |
|-------|------|---------|------------|
| 1 | Epic 1: Foundation | EF-1, EF-2, EF-3 | — |
| 2 | Epic 2: Name Matcher | EF-4, EF-5, EF-6 | Epic 1 |
| 3 | Epic 3: Perplexity | EF-7, EF-8 | Epic 1 |
| 4 | Epic 4: Website Scraper | EF-9 | Epic 1 |
| 5 | Epic 5: Pattern Gen | EF-10 | Epic 1 |
| 6 | Epic 6: Browser Discovery | EF-11 | Epic 1 |
| 7 | Epic 7: Mailin | EF-12, EF-13 | Epic 1 |
| 8 | Epic 8: Orchestration | EF-14, EF-15, EF-16 | All above |
| 9 | Epic 9: E2E Testing | EF-17, EF-18, EF-19 | Epic 8 |

Epics 2-7 can be built in parallel — they're independent nodes. Epic 8 wires everything together. Epic 9 is the final validation.

---

## Key Existing Code to Reuse

| File | What | Used In |
|------|------|---------|
| [gpt_utils.py](llm_utils/gpt_utils.py) | `PerplexityService` | EF-7 (Perplexity search) |
| [homepage_scraper.py](scraper/homepage_scraper.py) | `get_about_us_link()` | EF-9 (Website scraper) |
| [about_us_scraper.py](scraper/about_us_scraper.py) | `scrape_about_us_content()` | EF-9 (Website scraper) |
| [helpers.py](utils/helpers.py) | `normalize_url()`, `is_valid_url()` | EF-9 (Website scraper) |
| Crawl4AI (in requirements.txt) | Browser automation | EF-11, EF-12 |
| Google Script (provided by user) | LCS + brand matching logic | EF-4, EF-5 (ported to Python) |

---

## Testing Strategy

- **Per-epic**: Each node testable standalone with a sample LeadInput
- **Integration (Epic 9)**: Load real "Needs Enrichment" leads → run full pipeline → export split CSVs
- **Edge cases**: No company, no domain found, all nodes fail → `not_found`, catch-all domains
- **Output validation**: Two CSVs — enriched (email found) + still needs (email not found)
