# job_scout/application/lever_form.py
"""
Playwright prefill for Lever job application forms.
Apply URL pattern: https://jobs.lever.co/{slug}/{job_id}/apply
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


def apply_lever(
    apply_url: str,
    resume_text: str,
    cover_letter: str = "",
    headless: bool = True,
    profile: Optional[Dict] = None,
    use_pdf: bool = False,
) -> ApplyResult:
    """Prefill a Lever application form. Never submits."""
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

    url = apply_url if apply_url.endswith("/apply") else apply_url.rstrip("/") + "/apply"
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
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(1)

            # ── Standard fields ─────────────────────────────────────────────
            # Lever uses <label>Full name</label> not always #name.
            # Try label first (works on modern Lever boards), then id selectors.
            if not _fill_by_label(page, ["Full name", "Full Name", "Name"], profile["full_name"]):
                _fill(page, "#name, input[name='name']", profile["full_name"])
            if not _fill_by_label(page, ["Email", "Email address"], profile["email"]):
                _fill(page, "#email, input[name='email']", profile["email"])
            if not _fill_by_label(page, ["Phone", "Phone number"], profile["phone"]):
                _fill(page, "#phone, input[name='phone']", profile["phone"])
            _fill_by_label(page, ["Current location", "Location"], profile.get("location", ""))
            fill_other_email_inputs(page, profile["email"])

            if profile.get("linkedin_url"):
                _fill(page, "input[name='urls[LinkedIn]'], #urls-linkedin", profile["linkedin_url"])
                _fill_by_label(page, ["LinkedIn", "LinkedIn URL"], profile["linkedin_url"])
            if profile.get("github_url"):
                _fill(page, "input[name='urls[GitHub]'], #urls-github", profile["github_url"])
                _fill_by_label(page, ["GitHub", "GitHub URL"], profile["github_url"])
            if profile.get("portfolio_url"):
                _fill_by_label(page, ["Portfolio", "Website", "Personal Site"], profile["portfolio_url"])

            # ── Resume upload ───────────────────────────────────────────────
            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(resume_path)
                time.sleep(0.5)

            # ── Cover letter / comments ─────────────────────────────────────
            if cover_letter:
                for sel in ("textarea#comments", "textarea[name='comments']", "textarea[id*='comment']"):
                    try:
                        el = page.locator(sel)
                        if el.count() > 0:
                            el.first.fill(cover_letter[:3000])
                            break
                    except Exception:
                        continue

            # ── Common Y/N questions + Gemini fallback ──────────────────────
            fill_common_questions(page, profile)
            tick_required_consent_checkboxes(page)
            ai_notes = answer_unknowns_with_gemini(page, resume_text=resume_text, profile=profile)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = os.path.join(screenshots_dir(), f"lever_{ts}_prefill.png")
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


def _fill(page, selector: str, value: str):
    if not value:
        return
    for sel in selector.split(","):
        try:
            el = page.locator(sel.strip())
            if el.count() > 0:
                el.first.fill(value)
                return
        except Exception:
            continue


def _fill_by_label(page, labels, value: str) -> bool:
    """Fill the first matching label-associated input. Returns True if filled."""
    if not value:
        return False
    for label in labels:
        try:
            el = page.get_by_label(label, exact=False)
            if el.count() > 0:
                el.first.fill(value)
                return True
        except Exception:
            continue
    return False
