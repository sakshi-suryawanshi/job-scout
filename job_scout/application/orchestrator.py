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

    company_info = job.get("companies", {}) or {}
    ats_type = (company_info.get("ats_type") or job.get("ats_type") or "unknown").lower()
    source_board = (job.get("source_board") or "").lower()

    # ── Generate cover letter (shared across tiers) ───────────────────────
    cover_letter = _generate_cover_letter(job, resume_text)

    # ── Tier 3: Email outreach ────────────────────────────────────────────
    if source_board in _TIER3_SOURCES or "hn_" in apply_url or "news.ycombinator.com" in apply_url:
        from job_scout.application.email_outreach import send_outreach_email
        result = send_outreach_email(job, resume_text, profile)
        _record_application(db, job, result, resume_text)
        return result

    # ── Tier 1: Full automation ───────────────────────────────────────────
    if ats_type == "greenhouse":
        from job_scout.application.greenhouse_form import apply_greenhouse
        result = apply_greenhouse(apply_url, resume_text, cover_letter, headless, profile)
        _record_application(db, job, result, resume_text)
        return result

    if ats_type == "lever":
        from job_scout.application.lever_form import apply_lever
        result = apply_lever(apply_url, resume_text, cover_letter, headless, profile)
        _record_application(db, job, result, resume_text)
        return result

    if ats_type == "ashby":
        from job_scout.application.ashby_form import apply_ashby
        result = apply_ashby(apply_url, resume_text, cover_letter, headless, profile)
        _record_application(db, job, result, resume_text)
        return result

    # ── Tier 2: Semi-automation (everything else) ─────────────────────────
    from job_scout.application.manual import prepare_manual_apply
    result = prepare_manual_apply(job, resume_text, profile)
    _record_application(db, job, result, resume_text)
    return result


def _generate_cover_letter(job: Dict, resume_text: str) -> str:
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key or not resume_text:
        return ""
    try:
        from job_scout.application.manual import _generate_cover_letter
        from job_scout.ai.gemini import GeminiClient
        gemini = GeminiClient(gemini_key)
        return _generate_cover_letter(gemini, job, resume_text)
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


def run_auto_apply_batch(
    db,
    jobs: list,
    resume_text: str,
    daily_cap: int = 50,
    headless: bool = True,
) -> Dict:
    """
    Apply to a batch of jobs using the rules engine + orchestrator.

    Stops at daily_cap to prevent over-applying.
    Returns stats dict.
    """
    stats = {"evaluated": 0, "applied": 0, "needs_attention": 0, "failed": 0, "skipped": 0}
    profile = load_applicant_profile()

    if not profile.get("email"):
        print("run_auto_apply_batch: APPLY_EMAIL not set — skipping all applications")
        stats["skipped"] = len(jobs)
        return stats

    from job_scout.pipeline.rules_engine import load_rules, find_matching_rule

    rules = load_rules(db)
    if not rules:
        print("run_auto_apply_batch: no active rules — nothing to auto-apply")
        stats["skipped"] = len(jobs)
        return stats

    for job in jobs:
        if stats["applied"] >= daily_cap:
            stats["skipped"] += len(jobs) - stats["evaluated"]
            break

        stats["evaluated"] += 1
        matching_rule = find_matching_rule(job, rules)
        if not matching_rule:
            stats["skipped"] += 1
            continue

        action = matching_rule.get("action") or {}
        if action.get("type") != "auto_apply":
            stats["skipped"] += 1
            continue

        try:
            result = apply_to_job(job, resume_text, headless=headless, profile=profile, db=db)
            if result.status == "applied":
                stats["applied"] += 1
                print(f"  ✅ Applied: {job.get('title')} ({result.tier=})")
            elif result.status == "needs_attention":
                stats["needs_attention"] += 1
                print(f"  ⚠️  Needs attention: {job.get('title')} — {result.notes}")
            else:
                stats["failed"] += 1
                print(f"  ❌ Failed: {job.get('title')} — {result.error}")
        except Exception as e:
            stats["failed"] += 1
            print(f"  ❌ Exception applying to {job.get('title')}: {e}")

    return stats
