# EF-12: Mailin Bulk CSV Automation

**Epic**: Epic 7 — Mailin Batch Verification
**Priority**: High
**Depends On**: EF-1, EF-3

## Description

Create `email_finder/verification/mailin_automator.py` that automates the Mailin web platform via Crawl4AI to bulk-verify emails. Mailin has no API — this uses browser automation to upload a CSV and retrieve results.

## Implementation

```python
async def mailin_batch_verify(emails: list[str], config: Config) -> dict[str, str]:
    """
    Automate Mailin bulk email verification.

    Args:
        emails: List of email addresses to verify
        config: Config with Mailin credentials and timeout

    Returns:
        Dict mapping email → status: {"john@acme.com": "valid", "fake@bad.com": "invalid", ...}
        Possible statuses: "valid", "invalid", "catch_all", "unknown"
    """
```

### Automation Steps

1. **Prepare CSV**: Write emails to a temp CSV file (one column: "email")
2. **Launch browser**: Use Crawl4AI's `AsyncWebCrawler`
3. **Login to Mailin**:
   - Navigate to Mailin login page
   - Enter `config.mailin_email` and `config.mailin_password`
   - Submit login form
   - Wait for dashboard to load
4. **Navigate to Email Verification**:
   - Go to the verification page
   - Select "Bulk Email" tab
5. **Upload CSV**:
   - Find the file upload input element
   - Upload the temp CSV file
   - Click "Verify Emails" button
6. **Wait for processing**:
   - Poll the page for completion status
   - Respect `config.mailin_wait_timeout`
   - Handle progress indicators if available
7. **Retrieve results**:
   - Option A: Download results CSV if available
   - Option B: Scrape results table from the page
   - Parse into `{email: status}` map
8. **Cleanup**:
   - Delete temp CSV file
   - Close browser session

### Error Handling

- Login failure → raise with clear error message
- Upload failure → retry once, then raise
- Timeout waiting for results → return partial results if available
- Browser crash → cleanup and raise

## Acceptance Criteria

- [ ] Successfully logs into Mailin
- [ ] Uploads a CSV of 20 test emails
- [ ] Waits for verification to complete
- [ ] Returns correct status map for all emails
- [ ] Handles timeout gracefully (returns partial or raises)
- [ ] Cleans up temp files and browser session
- [ ] Works with both Standard and Catch-All verification types
