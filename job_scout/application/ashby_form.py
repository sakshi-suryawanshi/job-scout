# job_scout/application/ashby_form.py
"""
Playwright auto-fill for Ashby job application forms.
Apply URL pattern: https://jobs.ashbyhq.com/{slug}/{job_id}
Ashby uses a React SPA — fields load dynamically.
"""

import os
import time
from datetime import datetime
from typing import Dict, Optional

from job_scout.application.base import ApplyResult, load_applicant_profile, write_resume_tempfile, screenshots_dir


def apply_ashby(
    apply_url: str,
    resume_text: str,
    cover_letter: str = "",
    headless: bool = True,
    profile: Optional[Dict] = None,
) -> ApplyResult:
    """Auto-fill and submit an Ashby application form."""
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
        return ApplyResult(status="failed", tier=1, apply_url=apply_url, error="APPLY_EMAIL not set")

    resume_path = write_resume_tempfile(resume_text, ".txt")
    screenshot_path = ""

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            )
            page = context.new_page()
            page.set_default_timeout(30_000)

            page.goto(apply_url, wait_until="networkidle")
            time.sleep(2)  # Ashby SPA needs extra time to hydrate

            # ── Click "Apply" if on job description page ────────────────────
            try:
                apply_btn = page.locator("button:has-text('Apply'), a:has-text('Apply')")
                if apply_btn.count() > 0:
                    apply_btn.first.click()
                    page.wait_for_load_state("networkidle")
                    time.sleep(1.5)
            except Exception:
                pass

            # ── Fill fields by label (Ashby uses consistent aria-labels) ───
            _fill_labeled(page, "First Name", profile["first_name"])
            _fill_labeled(page, "Last Name",  profile["last_name"])
            _fill_labeled(page, "Email",      profile["email"])
            _fill_labeled(page, "Phone",      profile["phone"])

            if profile.get("linkedin_url"):
                _fill_labeled(page, "LinkedIn", profile["linkedin_url"])

            if profile.get("github_url"):
                _fill_labeled(page, "GitHub", profile["github_url"])

            if profile.get("portfolio_url"):
                _fill_labeled(page, "Website", profile["portfolio_url"])
                _fill_labeled(page, "Portfolio", profile["portfolio_url"])

            # ── Resume upload ───────────────────────────────────────────────
            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(resume_path)
                time.sleep(1)

            # ── Cover letter ────────────────────────────────────────────────
            if cover_letter:
                _fill_labeled(page, "Cover Letter", cover_letter[:3000])
                _fill_labeled(page, "Additional Information", cover_letter[:3000])

            # ── Screenshot before submit ────────────────────────────────────
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = os.path.join(screenshots_dir(), f"ashby_{ts}_before.png")
            page.screenshot(path=screenshot_path, full_page=False)

            # ── Submit ──────────────────────────────────────────────────────
            # Ashby's submit button has data-testid or text
            submit = page.locator(
                "button[data-testid='submit-application-button'], "
                "button:has-text('Submit Application'), "
                "button[type='submit']"
            )
            if submit.count() == 0:
                return ApplyResult(
                    status="needs_attention", tier=1, apply_url=apply_url,
                    screenshot_path=screenshot_path,
                    notes="Submit button not found — dynamic form may need manual review",
                )

            submit.first.click()

            # ── Confirm ─────────────────────────────────────────────────────
            try:
                page.wait_for_selector(
                    "text=application has been submitted, "
                    "text=Thank you for applying, "
                    "text=successfully submitted",
                    timeout=12_000,
                )
                ts2 = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(screenshots_dir(), f"ashby_{ts2}_success.png")
                page.screenshot(path=screenshot_path, full_page=False)
                return ApplyResult(
                    status="applied", tier=1, apply_url=apply_url,
                    screenshot_path=screenshot_path, cover_letter=cover_letter,
                )
            except PWTimeout:
                ts2 = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(screenshots_dir(), f"ashby_{ts2}_unclear.png")
                page.screenshot(path=screenshot_path, full_page=False)
                return ApplyResult(
                    status="applied", tier=1, apply_url=apply_url,
                    screenshot_path=screenshot_path, cover_letter=cover_letter,
                    notes="Submitted — success confirmation not detected",
                )

            browser.close()

    except Exception as e:
        return ApplyResult(status="failed", tier=1, apply_url=apply_url,
                           screenshot_path=screenshot_path, error=str(e))
    finally:
        try:
            os.unlink(resume_path)
        except Exception:
            pass


def _fill_labeled(page, label: str, value: str):
    if not value:
        return
    try:
        el = page.get_by_label(label, exact=False)
        if el.count() > 0:
            tag = el.first.evaluate("el => el.tagName.toLowerCase()")
            if tag == "textarea":
                el.first.fill(value)
            else:
                el.first.fill(value)
    except Exception:
        pass
