# job_scout/application/greenhouse_form.py
"""
Playwright auto-fill for Greenhouse job application forms.
Greenhouse forms are the most predictable of the major ATS platforms.

Public apply URL pattern: https://boards.greenhouse.io/{slug}/jobs/{job_id}
or the /apply redirect: https://boards.greenhouse.io/{slug}/jobs/{job_id}#app
"""

import os
import time
from datetime import datetime
from typing import Dict, Optional

from job_scout.application.base import ApplyResult, load_applicant_profile, write_resume_tempfile, screenshots_dir


def apply_greenhouse(
    apply_url: str,
    resume_text: str,
    cover_letter: str = "",
    headless: bool = True,
    profile: Optional[Dict] = None,
) -> ApplyResult:
    """
    Auto-fill and submit a Greenhouse application form.

    Args:
        apply_url:    Direct URL to the job application page.
        resume_text:  Plain-text tailored resume.
        cover_letter: Generated cover letter text (optional).
        headless:     True for scheduled runs, False for debug.
        profile:      Applicant details dict. None = load from env.

    Returns:
        ApplyResult with status and screenshot path.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        return ApplyResult(
            status="failed", tier=1, apply_url=apply_url,
            error="playwright not installed. Run: pip install playwright && playwright install chromium",
        )

    if profile is None:
        profile = load_applicant_profile()

    if not profile.get("email"):
        return ApplyResult(
            status="failed", tier=1, apply_url=apply_url,
            error="APPLY_EMAIL not set in environment",
        )

    resume_path = write_resume_tempfile(resume_text, ".txt")
    screenshot_path = ""

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            )
            page = context.new_page()
            page.set_default_timeout(30_000)

            page.goto(apply_url, wait_until="domcontentloaded")
            time.sleep(1)

            # ── Navigate to the apply form ──────────────────────────────────
            # Some Greenhouse URLs land on the job description, not the form.
            # Look for an "Apply" button and click it.
            try:
                apply_btn = page.locator("a:has-text('Apply'), button:has-text('Apply'), a:has-text('Apply for this job')")
                if apply_btn.count() > 0:
                    apply_btn.first.click()
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(1)
            except Exception:
                pass

            # ── Fill standard fields ────────────────────────────────────────
            _fill_by_name_or_label(page, "first_name", profile["first_name"])
            _fill_by_name_or_label(page, "last_name", profile["last_name"])
            _fill_by_name_or_label(page, "email", profile["email"])
            _fill_by_name_or_label(page, "phone", profile["phone"])

            if profile.get("linkedin_url"):
                _fill_by_label_text(page, ["LinkedIn", "LinkedIn URL", "LinkedIn Profile"], profile["linkedin_url"])

            if profile.get("github_url"):
                _fill_by_label_text(page, ["GitHub", "GitHub URL", "GitHub Profile"], profile["github_url"])

            if profile.get("portfolio_url"):
                _fill_by_label_text(page, ["Portfolio", "Website", "Personal Website"], profile["portfolio_url"])

            # ── Resume upload ───────────────────────────────────────────────
            resume_inputs = page.locator("input[type='file']")
            if resume_inputs.count() > 0:
                resume_inputs.first.set_input_files(resume_path)
                time.sleep(0.5)

            # ── Cover letter ────────────────────────────────────────────────
            if cover_letter:
                _fill_cover_letter(page, cover_letter)

            # ── Handle common custom questions ──────────────────────────────
            _fill_common_questions(page, profile)

            # ── Screenshot before submit ────────────────────────────────────
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = os.path.join(screenshots_dir(), f"greenhouse_{ts}_before.png")
            page.screenshot(path=screenshot_path, full_page=False)

            # ── Submit ──────────────────────────────────────────────────────
            submit = page.locator("input[type='submit'], button[type='submit'], button:has-text('Submit Application')")
            if submit.count() == 0:
                return ApplyResult(
                    status="needs_attention", tier=1, apply_url=apply_url,
                    screenshot_path=screenshot_path,
                    notes="Submit button not found — custom form structure",
                )

            submit.first.click()

            # ── Confirm success ─────────────────────────────────────────────
            try:
                page.wait_for_selector(
                    "text=application has been submitted, text=Thank you, text=successfully submitted",
                    timeout=10_000,
                )
                ts2 = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(screenshots_dir(), f"greenhouse_{ts2}_success.png")
                page.screenshot(path=screenshot_path, full_page=False)
                return ApplyResult(
                    status="applied", tier=1, apply_url=apply_url,
                    screenshot_path=screenshot_path, cover_letter=cover_letter,
                )
            except PWTimeout:
                # Page changed but no explicit success text — likely still submitted
                ts2 = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(screenshots_dir(), f"greenhouse_{ts2}_unclear.png")
                page.screenshot(path=screenshot_path, full_page=False)
                return ApplyResult(
                    status="applied", tier=1, apply_url=apply_url,
                    screenshot_path=screenshot_path, cover_letter=cover_letter,
                    notes="Submitted — success confirmation not detected (may still have applied)",
                )

            browser.close()

    except Exception as e:
        return ApplyResult(
            status="failed", tier=1, apply_url=apply_url,
            screenshot_path=screenshot_path, error=str(e),
        )
    finally:
        try:
            os.unlink(resume_path)
        except Exception:
            pass


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fill_by_name_or_label(page, name: str, value: str):
    if not value:
        return
    try:
        el = page.locator(f"input[name='{name}'], input[id='{name}']")
        if el.count() > 0:
            el.first.fill(value)
            return
    except Exception:
        pass


def _fill_by_label_text(page, labels, value: str):
    if not value:
        return
    for label in labels:
        try:
            el = page.get_by_label(label, exact=False)
            if el.count() > 0:
                el.first.fill(value)
                return
        except Exception:
            continue


def _fill_cover_letter(page, cover_letter: str):
    # Try textarea with cover-letter-related name/id/placeholder
    for selector in [
        "textarea[name*='cover'], textarea[id*='cover'], textarea[placeholder*='cover']",
        "textarea[name*='letter'], textarea[id*='letter']",
        "div[contenteditable='true']",
    ]:
        try:
            el = page.locator(selector)
            if el.count() > 0:
                el.first.fill(cover_letter[:3000])
                return
        except Exception:
            continue

    # Fallback: label matching
    _fill_by_label_text(page, ["Cover Letter", "Cover letter", "Message", "Letter"], cover_letter[:3000])


def _fill_common_questions(page, profile: Dict):
    """Answer common yes/no / text questions on Greenhouse custom forms."""
    # "Are you authorized to work in X?" — answer based on profile
    try:
        auth_select = page.locator("select[id*='authorized'], select[name*='authorized']")
        if auth_select.count() > 0:
            auth_select.first.select_option("Yes")
    except Exception:
        pass

    # "Will you now or in the future require sponsorship?" — No
    try:
        sponsor_select = page.locator("select[id*='sponsor'], select[name*='sponsor']")
        if sponsor_select.count() > 0:
            sponsor_select.first.select_option("No")
    except Exception:
        pass
