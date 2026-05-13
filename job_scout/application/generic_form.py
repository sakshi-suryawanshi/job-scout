# job_scout/application/generic_form.py
"""
Best-effort prefill for ANY job application form — Workday, SmartRecruiters,
Workable, board-redirects, custom company forms, etc.

Uses only generic helpers (no ATS-specific selectors). When the apply_url
lands on a job-listing page rather than a form, tries to click an Apply
button before filling.
"""

import os
import time
from datetime import datetime
from typing import Dict, Optional
from urllib.parse import urlparse

from job_scout.application.base import (
    ApplyResult, load_applicant_profile, write_resume_tempfile, screenshots_dir,
)
from job_scout.application._form_helpers import (
    answer_question,
    fill_common_questions, fill_other_email_inputs,
    tick_required_consent_checkboxes,
    compute_prefill_coverage, answer_unknowns_with_gemini, build_prefill_notes,
)


def apply_generic(
    apply_url: str,
    resume_text: str,
    cover_letter: str = "",
    headless: bool = True,
    profile: Optional[Dict] = None,
    use_pdf: bool = False,
) -> ApplyResult:
    """Best-effort prefill of a job application form on any apply_url."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ApplyResult(status="failed", tier=2, apply_url=apply_url,
                           error="playwright not installed")
    if profile is None:
        profile = load_applicant_profile()
    if not profile.get("email"):
        return ApplyResult(status="failed", tier=2, apply_url=apply_url,
                           error="APPLY_EMAIL not set")
    if not apply_url:
        return ApplyResult(status="skipped", tier=2, apply_url="",
                           notes="No apply URL")

    resume_path = write_resume_tempfile(resume_text, use_pdf=use_pdf)
    screenshot_path = ""
    host = urlparse(apply_url).netloc.lower()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            )
            page = ctx.new_page()
            page.set_default_timeout(30_000)
            try:
                page.goto(apply_url, wait_until="domcontentloaded", timeout=20_000)
            except Exception as nav_err:
                return ApplyResult(
                    status="failed", tier=2, apply_url=apply_url,
                    error=f"navigation: {nav_err}",
                )
            time.sleep(1.5)

            # Bail if the page is a bot-detection wall (Cloudflare Turnstile etc.)
            if _is_bot_challenge(page):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(screenshots_dir(), f"botblocked_{ts}.png")
                page.screenshot(path=screenshot_path, full_page=False)
                return ApplyResult(
                    status="needs_attention", tier=2, apply_url=apply_url,
                    screenshot_path=screenshot_path,
                    notes="Bot-detection challenge (Cloudflare/Turnstile) — manual apply required",
                )

            # Dismiss cookie / GDPR overlays that block form rendering
            _dismiss_cookie_banner(page)
            time.sleep(0.5)

            # Many board pages need an Apply click before the form shows.
            # The click may open a new tab — capture and switch to it.
            page = _click_apply_and_follow(page, ctx) or page
            time.sleep(1.5)

            # Re-check after navigation for cookie banners on the new page
            _dismiss_cookie_banner(page)

            # ── Standard fields by label ────────────────────────────────────
            _fill_label(page, ["First Name", "Given Name", "Firstname"], profile["first_name"])
            _fill_label(page, ["Last Name", "Family Name", "Surname", "Lastname"], profile["last_name"])
            _fill_label(page, ["Full Name", "Name"], profile["full_name"])
            _fill_label(page, ["Email", "Email Address", "E-mail"], profile["email"])
            _fill_label(page, ["Phone", "Phone Number", "Mobile", "Telephone"], profile["phone"])
            fill_other_email_inputs(page, profile["email"])

            if profile.get("linkedin_url"):
                _fill_label(page, ["LinkedIn", "LinkedIn URL", "LinkedIn Profile"], profile["linkedin_url"])
            if profile.get("github_url"):
                _fill_label(page, ["GitHub", "GitHub URL", "GitHub Profile"], profile["github_url"])
            if profile.get("portfolio_url"):
                _fill_label(page, ["Portfolio", "Website", "Personal Site", "Personal Website"], profile["portfolio_url"])

            # ── Resume upload ───────────────────────────────────────────────
            file_inputs = page.locator("input[type='file']")
            if file_inputs.count() > 0:
                try:
                    file_inputs.first.set_input_files(resume_path)
                    time.sleep(0.7)
                except Exception:
                    pass

            # ── Cover letter / additional info ─────────────────────────────
            if cover_letter:
                for labels in (
                    ["Cover Letter", "Cover letter"],
                    ["Additional Information", "Additional Info"],
                    ["Message", "Note", "Comments"],
                ):
                    if _fill_label(page, labels, cover_letter[:3000]):
                        break

            # ── Generic Y/N questions + Gemini fallback ─────────────────────
            fill_common_questions(page, profile)
            tick_required_consent_checkboxes(page)
            ai_notes = answer_unknowns_with_gemini(page, resume_text=resume_text, profile=profile)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_host = host.replace(":", "_").replace(".", "-") or "generic"
            screenshot_path = os.path.join(screenshots_dir(), f"{safe_host}_{ts}_prefill.png")
            page.screenshot(path=screenshot_path, full_page=True)
            coverage = compute_prefill_coverage(page)

            return ApplyResult(
                status="needs_attention", tier=2, apply_url=apply_url,
                screenshot_path=screenshot_path, cover_letter=cover_letter,
                notes=build_prefill_notes(coverage, ai_notes),
            )
    except Exception as e:
        return ApplyResult(status="failed", tier=2, apply_url=apply_url,
                           screenshot_path=screenshot_path, error=str(e))
    finally:
        try:
            os.unlink(resume_path)
        except Exception:
            pass


_APPLY_BUTTON_SELECTORS = (
    "a:has-text('Apply for this job')",
    "button:has-text('Apply for this job')",
    "a:has-text('Apply Now')",
    "button:has-text('Apply Now')",
    "a[role='button']:has-text('Apply')",
    "button:has-text('Apply')",
    "a:has-text('Apply')",
)


def _click_apply_and_follow(page, ctx):
    """Click an Apply button and follow any new tab it opens.

    Returns the new page if a popup was captured, else None (caller keeps
    the original page).
    """
    btn = None
    for sel in _APPLY_BUTTON_SELECTORS:
        try:
            cand = page.locator(sel)
            if cand.count() > 0 and cand.first.is_visible():
                btn = cand.first
                break
        except Exception:
            continue
    if btn is None:
        return None

    # Try to capture a new tab if the click opens one; fall back to same-page nav
    try:
        with ctx.expect_page(timeout=4_000) as new_page_info:
            btn.click()
        new_page = new_page_info.value
        try:
            new_page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except Exception:
            pass
        return new_page
    except Exception:
        # No popup — the click navigated the current page (or did nothing)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=8_000)
        except Exception:
            pass
        return None


def _dismiss_cookie_banner(page) -> None:
    """Click common cookie / GDPR accept buttons so the form can render."""
    for sel in (
        "button:has-text('Accept all')",
        "button:has-text('Allow all')",
        "button:has-text('Accept All')",
        "button:has-text('I agree')",
        "button:has-text('Required only')",
        "button:has-text('Reject all')",
        "button:has-text('Dismiss')",
        "button:has-text('Got it')",
        "button:has-text('OK')",
        "button[aria-label*='accept' i]",
        "button[id*='accept-cookies' i]",
    ):
        try:
            btn = page.locator(sel)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=1_500)
                return
        except Exception:
            continue


def _is_bot_challenge(page) -> bool:
    """Return True if the page is a bot-detection wall (Cloudflare etc.)."""
    try:
        title = (page.title() or "").lower()
        if any(t in title for t in ("just a moment", "verifying", "attention required")):
            return True
        # Look for Cloudflare / Turnstile telltale text via JS — more reliable
        # than Playwright's text= selector for case-insensitive substring match.
        return bool(page.evaluate("""() => {
            const t = (document.body && document.body.innerText) || '';
            const s = t.toLowerCase();
            return s.includes('performing security verification')
                || s.includes('verify you are human')
                || s.includes('checking your browser')
                || s.includes('cloudflare ray id');
        }"""))
    except Exception:
        return False


def _fill_label(page, labels, value: str) -> bool:
    """Fill the first form control whose label matches any of `labels`.
    Returns True if anything was filled."""
    if not value:
        return False
    for label in labels:
        try:
            el = page.get_by_label(label, exact=False).first
            if el.count() == 0:
                continue
            try:
                tag = (el.evaluate("e => e.tagName.toLowerCase()") or "")
            except Exception:
                tag = ""
            if tag in ("input", "textarea"):
                try:
                    el.fill(value)
                    return True
                except Exception:
                    continue
        except Exception:
            continue
    return False
