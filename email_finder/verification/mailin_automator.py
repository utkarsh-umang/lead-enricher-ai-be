"""
Mailin bulk email verification via browser automation (Playwright).

Two-phase async design (Mailin processes batches in the background):

  Phase 1 — Submit:
    mailin_submit_batch(emails, config) → task_id (str)
    Uploads a CSV, confirms the modal, and returns the Mailin Task ID.
    The browser session is closed immediately after — no waiting.

  Phase 2 — Fetch:
    mailin_fetch_results(task_id, emails, config) → {email: status}
    Opens a new session, navigates to Task Results, checks status, and
    downloads the completed CSV.  Raises RuntimeError if still processing.

Also provides `resolve_catch_all_domains` (EF-13).
"""

from __future__ import annotations

import asyncio
import csv
import logging
import re
import tempfile
from pathlib import Path
from typing import Optional

from email_finder.config import Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mailin URL constants
# ---------------------------------------------------------------------------
_MAILIN_BASE   = "https://app.mailin.ai"
_MAILIN_LOGIN  = f"{_MAILIN_BASE}/signin"
_MAILIN_VERIFY = f"{_MAILIN_BASE}/verification"

# Valid status strings returned by Mailin
_KNOWN_STATUSES = {"valid", "invalid", "catch_all", "unknown", "risky", "disposable"}

# Regex to detect status keywords in page text (fallback parser)
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
    Fallback: scan page content for email-status pairs when no CSV download
    is available.  Returns best-effort results with "unknown" for any email
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

        snippet = lower[idx: idx + 200]
        match = _RE_STATUS.search(snippet)
        if match:
            raw = match.group(1).lower().replace(" ", "_").replace("-", "_")
            results[email_lower] = "catch_all" if "catch" in raw else raw
        else:
            results[email_lower] = "unknown"

    return results


# ---------------------------------------------------------------------------
# Shared browser helpers
# ---------------------------------------------------------------------------

async def _screenshot(page, label: str) -> None:
    """Save a debug screenshot to /tmp; logs the path."""
    try:
        path = f"/tmp/mailin_debug_{label}.png"
        await page.screenshot(path=path, full_page=True)
        logger.info("Screenshot saved: %s", path)
    except Exception:
        pass


async def _login(page, config: Config, timeout_ms: int) -> None:
    """
    Navigate to the Mailin sign-in page and log in.
    No-op if the session is already authenticated (redirected away from /signin).
    """
    from playwright.async_api import TimeoutError as PWTimeout

    logger.info("Navigating to Mailin login page …")
    await page.goto(_MAILIN_LOGIN, wait_until="networkidle")
    await _screenshot(page, "01_login_page")

    if "/signin" not in page.url:
        logger.info("Already logged in (redirected to %s).", page.url)
        return

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
    await _screenshot(page, "02_login_filled")

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
        await _screenshot(page, "03_login_failed")
        raise RuntimeError(
            "Mailin login failed — screenshot saved to /tmp/mailin_debug_03_login_failed.png. "
            "Check credentials or inspect the login page selectors."
        )

    logger.info("Logged in. Current URL: %s", page.url)


# ---------------------------------------------------------------------------
# Phase 1 — Submit
# ---------------------------------------------------------------------------

