# job_scout/application/orchestrator.py
"""
Pick the right applier tier for each job and execute it.

Tier 1 (auto):  Greenhouse, Lever, Ashby — Playwright form-fill
Tier 2 (semi):  Workday, Workable, SmartRecruiters, custom — pre-fill + manual submit
Tier 3 (email): HN comment / IndieHackers / Twitter — cold email outreach
"""

import os
from typing import Dict, Optional

from job_scout.application.base import ApplyResult, load_applicant_profile


# ATS types that get full automation (Tier 1)
_TIER1_ATS = {"greenhouse", "lever", "ashby"}

# Source boards that get email outreach (Tier 3)
_TIER3_SOURCES = {"hackernews", "hackernews_jobs", "reddit_forhire", "reddit_remotejs"}

# apply_url must contain the ATS's own domain — otherwise the URL is a
# board-listing page (RemoteOK, Wellfound, etc.) and the Tier-1 form-filler
# will never find the right inputs. Route those to Tier-2 instead.
_TIER1_URL_HOSTS = {
    "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io", "greenhouse.io"),
    "lever":      ("jobs.lever.co", "lever.co"),
    "ashby":      ("jobs.ashbyhq.com", "ashbyhq.com"),
}


_PREFILLABLE_HOSTS = {
    "boards.greenhouse.io", "job-boards.greenhouse.io",
    "boards.eu.greenhouse.io", "job-boards.eu.greenhouse.io",
    "jobs.ashbyhq.com",
    "jobs.lever.co",
}


def _is_prefillable_url(apply_url: str) -> bool:
    """Return True if this URL hosts an actual application form.

    HN threads, LinkedIn listings, Reddit posts, board aggregator pages,
    and Cloudflare-walled sites don't have fillable forms.
    """
    from urllib.parse import urlparse, parse_qs
    if not apply_url:
        return False
    parsed = urlparse(apply_url)
    host = parsed.netloc.lower()
    if host in _PREFILLABLE_HOSTS:
        return True
    if parse_qs(parsed.query).get("gh_jid"):
        return True
    return False


def _is_tier1_apply_url(ats_type: str, apply_url: str) -> bool:
    hosts = _TIER1_URL_HOSTS.get(ats_type, ())
    return any(h in (apply_url or "").lower() for h in hosts)


def _rewrite_greenhouse_jid(apply_url: str) -> str:
    """If `apply_url` carries a `gh_jid=NNN` query param, rewrite to the
    canonical Greenhouse boards URL. Many company careers pages (Samsara,
    Nebius, SoFi…) embed Greenhouse and use this param — the canonical URL
    serves the same form without the wrapper SPA.

    We can't infer the company slug from the param alone, but Greenhouse's
    boards URL `https://boards.greenhouse.io/embed/job_app?for={slug}&token={jid}`
    isn't universal either. The reliable canonical form for an isolated job
    is `https://boards.greenhouse.io/embed/job_app?token={jid}` which serves
    the same fields. Returns "" if no gh_jid param is present.
    """
    from urllib.parse import urlparse, parse_qs
    try:
        u = urlparse(apply_url or "")
        params = parse_qs(u.query)
        jid = (params.get("gh_jid") or [None])[0]
        if not jid:
            return ""
        return f"https://boards.greenhouse.io/embed/job_app?token={jid}"
    except Exception:
        return ""


