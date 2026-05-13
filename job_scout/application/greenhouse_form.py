# job_scout/application/greenhouse_form.py
"""
Playwright prefill for Greenhouse job application forms.
Apply URL pattern: https://boards.greenhouse.io/{slug}/jobs/{job_id}
                   https://job-boards.greenhouse.io/{slug}/jobs/{job_id}

Prefill-only — never auto-submits. The user reviews and clicks Submit.
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


def apply_greenhouse(
    apply_url: str,
    resume_text: str,
    cover_letter: str = "",
    headless: bool = True,
    profile: Optional[Dict] = None,
    use_pdf: bool = False,
) -> ApplyResult:
    """Prefill a Greenhouse application form. Never submits."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ApplyResult(
            status="failed", tier=1, apply_url=apply_url,
            error="playwright not installed. Run: pip install playwright && playwright install chromium",
        )

    if profile is None:
        profile = load_applicant_profile()

    if not profile.get("email"):
        return ApplyResult(status="failed", tier=1, apply_url=apply_url,
                           error="APPLY_EMAIL not set in environment")

    resume_path = write_resume_tempfile(resume_text, use_pdf=use_pdf)
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

            # Some Greenhouse URLs land on a description page; click Apply if so.
            try:
                btn = page.locator(
                    "a:has-text('Apply'), button:has-text('Apply'), "
                    "a:has-text('Apply for this job')"
                )
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(1)
            except Exception:
                pass

            # ── Standard fields ─────────────────────────────────────────────
            _fill_by_name_or_label(page, "first_name", profile["first_name"])
            _fill_by_name_or_label(page, "last_name",  profile["last_name"])
            _fill_by_name_or_label(page, "email",      profile["email"])
            _fill_by_name_or_label(page, "phone",      profile["phone"])
            fill_other_email_inputs(page, profile["email"])

            if profile.get("linkedin_url"):
                _fill_by_label_text(page, ["LinkedIn", "LinkedIn URL", "LinkedIn Profile"], profile["linkedin_url"])
            if profile.get("github_url"):
                _fill_by_label_text(page, ["GitHub", "GitHub URL", "GitHub Profile"], profile["github_url"])
            if profile.get("portfolio_url"):
                _fill_by_label_text(page, ["Portfolio", "Website", "Personal Website"], profile["portfolio_url"])

            # ── Resume upload ───────────────────────────────────────────────
            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(resume_path)
                time.sleep(0.5)

            # ── Cover letter ────────────────────────────────────────────────
            if cover_letter:
                _fill_cover_letter(page, cover_letter)

            # ── Common Y/N questions + Gemini fallback for unknowns ─────────
            fill_common_questions(page, profile)
            tick_required_consent_checkboxes(page)
            ai_notes = answer_unknowns_with_gemini(page, resume_text=resume_text, profile=profile)

            # ── Screenshot + coverage report ────────────────────────────────
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = os.path.join(screenshots_dir(), f"greenhouse_{ts}_prefill.png")
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


# ── Greenhouse-specific micro-helpers ───────────────────────────────────────

def _fill_by_name_or_label(page, name: str, value: str):
    if not value:
        return
    try:
        el = page.locator(f"input[name='{name}'], input[id='{name}']")
        if el.count() > 0:
            el.first.fill(value)
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
    for selector in (
        "textarea[name*='cover'], textarea[id*='cover'], textarea[placeholder*='cover']",
        "textarea[name*='letter'], textarea[id*='letter']",
        "div[contenteditable='true']",
    ):
        try:
            el = page.locator(selector)
            if el.count() > 0:
                el.first.fill(cover_letter[:3000])
                return
        except Exception:
            continue
    _fill_by_label_text(page, ["Cover Letter", "Cover letter", "Message", "Letter"], cover_letter[:3000])
