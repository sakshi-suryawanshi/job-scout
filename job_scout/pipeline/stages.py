# job_scout/pipeline/stages.py
"""
Each pipeline stage as an isolated function returning a stats dict.
Stages can be enabled/disabled independently.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional


# ── Stage 1: DISCOVER ─────────────────────────────────────────────────────────

def stage_discover(db, config: Dict = None) -> Dict:
    """
    Pull new companies from YC, alternative sources, remoteintech, and Serper.
    Returns: {new_companies, bumped_companies, queries_used, errors}
    """
    config = config or {}
    stats = {"new_companies": 0, "bumped_companies": 0, "queries_used": 0, "errors": 0}

    existing = db.get_companies(active_only=False, limit=10000)
    existing_names = {c["name"].lower() for c in existing}

    def _insert_new(companies: List[Dict], label: str) -> int:
        new = [c for c in companies if (c.get("name") or "").lower() not in existing_names]
        if not new:
            return 0
        inserted = db.add_companies_bulk(new)
        print(f"  {label}: {inserted} new companies")
        for c in new:
            existing_names.add((c.get("name") or "").lower())
        return inserted

    # YC batches
    if config.get("yc_enabled", True):
        try:
            from job_scout.discovery.yc import fetch_yc_companies
            for batch in config.get("yc_batches", ["W24", "S24", "W23"]):
                companies = fetch_yc_companies(batch=batch, limit=config.get("yc_limit", 100))
                stats["new_companies"] += _insert_new(companies, f"YC {batch}")
        except Exception as e:
            print(f"  YC error: {e}")
            stats["errors"] += 1

    # remoteintech/remote-jobs GitHub list
    if config.get("remoteintech_enabled", True):
        try:
            from job_scout.discovery.github_lists import fetch_remoteintech
            companies = fetch_remoteintech(filter_global=True)
            stats["new_companies"] += _insert_new(companies, "remoteintech")
        except Exception as e:
            print(f"  remoteintech error: {e}")
            stats["errors"] += 1

    # Alternative sources (Wellfound RSS, RemoteOK, WWR)
    if config.get("alternative_enabled", True):
        try:
            from job_scout.discovery.alternative import fetch_alternative_sources
            companies = fetch_alternative_sources()
            stats["new_companies"] += _insert_new(companies, "alternative sources")
        except Exception as e:
            print(f"  alternative error: {e}")
            stats["errors"] += 1

    # Serper daily dorks
    if config.get("serper_enabled", True) and os.getenv("SERPER_API_KEY"):
        try:
            from job_scout.discovery.serper_dorking import SerperDorker
            from job_scout.db.repositories.usage import record_usage, get_usage_monthly

            usage = get_usage_monthly("serper")
            if usage["remaining"] < 50:
                print(f"  Serper skipped: only {usage['remaining']} queries left this month")
            else:
                dorker = SerperDorker()
                categories = config.get("serper_categories", [
                    "linkedin_daily", "indeed_daily", "distress_signals",
                    "funding_signals", "yc_latest",
                ])
                max_q = config.get("serper_max_queries_per_category", 3)
                companies_raw = dorker.run_discovery(
                    categories=categories,
                    max_queries_per_category=max_q,
                )
                stats["new_companies"] += _insert_new(companies_raw, "Serper dorking")
                stats["queries_used"] = dorker.queries_used
                record_usage("serper", dorker.queries_used)
        except Exception as e:
            print(f"  Serper error: {e}")
            stats["errors"] += 1

    print(f"Stage 1 DISCOVER: {stats}")
    return stats


# ── Stage 2: SCRAPE ───────────────────────────────────────────────────────────

def stage_scrape(db, config: Dict = None) -> Dict:
    """
    Scrape jobs from all enabled ATS boards + job boards.
    Returns: {jobs_found, jobs_new, jobs_updated, errors, by_source}
    """
    config = config or {}
    stats = {"jobs_found": 0, "jobs_new": 0, "errors": 0, "by_source": {}}

    # Load user criteria from profile preferences
    criteria = _load_criteria(db, config)

    # ATS scraping
    if config.get("ats_enabled", True):
        try:
            from job_scout.scraping.ats import scrape_ats_jobs
            ats_types = config.get("ats_types", ["greenhouse", "lever", "ashby"])
            max_slugs = config.get("max_slugs_per_ats", 100)
            ats_stats = scrape_ats_jobs(db=db, ats_types=ats_types, criteria=criteria, max_slugs_per_ats=max_slugs)
            stats["jobs_found"] += ats_stats.get("total_scraped", 0)
            stats["jobs_new"] += ats_stats.get("saved", 0)
            stats["errors"] += ats_stats.get("errors", 0)
            stats["by_source"]["ats"] = ats_stats.get("by_ats", {})
        except Exception as e:
            print(f"  ATS scrape error: {e}")
            stats["errors"] += 1

    # Board scraping
    if config.get("boards_enabled", True):
        try:
            from job_scout.scraping.boards import scrape_board_jobs
            boards = config.get("boards", None)  # None = use boards_config.json defaults
            board_stats = scrape_board_jobs(db=db, boards=boards, criteria=criteria)
            stats["jobs_found"] += board_stats.get("total_scraped", 0)
            stats["jobs_new"] += board_stats.get("saved", 0)
            stats["errors"] += board_stats.get("errors", 0)
            stats["by_source"]["boards"] = board_stats.get("by_board", {})
        except Exception as e:
            print(f"  boards scrape error: {e}")
            stats["errors"] += 1

    print(f"Stage 2 SCRAPE: {stats['jobs_found']} found, {stats['jobs_new']} new")
    return stats


# ── Stage 3: ENRICH ───────────────────────────────────────────────────────────

def stage_enrich(db, config: Dict = None) -> Dict:
    """
    Compute desperation scores for new unscored jobs.
    Returns: {enriched, errors}
    """
    config = config or {}
    stats = {"enriched": 0, "errors": 0}

    try:
        from job_scout.enrichment.desperation import compute_desperation_for_jobs
        # Only enrich jobs with no desperation score yet
        all_jobs = db.get_jobs(limit=config.get("max_jobs", 1000), days=config.get("days", 90))
        no_desp = [j for j in all_jobs if not j.get("desperation_score")]
        if no_desp:
            stats["enriched"] = compute_desperation_for_jobs(db, no_desp)
    except Exception as e:
        print(f"  enrich error: {e}")
        stats["errors"] += 1

    print(f"Stage 3 ENRICH: {stats}")
    return stats


# ── Stage 4: CLASSIFY ─────────────────────────────────────────────────────────

def stage_classify(db, config: Dict = None) -> Dict:
    """
    Assign multi-label categories to jobs (job_categories table).
    Returns: {classified, categories_added, by_category, errors}
    """
    config = config or {}
    stats = {"classified": 0, "categories_added": 0, "by_category": {}, "errors": 0}

    try:
        from job_scout.enrichment.classifier import classify_jobs_bulk
        all_jobs = db.get_jobs(limit=config.get("max_jobs", 1000), days=config.get("days", 90))
        result = classify_jobs_bulk(db, all_jobs)
        stats.update(result)
    except Exception as e:
        print(f"  classify error: {e}")
        stats["errors"] += 1

    print(f"Stage 4 CLASSIFY: {stats['classified']} jobs, {stats['categories_added']} categories")
    return stats


# ── Stage 5: SCORE ────────────────────────────────────────────────────────────

def stage_score(db, config: Dict = None) -> Dict:
    """
    Score unscored jobs: rule-based pre-filter → Gemini AI.
    Returns: {rule_passed, ai_scored, total_scored, avg_score, errors}
    """
    config = config or {}
    stats = {"rule_passed": 0, "ai_scored": 0, "total_scored": 0, "avg_score": 0.0, "errors": 0}

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    use_ai = config.get("use_ai", True) and bool(gemini_key)

    if use_ai:
        # Check quota guard
        try:
            from job_scout.db.repositories.usage import get_usage_today
            usage = get_usage_today("gemini")
            if usage["remaining"] < 100:
                print(f"  Gemini quota low ({usage['remaining']} left) — rule-based only")
                use_ai = False
        except Exception:
            pass

    try:
        from job_scout.ai.gemini import score_all_jobs
        criteria = _load_criteria(db, config)
        result = score_all_jobs(
            db=db,
            criteria=criteria,
            use_ai=use_ai,
            max_jobs=config.get("max_jobs", 500),
        )
        stats["total_scored"] = result.get("scored", 0)
        stats["avg_score"] = result.get("avg_score", 0.0)
        stats["ai_scored"] = result.get("scored", 0) if result.get("ai_used") else 0
        stats["rule_passed"] = stats["total_scored"]
    except Exception as e:
        print(f"  score error: {e}")
        stats["errors"] += 1

    print(f"Stage 5 SCORE: {stats['total_scored']} scored (avg {stats['avg_score']}), AI={use_ai}")
    return stats


# ── Stage 6: AUTO-APPLY ───────────────────────────────────────────────────────

def stage_auto_apply(db, config: Dict = None) -> Dict:
    """
    Placeholder for auto-apply (Phase 6 of V2_PLAN.md).
    Evaluates rules and tags jobs, but does not submit forms yet.
    Returns: {evaluated, would_apply, needs_attention, skipped}
    """
    config = config or {}
    stats = {"evaluated": 0, "would_apply": 0, "needs_attention": 0, "skipped": 0}

    try:
        from job_scout.pipeline.rules_engine import load_rules, find_matching_rule
        rules = load_rules(db)
        if not rules:
            print("  No auto-apply rules configured — skipping")
            return stats

        # Get unactioned recommended jobs
        all_jobs = db.get_jobs(limit=500, days=config.get("days", 30))
        candidates = [
            j for j in all_jobs
            if not j.get("user_action")
            and (j.get("match_score", 0) or 0) >= 70
        ]

        daily_cap = config.get("daily_auto_apply_cap", 50)
        applied_today = 0

        for job in candidates:
            if applied_today >= daily_cap:
                stats["skipped"] += len(candidates) - stats["evaluated"]
                break

            stats["evaluated"] += 1
            matching_rule = find_matching_rule(job, rules)
            if matching_rule:
                action = (matching_rule.get("action") or {})
                if action.get("type") == "auto_apply":
                    ats_type = job.get("companies", {}).get("ats_type", "unknown") if isinstance(job.get("companies"), dict) else "unknown"
                    if ats_type in ("greenhouse", "lever", "ashby"):
                        # Phase 6 would fire the Playwright applier here.
                        # For now: tag as 'queued_for_auto_apply' so Auto-Pilot UI shows it.
                        try:
                            db._request("PATCH", f"jobs?id=eq.{job['id']}", json={
                                "user_action": "queued_auto_apply"
                            })
                        except Exception:
                            pass
                        stats["would_apply"] += 1
                        applied_today += 1
                    else:
                        stats["needs_attention"] += 1
    except Exception as e:
        print(f"  auto-apply stage error: {e}")

    print(f"Stage 6 AUTO-APPLY (dry run): {stats}")
    return stats


# ── Stage 7: FOLLOW-UPS ───────────────────────────────────────────────────────

def stage_follow_ups(db, config: Dict = None) -> Dict:
    """
    Find applied jobs past their follow-up window.
    Returns: {follow_ups_due}
    """
    config = config or {}
    stats = {"follow_ups_due": 0}

    try:
        follow_ups = db.get_follow_ups_due()
        stats["follow_ups_due"] = len(follow_ups)
    except Exception as e:
        print(f"  follow-ups error: {e}")

    print(f"Stage 7 FOLLOW-UPS: {stats}")
    return stats


# ── Stage 8: DIGEST ───────────────────────────────────────────────────────────

def stage_digest(db, run_stats: Dict, config: Dict = None) -> Dict:
    """
    Compose and send the daily email digest.
    Returns: {digest_html, sent, recipients, errors}
    """
    config = config or {}
    stats = {"digest_html": "", "sent": 0, "recipients": 0, "errors": 0}

    try:
        from job_scout.pipeline.digest import build_digest_html
        html = build_digest_html(db, run_stats, config)
        stats["digest_html"] = html

        # Send if email configured
        recipient = config.get("digest_email") or os.getenv("DIGEST_EMAIL", "")
        if recipient:
            try:
                from job_scout.notifications.email import send_email
                subject = _build_subject(run_stats)
                sent = send_email(to=recipient, subject=subject, html_body=html)
                if sent:
                    stats["sent"] = 1
                    stats["recipients"] = 1
            except Exception as e:
                print(f"  email send error: {e}")
                stats["errors"] += 1
        else:
            print("  DIGEST_EMAIL not set — digest built but not sent")
    except Exception as e:
        print(f"  digest error: {e}")
        stats["errors"] += 1

    print(f"Stage 8 DIGEST: sent={stats['sent']}")
    return stats


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_criteria(db, config: Dict) -> Dict:
    """Load scoring/filter criteria from user profile preferences, with fallback defaults."""
    prefs = config.get("criteria") or {}
    if not prefs:
        try:
            result = db._request("GET", "user_profile", params={"limit": 1})
            prefs = ((result[0].get("preferences") or {}) if result else {})
            prefs = prefs if isinstance(prefs, dict) else {}
        except Exception:
            pass
    return {
        "title_keywords": prefs.get("title_keywords", ["backend", "developer", "engineer", "python", "golang"]),
        "required_skills": prefs.get("skills", []),
        "exclude_keywords": prefs.get("exclude_keywords", ["staff", "principal", "director", "vp"]),
        "remote_only": prefs.get("remote_only", True),
        "global_remote_only": prefs.get("global_remote", True),
        "max_yoe": prefs.get("max_yoe", 5),
        "min_salary": prefs.get("min_salary"),
    }


def _build_subject(run_stats: Dict) -> str:
    from datetime import date
    scrape = run_stats.get("scrape", {})
    score = run_stats.get("score", {})
    auto_apply = run_stats.get("auto_apply", {})
    new = scrape.get("jobs_new", 0)
    applied = auto_apply.get("would_apply", 0)
    attention = auto_apply.get("needs_attention", 0)
    today = date.today().strftime("%B %-d")
    return f"Job Scout Daily — {new} new, {applied} applied, {attention} need you ({today})"