def apply_to_job(
    job: Dict,
    resume_text: str,
    headless: bool = True,
    profile: Optional[Dict] = None,
    db=None,
) -> ApplyResult:
    """
    Main entry point. Selects the applier tier based on the job's ATS type
    and source board, then executes the application.

    Args:
        job:         Job dict from DB (must include apply_url, companies{ats_type}).
        resume_text: Tailored resume plain text.
        headless:    Playwright headless mode (True for scheduled, False for debug).
        profile:     Applicant profile dict. None = load from env.
        db:          DB instance for recording the application.

    Returns:
        ApplyResult with status and details.
    """
    if profile is None:
        profile = load_applicant_profile()

    apply_url = job.get("apply_url", "")
    if not apply_url:
        return ApplyResult(status="skipped", tier=0, apply_url="", notes="No apply URL")

    # Skip Playwright entirely for URLs that don't host application forms.
    if not _is_prefillable_url(apply_url):
        return ApplyResult(
            status="needs_attention", tier=0, apply_url=apply_url,
            notes="Not a direct application form — apply manually via the link.",
        )

    company_info = job.get("companies", {}) or {}
    ats_type = (company_info.get("ats_type") or job.get("ats_type") or "unknown").lower()
    source_board = (job.get("source_board") or "").lower()

    score = int(job.get("match_score") or 0)

    # ── Resume strategy based on score + remaining Gemini quota ──────────
    #
    # Priority 1 (score ≥ 80): always tailor — these are high-confidence jobs
    #   → Gemini rewrites resume from .tex source for this specific role
    #   → attach tailored text to ATS form
    #
    # Priority 2 (score 70–79): tailor ONLY if Gemini quota is still available
    #   after processing all ≥80 jobs.  If quota is low, fall back to PDF.
    #   → attach tailored text when quota allows
    #   → attach original PDF when quota is running out
    if score >= 80:
        tailored_resume = _tailor_resume_for_job(job, resume_text)
        use_pdf = False

    elif score >= 70:
        if _has_gemini_quota(min_remaining=100):
            # Quota available → upgrade: tailor and submit just like ≥80 jobs
            tailored_resume = _tailor_resume_for_job(job, resume_text)
            use_pdf = False
        else:
            # Quota low → fall back to original PDF, no tailoring cost
            tailored_resume = resume_text
            use_pdf = True

    else:
        tailored_resume = resume_text
        use_pdf = True

    # ── Generate cover letter (shared across tiers, always uses .tex text) ─
    cover_letter = _generate_cover_letter(job, resume_text)

    # ── Tier 3: Email outreach ─────────────────────────────────────────────
    if source_board in _TIER3_SOURCES or "hn_" in apply_url or "news.ycombinator.com" in apply_url:
        from job_scout.application.email_outreach import send_outreach_email
        result = send_outreach_email(job, resume_text, profile)
        _record_application(db, job, result, resume_text)
        return result

    # Many company careers pages embed Greenhouse via a `?gh_jid=XXX` param.
    # Rewriting those to the canonical boards.greenhouse.io URL lets the
    # Tier-1 filler handle them instead of relying on the SPA to render.
    rewritten = _rewrite_greenhouse_jid(apply_url)
    if rewritten and rewritten != apply_url:
        apply_url = rewritten
        if ats_type not in _TIER1_ATS:
            ats_type = "greenhouse"

    # ── Tier 1: ATS-specific Playwright prefill ────────────────────────────
    # Use the ATS-specific filler only when apply_url points at the ATS's own
    # host (otherwise the apply_url is a board listing and ATS selectors miss).
    if ats_type in _TIER1_ATS and _is_tier1_apply_url(ats_type, apply_url):
        if ats_type == "greenhouse":
            from job_scout.application.greenhouse_form import apply_greenhouse
            result = apply_greenhouse(apply_url, tailored_resume, cover_letter, headless, profile, use_pdf=use_pdf)
        elif ats_type == "lever":
            from job_scout.application.lever_form import apply_lever
            result = apply_lever(apply_url, tailored_resume, cover_letter, headless, profile, use_pdf=use_pdf)
        else:  # ashby
            from job_scout.application.ashby_form import apply_ashby
            result = apply_ashby(apply_url, tailored_resume, cover_letter, headless, profile, use_pdf=use_pdf)
        _record_application(db, job, result, tailored_resume)
        return result

    # ── Generic Playwright prefill (any other apply_url) ───────────────────
    # Workday / SmartRecruiters / board redirects / company custom forms all
    # land here. Best-effort: fill standard fields, common questions, ask
    # Gemini for unknowns, screenshot, return needs_attention.
    from job_scout.application.generic_form import apply_generic
    result = apply_generic(apply_url, tailored_resume, cover_letter, headless, profile, use_pdf=use_pdf)
    _record_application(db, job, result, tailored_resume)
    return result


