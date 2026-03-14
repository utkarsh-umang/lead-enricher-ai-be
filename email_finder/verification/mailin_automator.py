"""
Mailin bulk email verification via browser automation (Crawl4AI / Playwright).

Mailin has no public API — this module drives the web UI to:
  1. Log in with Mailin credentials.
  2. Upload a CSV of candidate email addresses for bulk verification.
  3. Poll until processing completes (or timeout).
  4. Download / scrape the results and return a {email → status} map.
  5. Clean up temp files and the browser session.
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
_MAILIN_BASE       = "https://app.mailin.io"
_MAILIN_LOGIN      = f"{_MAILIN_BASE}/login"
_MAILIN_DASHBOARD  = f"{_MAILIN_BASE}/dashboard"
_MAILIN_VERIFY     = f"{_MAILIN_BASE}/email-verification"

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
) -> dict[str, str]:
    """
    Drive the Mailin web UI via Playwright (exposed through Crawl4AI's
    underlying browser) to upload *csv_path* and return verification results.

    Uses Playwright directly for fine-grained interaction (form fills, file
    upload, polling) while delegating browser lifecycle to Crawl4AI.
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
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            # ------------------------------------------------------------------
            # 1. Login
            # ------------------------------------------------------------------
            logger.info("Navigating to Mailin login page …")
            await page.goto(_MAILIN_LOGIN, wait_until="networkidle")

            await page.fill('input[type="email"], input[name="email"]', config.mailin_email)
            await page.fill('input[type="password"], input[name="password"]', config.mailin_password)
            await page.click('button[type="submit"]')

            try:
                await page.wait_for_url(f"{_MAILIN_BASE}/**", timeout=timeout_ms)
            except PWTimeout:
                raise RuntimeError("Mailin login failed — check credentials or login page structure.")

            logger.info("Logged into Mailin successfully.")

            # ------------------------------------------------------------------
            # 2. Navigate to bulk verification
            # ------------------------------------------------------------------
            await page.goto(_MAILIN_VERIFY, wait_until="networkidle")

            # Try to click a "Bulk Email" tab if present
            bulk_tab = page.locator("text=/bulk/i").first
            if await bulk_tab.count():
                await bulk_tab.click()

            # ------------------------------------------------------------------
            # 3. Upload CSV
            # ------------------------------------------------------------------
            logger.info("Uploading CSV with %d emails …", len(emails))
            upload_input = page.locator('input[type="file"]').first
            for attempt in range(2):
                try:
                    await upload_input.set_input_files(str(csv_path))
                    break
                except Exception as exc:
                    if attempt == 1:
                        raise RuntimeError(f"CSV upload failed after retry: {exc}") from exc
                    logger.warning("Upload attempt 1 failed (%s), retrying …", exc)
                    await asyncio.sleep(2)

            # Click verify button
            verify_btn = page.locator("button", has_text=re.compile(r"verify", re.IGNORECASE)).first
            if await verify_btn.count():
                await verify_btn.click()

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

            if not completed:
                logger.warning(
                    "Mailin wait timeout (%ds) reached — returning partial results.",
                    config.mailin_wait_timeout,
                )

            # ------------------------------------------------------------------
            # 5. Retrieve results
            # ------------------------------------------------------------------
            # Option A: download CSV
            try:
                async with page.expect_download(timeout=timeout_ms) as dl_info:
                    dl_btn = page.locator("button, a", has_text=re.compile(r"download", re.IGNORECASE)).first
                    if await dl_btn.count():
                        await dl_btn.click()
                download = await dl_info.value
                import io
                raw = Path(await download.path()).read_text(encoding="utf-8")
                results = _parse_results_csv(raw)
                logger.info("Results parsed from downloaded CSV (%d rows).", len(results))
            except Exception:
                # Option B: scrape results table
                content = await page.content()
                results = _parse_results_table(content, emails)
                logger.info("Results parsed from page table (%d rows).", len(results))

        finally:
            await context.close()
            await browser.close()

    return results


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def mailin_batch_verify(emails: list[str], config: Config) -> dict[str, str]:
    """
    Automate Mailin bulk email verification.

    Args:
        emails: List of email addresses to verify.
        config: Config with Mailin credentials and timeout settings.

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

        results = await _run_playwright_automation(emails, csv_path, config)

        # Ensure every submitted email has a status
        for email in emails:
            results.setdefault(email.lower(), "unknown")

        return results

    finally:
        if csv_path and csv_path.exists():
            csv_path.unlink()
            logger.debug("Temp CSV deleted: %s", csv_path)
