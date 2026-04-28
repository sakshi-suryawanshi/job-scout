# tests/integration/test_pipeline_e2e.py
"""
End-to-end pipeline smoke tests.

These tests require a live Supabase instance (SUPABASE_URL + SUPABASE_KEY in env).
They are skipped automatically in CI unless RUN_INTEGRATION_TESTS=1 is set.

Run locally:
  RUN_INTEGRATION_TESTS=1 pytest tests/integration/ -v
"""

import os
import pytest

SKIP_REASON = "Set RUN_INTEGRATION_TESTS=1 to run integration tests"
requires_db = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason=SKIP_REASON,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_db():
    from db import get_db
    return get_db()


# ── DB connectivity ───────────────────────────────────────────────────────────

@requires_db
def test_db_connection():
    db = _get_db()
    companies = db.get_companies(active_only=False, limit=1)
    assert isinstance(companies, list)


@requires_db
def test_get_jobs_returns_list():
    db = _get_db()
    jobs = db.get_jobs(limit=5, days=90)
    assert isinstance(jobs, list)


# ── Pipeline stages smoke ─────────────────────────────────────────────────────

@requires_db
def test_stage_enrich_no_crash():
    """Stage 3 (enrich) should run without raising even on empty data."""
    from job_scout.pipeline.stages import stage_enrich
    db = _get_db()
    result = stage_enrich(db, config={"max_jobs": 5, "days": 1})
    assert "enriched" in result
    assert "errors" in result


@requires_db
def test_stage_classify_no_crash():
    """Stage 4 (classify) should run without raising even on empty data."""
    from job_scout.pipeline.stages import stage_classify
    db = _get_db()
    result = stage_classify(db, config={"max_jobs": 5, "days": 1})
    assert "classified" in result


@requires_db
def test_stage_follow_ups_no_crash():
    """Stage 7 (follow-ups) should always return a count, never raise."""
    from job_scout.pipeline.stages import stage_follow_ups
    db = _get_db()
    result = stage_follow_ups(db)
    assert "follow_ups_due" in result
    assert isinstance(result["follow_ups_due"], int)


# ── Digest build ──────────────────────────────────────────────────────────────

@requires_db
def test_build_digest_returns_html():
    from job_scout.pipeline.digest import build_digest_html
    db = _get_db()
    html = build_digest_html(db, run_stats={}, config={})
    assert "<html" in html
    assert "Job Scout" in html


# ── Dedup / global-remote filter ─────────────────────────────────────────────

def test_is_globally_remote_us_city_rejected():
    from job_scout.enrichment.dedup import is_globally_remote
    assert is_globally_remote({"is_remote": True, "location": "New York, US"}) is False


def test_is_globally_remote_blank_accepted():
    from job_scout.enrichment.dedup import is_globally_remote
    assert is_globally_remote({"is_remote": True, "location": ""}) is True


def test_is_globally_remote_worldwide_accepted():
    from job_scout.enrichment.dedup import is_globally_remote
    assert is_globally_remote({"is_remote": True, "location": "Worldwide"}) is True


# ── Auto-apply rules repository ───────────────────────────────────────────────

@requires_db
def test_get_rules_returns_list():
    from job_scout.db.repositories.auto_apply_rules import get_rules
    db = _get_db()
    rules = get_rules(db)
    assert isinstance(rules, list)


# ── New ATS scrapers — network smoke (skipped unless network tests enabled) ───

network = pytest.mark.skipif(
    not os.getenv("RUN_NETWORK_TESTS"),
    reason="Set RUN_NETWORK_TESTS=1 to run network tests",
)


@network
def test_workable_scraper_returns_list():
    from job_scout.scraping.ats.workable import WorkableScraper
    scraper = WorkableScraper()
    jobs = scraper.get_jobs("ghost")
    assert isinstance(jobs, list)


@network
def test_smartrecruiters_scraper_returns_list():
    from job_scout.scraping.ats.smartrecruiters import SmartRecruitersScraper
    scraper = SmartRecruitersScraper()
    jobs = scraper.get_jobs("Automattic")
    assert isinstance(jobs, list)