def _tailor_resume_for_job(job: Dict, resume_text: str) -> str:
    """Rewrite resume_text for this specific job using Gemini.
    Called only for score ≥ 80 — saves Gemini quota on lower-confidence jobs.
    Falls back to the original text IMMEDIATELY if Gemini is unavailable or
    rate-limited — does NOT retry, because auto-apply cannot block 3 min/job.
    """
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key or not resume_text:
        return resume_text
    try:
        import httpx
        from job_scout.ai.gemini import GeminiClient, GEMINI_API_URL, tailor_resume
        from job_scout.ai.prompts import TAILOR_PROMPT

        # One-shot attempt — no retry. If rate limited, fall back instantly.
        company_info = job.get("companies", {}) or {}
        company_name = company_info.get("name", "") or job.get("company_name", "Unknown")
        desc = (job.get("description") or "")[:2000]
        description_section = f"- Description excerpt:\n{desc}" if desc.strip() else ""
        prompt = TAILOR_PROMPT.format(
            job_title=job.get("title", "Unknown"),
            company_name=company_name,
            location=job.get("location", "Remote"),
            is_remote=job.get("is_remote", True),
            source_board=job.get("source_board", ""),
            description_section=description_section,
            resume_text=resume_text[:4000],
        )
        client = httpx.Client(timeout=30.0)
        resp = client.post(f"{GEMINI_API_URL}?key={gemini_key}", json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 6000, "temperature": 0.2},
        })
        if resp.status_code == 200:
            candidates = resp.json().get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "") or resume_text
        # Any non-200 (429, 503, etc.) → fall back instantly, no wait
        print(f"  Tailor resume skipped (HTTP {resp.status_code}) — using original .tex")
        return resume_text
    except Exception:
        return resume_text


def _has_gemini_quota(min_remaining: int = 100) -> bool:
    """Return True if enough Gemini quota remains to tailor one more resume.

    Reads today's usage from the api_usage table.
    Falls back to True (assume quota available) if the DB call fails —
    better to attempt tailoring than to silently downgrade.
    """
    try:
        from job_scout.db.repositories.usage import get_usage_today
        usage = get_usage_today("gemini")
        return usage.get("remaining", 9999) >= min_remaining
    except Exception:
        return True   # fail-open: try tailoring rather than silently skipping


def _generate_cover_letter(job: Dict, resume_text: str) -> str:
    """Generate cover letter — one-shot, no retry. Returns '' if rate limited."""
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key or not resume_text:
        return ""
    try:
        import httpx
        from job_scout.ai.gemini import GEMINI_API_URL
        company_info = job.get("companies", {}) or {}
        company_name = company_info.get("name", "") or job.get("company_name", "Unknown")
        prompt = f"""Write a concise cover letter (3 short paragraphs, under 200 words) for:
Role: {job.get('title','?')} at {company_name}
Candidate background: {resume_text[:800]}
Rules: facts only, mention role+company, no fluff, plain text."""
        client = httpx.Client(timeout=20.0)
        resp = client.post(f"{GEMINI_API_URL}?key={gemini_key}", json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 400, "temperature": 0.3},
        })
        if resp.status_code == 200:
            candidates = resp.json().get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
        print(f"  Cover letter skipped (HTTP {resp.status_code}) — continuing without")
        return ""
    except Exception:
        return ""


