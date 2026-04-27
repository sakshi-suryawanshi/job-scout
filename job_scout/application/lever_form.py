# job_scout/application/lever_form.py
"""
Playwright auto-fill for Lever job application forms.
Apply URL pattern: https://jobs.lever.co/{slug}/{job_id}/apply
"""

import os
import time
from datetime import datetime
from typing import Dict, Optional

from job_scout.application.base import ApplyResult, load_applicant_profile, write_resume_tempfile, screenshots_dir


def apply_lever(
    apply_url: str,
    resume_text: str,
    cover_letter: str = "",
    headless: bool = True,
    profile: Optional[Dict] = None,
) -> ApplyResult:
    """Auto-fill and submit a Lever application form."""
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

    # Lever apply URLs end in /apply — add it if missing
    url = apply_url if apply_url.endswith("/apply") else apply_url.rstrip("/") + "/apply"

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

            page.goto(url, wait_until="domcontentloaded")
            time.sleep(1)

            # ── Fill standard fields ────────────────────────────────────────
            # Lever uses input#name (full name), input#email, input#phone
            _fill(page, "#name",  profile["full_name"])
            _fill(page, "#email", profile["email"])
            _fill(page, "#phone", profile["phone"])

            if profile.get("linkedin_url"):
                _fill_by_label(page, ["LinkedIn", "LinkedIn URL"], profile["linkedin_url"])
                _fill(page, "#urls-linkedin, input[name='urls[LinkedIn]']", profile["linkedin_url"])

            if profile.get("github_url"):
                _fill_by_label(page, ["GitHub", "GitHub URL"], profile["github_url"])
                _fill(page, "#urls-github, input[name='urls[GitHub]']", profile["github_url"])

            if profile.get("portfolio_url"):
                _fill_by_label(page, ["Portfolio", "Website", "Personal Site"], profile["portfolio_url"])

            # ── Resume upload ───────────────────────────────────────────────
            file_input = page.locator("input[type='file']")
            if file_input.count() > 0:
                file_input.first.set_input_files(resume_path)
                time.sleep(0.5)

            # ── Cover letter / comments ─────────────────────────────────────
            if cover_letter:
                for sel in ["textarea#comments", "textarea[name='comments']", "textarea[id*='comment']"]:
                    try:
                        el = page.locator(sel)
                        if el.count() > 0:
                            el.first.fill(cover_letter[:3000])
                            break
                    except Exception:
                        continue

            # ── Screenshot before submit ────────────────────────────────────
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = os.path.join(screenshots_dir(), f"lever_{ts}_before.png")
            page.screenshot(path=screenshot_path, full_page=False)

            # ── Submit ──────────────────────────────────────────────────────
            submit = page.locator("button[type='submit']:has-text('Submit'), button:has-text('Submit application')")
            if submit.count() == 0:
                submit = page.locator("button[type='submit']")
            if submit.count() == 0:
                return ApplyResult(
                    status="needs_attention", tier=1, apply_url=apply_url,
                    screenshot_path=screenshot_path,
                    notes="Submit button not found",
                )

            submit.first.click()

            # ── Confirm ─────────────────────────────────────────────────────
            try:
                page.wait_for_selector("text=Thank you, text=submitted, text=received", timeout=10_000)
                ts2 = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(screenshots_dir(), f"lever_{ts2}_success.png")
                page.screenshot(path=screenshot_path, full_page=False)
                return ApplyResult(
                    status="applied", tier=1, apply_url=apply_url,
                    screenshot_path=screenshot_path, cover_letter=cover_letter,
                )
            except PWTimeout:
                ts2 = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(screenshots_dir(), f"lever_{ts2}_unclear.png")
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


def _fill_by_label(page, labels, value: str):
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
