"""
Mailin bulk email verification via browser automation (Crawl4AI / Playwright).

Mailin has no public API — this module drives the web UI to:
  1. Log in with Mailin credentials.
  2. Upload a CSV of candidate email addresses for bulk verification.
  3. Poll until processing completes (or timeout).
  4. Download / scrape the results and return a {email → status} map.
  5. Clean up temp files and the browser session.

Also provides `resolve_catch_all_domains` (EF-13) to detect catch-all domains
from Mailin results and pick the best candidate email for each lead.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import re
import tempfile
import time
from pathlib import Path
from typing import Optional

from email_finder.config import Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mailin URL constants
# ---------------------------------------------------------------------------
_MAILIN_BASE       = "https://app.mailin.ai"
_MAILIN_LOGIN      = f"{_MAILIN_BASE}/signin"
_MAILIN_DASHBOARD  = f"{_MAILIN_BASE}/dashboard"
_MAILIN_VERIFY     = f"{_MAILIN_BASE}/verification"

# How often (seconds) to poll the page while waiting for bulk results
_POLL_INTERVAL = 10

# Valid status strings returned by Mailin
_KNOWN_STATUSES = {"valid", "invalid", "catch_all", "unknown", "risky", "disposable"}

# Regex to detect completion markers in page content
_RE_STATUS = re.compile(
    r"(valid|invalid|catch[_\s]?all|unknown|risky|disposable)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def _write_temp_csv(emails: list[str]) -> Path:
    """Write *emails* to a temp CSV file and return its path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8"
    )
    writer = csv.writer(tmp)
    writer.writerow(["email"])
    for email in emails:
        writer.writerow([email.strip()])
    tmp.close()
    return Path(tmp.name)


def _parse_results_csv(csv_text: str) -> dict[str, str]:
    """Parse a downloaded Mailin results CSV into {email: status}."""
    results: dict[str, str] = {}
    reader = csv.DictReader(csv_text.splitlines())
    for row in reader:
        email = (row.get("email") or row.get("Email") or "").strip().lower()
        status = (
            row.get("status") or row.get("Status") or
            row.get("result") or row.get("Result") or "unknown"
        ).strip().lower()
        if email:
            results[email] = status if status in _KNOWN_STATUSES else "unknown"
    return results


def _parse_results_table(page_content: str, emails: list[str]) -> dict[str, str]:
    """
    Fallback: scan page content for email-status pairs when no CSV is
    available.  Returns best-effort results with "unknown" for any email
    whose status could not be determined.
    """
    results: dict[str, str] = {}
    lower = page_content.lower()

    for email in emails:
        email_lower = email.lower()
        idx = lower.find(email_lower)
        if idx == -1:
            results[email_lower] = "unknown"
            continue

        # Look for a status keyword in the surrounding 200 chars
        snippet = lower[idx: idx + 200]
        match = _RE_STATUS.search(snippet)
        if match:
            raw = match.group(1).lower().replace(" ", "_").replace("-", "_")
            results[email_lower] = "catch_all" if "catch" in raw else raw
        else:
            results[email_lower] = "unknown"

    return results


# ---------------------------------------------------------------------------
# Browser automation steps
# ---------------------------------------------------------------------------