def _record_application(db, job: Dict, result: ApplyResult, resume_text: str):
    """Persist the application outcome to the applications table."""
    if not db or not job.get("id"):
        return

    job_id = job["id"]
    try:
        from datetime import datetime, timedelta

        payload = {
            "job_id": job_id,
            "status": result.status if result.status == "applied" else "saved",
            "applied_via": f"auto_tier{result.tier}",
            "cover_letter": result.cover_letter[:5000] if result.cover_letter else None,
            "notes": result.notes[:500] if result.notes else None,
        }

        if result.status == "applied":
            now = datetime.now()
            payload["applied_at"] = now.isoformat()
            payload["follow_up_due_at"] = (now + timedelta(days=5)).isoformat()
            # Also update the jobs table for V1 compat
            try:
                db._request("PATCH", f"jobs?id=eq.{job_id}", json={
                    "user_action": "applied",
                    "applied_date": now.isoformat(),
                    "follow_up_date": (now + timedelta(days=5)).isoformat(),
                    "is_new": False,
                })
            except Exception:
                pass
        elif result.status == "needs_attention":
            try:
                db._request("PATCH", f"jobs?id=eq.{job_id}", json={
                    "user_action": "needs_attention",
                    "is_new": False,
                })
            except Exception:
                pass

        # Upsert into applications table
        db._request(
            "POST", "applications", json=payload,
            headers={**db.headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
        )
    except Exception as e:
        print(f"_record_application error for {job_id}: {e}")


# Max jobs from the same company in a single batch — prevents one company's
# career page flooding the pipeline (e.g. SpaceX 6 Starlink roles).
_MAX_PER_COMPANY = int(os.getenv("AUTO_APPLY_MAX_PER_COMPANY", "2"))


def run_auto_apply_batch(
    db,
    jobs: list,
    resume_text: str,
    daily_cap: int = 50,
    headless: bool = True,
) -> Dict:
    """
    Prepare applications for a batch of jobs: generate cover letter, mark
    needs_attention, store in applications table. NO Playwright — the user
    triggers the actual form-fill from the UI when they're ready.

    Stops at daily_cap. Max `_MAX_PER_COMPANY` jobs per company.
    Returns stats dict.
    """
    from collections import Counter

    stats = {"evaluated": 0, "prepared": 0, "needs_attention": 0, "skipped": 0}
    profile = load_applicant_profile()

    if not profile.get("email"):
        print("run_auto_apply_batch: APPLY_EMAIL not set — skipping")
        stats["skipped"] = len(jobs)
        return stats

    from job_scout.pipeline.rules_engine import load_rules, find_matching_rule

    rules = load_rules(db)
    if not rules:
        print("run_auto_apply_batch: no DB rules — using built-in default (score≥80)")
        rules = [{
            "name": "_builtin_default",
            "is_active": True,
            "priority": 0,
            "conditions": {"all_of": [
                {"field": "match_score", "op": ">=", "value": 80},
            ]},
            "action": {"type": "auto_apply", "tier": 1},
        }]

    company_counts: Counter = Counter()

    for job in jobs:
        if stats["prepared"] >= daily_cap:
            stats["skipped"] += len(jobs) - stats["evaluated"]
            break

        stats["evaluated"] += 1

        # Per-company cap
        co_name = ((job.get("companies") or {}).get("name") or "").lower()
        if co_name and company_counts[co_name] >= _MAX_PER_COMPANY:
            stats["skipped"] += 1
            continue

        matching_rule = find_matching_rule(job, rules)
        if not matching_rule:
            stats["skipped"] += 1
            continue

        action = matching_rule.get("action") or {}
        if action.get("type") != "auto_apply":
            stats["skipped"] += 1
            continue

        # Prepare the application: cover letter + record — no Playwright.
        try:
            cover_letter = _generate_cover_letter(job, resume_text)
            result = ApplyResult(
                status="needs_attention", tier=0,
                apply_url=job.get("apply_url", ""),
                cover_letter=cover_letter,
                notes="Prepared — open Prefill & Apply in the Jobs page to fill the form.",
            )
            _record_application(db, job, result, resume_text)
            stats["needs_attention"] += 1
            stats["prepared"] += 1
            if co_name:
                company_counts[co_name] += 1
            print(f"  📋 Prepared: {job.get('title')} — {co_name or 'unknown'}")
        except Exception as e:
            stats["skipped"] += 1
            print(f"  ❌ Prepare error: {job.get('title')} — {e}")

    return stats


def prefill_and_open(job: Dict, resume_text: str, db=None) -> ApplyResult:
    """Open a VISIBLE Playwright browser, prefill the application form, and
    leave the window open for the user to review and submit.

    Called from the UI (Jobs page "Prefill & Open" button), NOT from the
    scheduled pipeline.
    """
    return apply_to_job(job, resume_text, headless=False, db=db)