async def _playwright_submit(
    emails: list[str],
    csv_path: Path,
    config: Config,
    headless: bool = True,
) -> str:
    """
    Upload *csv_path* to Mailin, confirm the modal, and return the Task ID.
    The browser is closed immediately — Mailin processes the batch async.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    timeout_ms = config.browser_timeout * 1000

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            await _login(page, config, timeout_ms)

            # Navigate to Email Verification page
            await page.goto(_MAILIN_VERIFY, wait_until="networkidle")
            await _screenshot(page, "04_verify_page")

            # Upload CSV via the "browse" link (fires React change event properly)
            logger.info("Uploading CSV with %d emails …", len(emails))
            try:
                async with page.expect_file_chooser(timeout=timeout_ms) as fc_info:
                    await page.locator("text=browse").click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(str(csv_path))
                logger.info("File attached via file chooser.")
            except Exception as exc:
                await _screenshot(page, "05_upload_failed")
                raise RuntimeError(f"CSV upload failed: {exc}") from exc

            # Wait for "Confirm File Upload" modal
            await asyncio.sleep(2)
            await _screenshot(page, "06_confirm_modal")

            confirm_btn = page.locator("button:has-text('Confirm & Upload')").first
            if await confirm_btn.count():
                await confirm_btn.click()
                logger.info("Clicked 'Confirm & Upload'.")
            else:
                await _screenshot(page, "06b_no_confirm_btn")
                raise RuntimeError(
                    "Confirm & Upload button not found — "
                    "check /tmp/mailin_debug_06_confirm_modal.png"
                )

            # Wait for Task Results table to appear (auto-redirect after confirm)
            await page.wait_for_selector("table tbody tr", timeout=30_000)
            await _screenshot(page, "07_task_submitted")

            # Scrape the Task ID from the first row (most recently submitted)
            task_id = (
                await page.locator("table tbody tr:first-child td:first-child").inner_text()
            ).strip()
            logger.info("Mailin Task ID: %s", task_id)
            return task_id

        finally:
            await _screenshot(page, "99_final_state")
            await context.close()
            await browser.close()


async def mailin_submit_batch(
    emails: list[str],
    config: Config,
    headless: bool = True,
) -> str:
    """
    Upload *emails* to Mailin for bulk verification and return the Task ID.

    Mailin processes batches asynchronously — this function returns immediately
    after the upload is confirmed.  Use ``mailin_fetch_results`` once Mailin
    has finished processing.

    Args:
        emails:   List of email addresses to verify.
        config:   Config with Mailin credentials.
        headless: Set False to watch the browser window (useful for debugging).

    Returns:
        Mailin Task ID string (e.g. ``"30394406"``).
    """
    if not emails:
        raise ValueError("emails list is empty")

    csv_path: Optional[Path] = None
    try:
        csv_path = _write_temp_csv(emails)
        logger.info("Temp CSV written to %s", csv_path)
        return await _playwright_submit(emails, csv_path, config, headless=headless)
    finally:
        if csv_path and csv_path.exists():
            csv_path.unlink()
            logger.debug("Temp CSV deleted: %s", csv_path)


# ---------------------------------------------------------------------------
# Phase 2 — Fetch results
# ---------------------------------------------------------------------------

async def _playwright_fetch(
    task_id: str,
    emails: list[str],
    config: Config,
    headless: bool = True,
) -> dict[str, str]:
    """
    Navigate to Mailin Task Results, find *task_id*, and download the CSV.
    Raises RuntimeError if the task is still processing.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    timeout_ms = config.browser_timeout * 1000

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            await _login(page, config, timeout_ms)

            # Navigate to Verification page → click Task Results tab
            await page.goto(_MAILIN_VERIFY, wait_until="networkidle")
            task_results_link = page.locator("text=Task Results").first
            if await task_results_link.count():
                await task_results_link.click()
                await asyncio.sleep(1)

            await _screenshot(page, "10_task_results_list")

            # Locate the row for our task_id
            row = page.locator(f"tr:has-text('{task_id}')").first
            if not await row.count():
                raise RuntimeError(
                    f"Task ID {task_id!r} not found in Task Results. "
                    "Make sure you are logged in to the correct account."
                )

            # Check status — 4th column (0-indexed: 3)
            status_text = (await row.locator("td").nth(3).inner_text()).strip().lower()
            logger.info("Task %s status: %s", task_id, status_text)

            if "verif" in status_text or "process" in status_text or "pending" in status_text:
                raise RuntimeError(
                    f"Task {task_id} is still processing (status: '{status_text}'). "
                    "Wait for Mailin to finish, then re-run the results notebook."
                )

            # Download the results CSV
            try:
                async with page.expect_download(timeout=timeout_ms) as dl_info:
                    # Download icon is the last <a> in the Action column
                    await row.locator("a").last.click()
                download = await dl_info.value
                raw = Path(await download.path()).read_text(encoding="utf-8")
                results = _parse_results_csv(raw)
                logger.info("Parsed %d rows from downloaded CSV.", len(results))
            except Exception as exc:
                logger.warning("Download failed (%s) — falling back to page scrape.", exc)
                content = await page.content()
                results = _parse_results_table(content, emails)
                logger.info("Parsed %d rows from page content (fallback).", len(results))

            for email in emails:
                results.setdefault(email.lower(), "unknown")

            return results

        finally:
            await _screenshot(page, "99_final_state")
            await context.close()
            await browser.close()


async def mailin_fetch_results(
    task_id: str,
    emails: list[str],
    config: Config,
    headless: bool = True,
) -> dict[str, str]:
    """
    Fetch completed Mailin verification results for *task_id*.

    Args:
        task_id: Task ID returned by ``mailin_submit_batch``.
        emails:  Original list of emails submitted (used as fallback keys).
        config:  Config with Mailin credentials.
        headless: Set False to watch the browser window.

    Returns:
        Dict mapping ``email → status``.

    Raises:
        RuntimeError: If the task is still processing or not found.
    """
    return await _playwright_fetch(task_id, emails, config, headless=headless)


# ---------------------------------------------------------------------------
# EF-13: Catch-all detection and resolution
# ---------------------------------------------------------------------------

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

        statuses = {p.lower(): verification_results.get(p.lower(), "unknown") for p in patterns}
        valid_emails = [e for e, s in statuses.items() if s == "valid"]

        non_unknown = [s for s in statuses.values() if s != "unknown"]
        is_catch_all = bool(non_unknown) and all(s == "valid" for s in non_unknown)

        if is_catch_all:
            best_email: str | None = None
            for pattern_email in patterns:
                if pattern_email.lower() in statuses:
                    best_email = pattern_email.lower()
                    break

            resolved[lead_id] = {
                "email": best_email,
                "is_catch_all": True,
                "confidence": 0.5,
                "status": "catch_all",
            }

        elif valid_emails:
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
            resolved[lead_id] = {
                "email": None,
                "is_catch_all": False,
                "confidence": 0.0,
                "status": "not_found",
            }

    return resolved