async def _run_playwright_automation(
    emails: list[str],
    csv_path: Path,
    config: Config,
    headless: bool = True,
) -> dict[str, str]:
    """
    Drive the Mailin web UI via Playwright to upload *csv_path* and return
    verification results.

    Set ``headless=False`` (via ``mailin_batch_verify(..., headless=False)``)
    to open a visible browser window for debugging.
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError as exc:
        raise RuntimeError(
            "playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    timeout_ms = config.browser_timeout * 1000
    results: dict[str, str] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)

        async def _screenshot(label: str) -> None:
            """Save a debug screenshot to /tmp; logs the path."""
            try:
                path = f"/tmp/mailin_debug_{label}.png"
                await page.screenshot(path=path, full_page=True)
                logger.info("Screenshot saved: %s", path)
            except Exception:
                pass

        try:
            # ------------------------------------------------------------------
            # 1. Login
            # ------------------------------------------------------------------
            logger.info("Navigating to Mailin login page …")
            await page.goto(_MAILIN_LOGIN, wait_until="networkidle")
            await _screenshot("01_login_page")

            # If already logged in, Mailin redirects away from /signin
            if "/signin" not in page.url:
                logger.info("Already logged in (redirected to %s).", page.url)
            else:
                # Try common selectors for email + password fields
                email_sel = (
                    'input[type="email"], input[name="email"], '
                    'input[placeholder*="email" i], input[id*="email" i]'
                )
                password_sel = (
                    'input[type="password"], input[name="password"], '
                    'input[placeholder*="password" i], input[id*="password" i]'
                )

                await page.locator(email_sel).first.fill(config.mailin_email)
                await page.locator(password_sel).first.fill(config.mailin_password)
                await _screenshot("02_login_filled")

                # Submit — try submit button first, then Enter key
                submit = page.locator(
                    'button[type="submit"], input[type="submit"], '
                    'button:has-text("Sign In"), button:has-text("Sign in"), '
                    'button:has-text("Login"), button:has-text("Log in")'
                ).first
                if await submit.count():
                    await submit.click()
                else:
                    await page.locator(password_sel).first.press("Enter")

                try:
                    await page.wait_for_url(
                        lambda url: "/signin" not in url,
                        timeout=timeout_ms,
                    )
                except PWTimeout:
                    await _screenshot("03_login_failed")
                    raise RuntimeError(
                        "Mailin login failed — screenshot saved to /tmp/mailin_debug_03_login_failed.png. "
                        "Check credentials or inspect the login page selectors."
                    )

            logger.info("Logged in. Current URL: %s", page.url)

            # ------------------------------------------------------------------
            # 2. Navigate to bulk verification
            # ------------------------------------------------------------------
            await page.goto(_MAILIN_VERIFY, wait_until="networkidle")
            await _screenshot("04_verify_page")

            # ------------------------------------------------------------------
            # 3. Upload CSV via file chooser (React-friendly approach)
            # Page has a "browse" link that triggers the OS file picker.
            # Using expect_file_chooser fires the React change event properly.
            # ------------------------------------------------------------------
            logger.info("Uploading CSV with %d emails …", len(emails))
            try:
                async with page.expect_file_chooser(timeout=timeout_ms) as fc_info:
                    await page.locator("text=browse").click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(str(csv_path))
                logger.info("File attached via file chooser.")
            except Exception as exc:
                await _screenshot("05_upload_failed")
                raise RuntimeError(f"CSV upload failed: {exc}") from exc

            # Wait for the UI to register the file (React state update)
            await asyncio.sleep(2)
            await _screenshot("06_after_upload")

            # Confirm the "Confirm File Upload" modal if it appears
            confirm_btn = page.locator("button:has-text('Confirm & Upload')").first
            if await confirm_btn.count():
                await confirm_btn.click()
                logger.info("Clicked 'Confirm & Upload' modal button.")
                await asyncio.sleep(1)

            # ------------------------------------------------------------------
            # 4. Poll for completion
            # ------------------------------------------------------------------
            logger.info("Waiting for Mailin to process emails …")
            deadline = time.monotonic() + config.mailin_wait_timeout
            completed = False

            while time.monotonic() < deadline:
                await asyncio.sleep(_POLL_INTERVAL)
                content = await page.content()
                lower = content.lower()

                if "complete" in lower or "download" in lower or "results" in lower:
                    completed = True
                    break
                if "processing" in lower or "progress" in lower:
                    logger.debug("Still processing …")

            await _screenshot("07_after_processing")

            if not completed:
                logger.warning(
                    "Mailin wait timeout (%ds) reached — screenshot: /tmp/mailin_debug_07_after_processing.png",
                    config.mailin_wait_timeout,
                )

            # ------------------------------------------------------------------
            # 5. Retrieve results
            # ------------------------------------------------------------------
            try:
                async with page.expect_download(timeout=timeout_ms) as dl_info:
                    dl_btn = page.locator(
                        "button:has-text('Download'), a:has-text('Download'), "
                        "button:has-text('Export'), a:has-text('Export')"
                    ).first
                    if await dl_btn.count():
                        await dl_btn.click()
                download = await dl_info.value
                raw = Path(await download.path()).read_text(encoding="utf-8")
                results = _parse_results_csv(raw)
                logger.info("Results parsed from downloaded CSV (%d rows).", len(results))
            except Exception:
                content = await page.content()
                results = _parse_results_table(content, emails)
                logger.info("Results parsed from page table (%d rows).", len(results))

        finally:
            await _screenshot("99_final_state")
            await context.close()
            await browser.close()

    return results


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# EF-13: Catch-all detection and resolution
# ---------------------------------------------------------------------------

# Priority order for picking the "best guess" email on catch-all domains.
# Indices correspond to the pattern list produced by generate_email_patterns().
_CATCH_ALL_PRIORITY_PATTERNS = [
    lambda f, l, d: f"{f}.{l}@{d}",   # first.last  (most common)
    lambda f, l, d: f"{f}{l}@{d}",    # firstlast
    lambda f, l, d: f"{f[0]}{l}@{d}", # flast
]


def _domain_of(email: str) -> str:
    """Return the domain part of an email address."""
    return email.split("@", 1)[-1].lower()


def resolve_catch_all_domains(
    verification_results: dict[str, str],
    lead_patterns: dict[str, list[str]],
) -> dict[str, dict]:
    """
    Detect catch-all domains and resolve the best candidate email for each lead.

    Args:
        verification_results: ``{email: status}`` map returned by Mailin.
        lead_patterns:        ``{lead_id: [ordered pattern list]}`` — patterns
                              must be in the same priority order as produced by
                              ``generate_email_patterns()``.

    Returns:
        ``{lead_id: {"email": str | None, "is_catch_all": bool, "confidence": float, "status": str}}``
    """
    resolved: dict[str, dict] = {}

    for lead_id, patterns in lead_patterns.items():
        if not patterns:
            resolved[lead_id] = {
                "email": None, "is_catch_all": False,
                "confidence": 0.0, "status": "not_found",
            }
            continue

        # Collect statuses for this lead's patterns
        statuses = {p.lower(): verification_results.get(p.lower(), "unknown") for p in patterns}
        valid_emails = [e for e, s in statuses.items() if s == "valid"]

        # ------------------------------------------------------------------
        # Catch-all detection: ALL non-unknown patterns came back "valid"
        # ------------------------------------------------------------------
        non_unknown = [s for s in statuses.values() if s != "unknown"]
        is_catch_all = bool(non_unknown) and all(s == "valid" for s in non_unknown)

        if is_catch_all:
            # Pick best-guess by priority: first.last > firstlast > flast
            best_email: str | None = None
            for pattern_email in patterns:   # patterns already in priority order
                if pattern_email.lower() in statuses:
                    best_email = pattern_email.lower()
                    break  # first valid pattern = first.last format

            resolved[lead_id] = {
                "email": best_email,
                "is_catch_all": True,
                "confidence": 0.5,
                "status": "catch_all",
            }

        elif valid_emails:
            # Normal domain — one or more genuine valid emails
            # Pick by original pattern priority order
            best = None
            for p in patterns:
                if p.lower() in valid_emails:
                    best = p.lower()
                    break

            confidence = 0.9 if len(valid_emails) == 1 else 0.85
            resolved[lead_id] = {
                "email": best,
                "is_catch_all": False,
                "confidence": confidence,
                "status": "verified",
            }

        else:
            # No valid emails found
            resolved[lead_id] = {
                "email": None,
                "is_catch_all": False,
                "confidence": 0.0,
                "status": "not_found",
            }

    return resolved


async def mailin_batch_verify(
    emails: list[str],
    config: Config,
    headless: bool = True,
) -> dict[str, str]:
    """
    Automate Mailin bulk email verification.

    Args:
        emails:   List of email addresses to verify.
        config:   Config with Mailin credentials and timeout settings.
        headless: Set False to open a visible browser window for debugging.
                  Screenshots are always saved to /tmp/mailin_debug_*.png.

    Returns:
        Dict mapping ``email → status`` where status is one of:
        ``"valid"``, ``"invalid"``, ``"catch_all"``, ``"unknown"``.

    Raises:
        RuntimeError: If login fails or the browser session crashes.
    """
    if not emails:
        return {}

    csv_path: Optional[Path] = None
    try:
        csv_path = _write_temp_csv(emails)
        logger.info("Temp CSV written to %s", csv_path)

        results = await _run_playwright_automation(emails, csv_path, config, headless=headless)

        # Ensure every submitted email has a status
        for email in emails:
            results.setdefault(email.lower(), "unknown")

        return results

    finally:
        if csv_path and csv_path.exists():
            csv_path.unlink()
            logger.debug("Temp CSV deleted: %s", csv_path)
