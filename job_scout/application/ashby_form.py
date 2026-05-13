# job_scout/application/ashby_form.py
"""
Playwright prefill for Ashby job application forms.
Apply URL pattern: https://jobs.ashbyhq.com/{slug}/{job_id}
Ashby is a React SPA — fields hydrate after navigation.
"""

import os
import time
from datetime import datetime
from typing import Dict, Optional

from job_scout.application.base import (
    ApplyResult, load_applicant_profile, write_resume_tempfile, screenshots_dir,
)
from job_scout.application._form_helpers import (
    fill_common_questions, fill_other_email_inputs,
    tick_required_consent_checkboxes,
    compute_prefill_coverage, answer_unknowns_with_gemini, build_prefill_notes,
)


def apply_ashby(
    apply_url: str,
    resume_text: str,
    cover_letter: str = "",
    headless: bool = True,
    profile: Optional[Dict] = None,
    use_pdf: bool = False,
) -> ApplyResult:
    """Prefill an Ashby application form. Never submits."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ApplyResult(status="failed", tier=1, apply_url=apply_url,
                           error="playwright not installed")
    if profile is None:
        profile = load_applicant_profile()
    if not profile.get("email"):
        return ApplyResult(status="failed", tier=1, apply_url=apply_url,
                           error="APPLY_EMAIL not set")

    resume_path = write_resume_tempfile(resume_text, use_pdf=use_pdf)
    screenshot_path = ""

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            )
            page = ctx.new_page()
            page.set_default_timeout(30_000)
            page.goto(apply_url, wait_until="networkidle")
            time.sleep(2)  # Ashby needs extra hydration time

            # Click "Apply" if on job description page
            try:
                btn = page.locator("button:has-text('Apply'), a:has-text('Apply')")
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_load_state("networkidle")
                    time.sleep(1.5)
            except Exception:
                pass

            # ── Standard fields by aria-label (Ashby pattern) ───────────────
            # Some Ashby boards use First/Last, others a single Name field.
            # Try both; whichever matches wins.
            if not _fill_labeled(page, "First Name", profile["first_name"]):
                _fill_labeled(page, "Name", profile["full_name"])
            _fill_labeled(page, "Last Name",  profile["last_name"])
            _fill_labeled(page, "Email",      profile["email"])
            _fill_labeled(page, "Phone",      profile["phone"])
            fill_other_email_inputs(page, profile["email"])

            if profile.get("linkedin_url"):
                _fill_labeled(page, "LinkedIn", profile["linkedin_url"])
            if profile.get("github_url"):
                _fill_labeled(page, "GitHub", profile["github_url"])
            if profile.get("portfolio_url"):
                _fill_labeled(page, "Website",   profile["portfolio_url"])
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

            # ── Common Y/N questions + Gemini fallback ──────────────────────
            fill_common_questions(page, profile)
            tick_required_consent_checkboxes(page)
            ai_notes = answer_unknowns_with_gemini(page, resume_text=resume_text, profile=profile)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = os.path.join(screenshots_dir(), f"ashby_{ts}_prefill.png")
            page.screenshot(path=screenshot_path, full_page=True)
            coverage = compute_prefill_coverage(page)

            return ApplyResult(
                status="needs_attention", tier=1, apply_url=apply_url,
                screenshot_path=screenshot_path, cover_letter=cover_letter,
                notes=build_prefill_notes(coverage, ai_notes),
            )
    except Exception as e:
        return ApplyResult(status="failed", tier=1, apply_url=apply_url,
                           screenshot_path=screenshot_path, error=str(e))
    finally:
        try:
            os.unlink(resume_path)
        except Exception:
            pass


def _fill_labeled(page, label: str, value: str) -> bool:
    """Fill the first label-matched input. Returns True on success."""
    if not value:
        return False
    try:
        el = page.get_by_label(label, exact=False)
        if el.count() > 0:
            el.first.fill(value)
            return True
    except Exception:
        pass
    return False
