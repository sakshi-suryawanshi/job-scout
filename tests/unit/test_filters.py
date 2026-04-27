"""
Tests for job_scout.enrichment.filters.matches_criteria
Bug-driven: covers the filter cases that produced false positives/negatives in V1.
"""

import pytest
from job_scout.enrichment.filters import matches_criteria

_BASE_CRITERIA = {
    "title_keywords": ["backend", "engineer", "developer", "python"],
    "required_skills": ["python"],
    "exclude_keywords": ["staff", "principal", "director", "vp"],
    "remote_only": True,
    "global_remote_only": False,
    "max_yoe": 5,
}


def _job(**kwargs):
    defaults = {
        "title": "Backend Engineer",
        "description": "We use python and go.",
        "location": "Remote",
        "is_remote": True,
    }
    return {**defaults, **kwargs}


# ── Title keyword matching ────────────────────────────────────────────────────

def test_title_keyword_match():
    assert matches_criteria(_job(title="Backend Engineer"), _BASE_CRITERIA) is True


def test_title_keyword_no_match():
    assert matches_criteria(_job(title="Sales Manager"), _BASE_CRITERIA) is False


def test_title_keyword_case_insensitive():
    assert matches_criteria(_job(title="BACKEND ENGINEER"), _BASE_CRITERIA) is True


# ── Exclude keywords ──────────────────────────────────────────────────────────

def test_exclude_keyword_in_title():
    assert matches_criteria(_job(title="Staff Backend Engineer"), _BASE_CRITERIA) is False


def test_exclude_keyword_director():
    assert matches_criteria(_job(title="Director of Engineering"), _BASE_CRITERIA) is False


def test_exclude_keyword_not_in_title_passes():
    assert matches_criteria(_job(title="Backend Engineer"), _BASE_CRITERIA) is True


# ── Remote filter ─────────────────────────────────────────────────────────────

def test_remote_only_filter_rejects_onsite():
    assert matches_criteria(_job(is_remote=False, location="San Francisco"), _BASE_CRITERIA) is False


def test_remote_only_false_accepts_onsite():
    crit = {**_BASE_CRITERIA, "remote_only": False}
    assert matches_criteria(_job(is_remote=False, location="San Francisco"), crit) is True


# ── Skills filter ─────────────────────────────────────────────────────────────

def test_required_skill_in_description():
    assert matches_criteria(_job(description="We use Python and PostgreSQL"), _BASE_CRITERIA) is True


def test_required_skill_missing():
    crit = {**_BASE_CRITERIA, "required_skills": ["java"]}
    assert matches_criteria(_job(description="We use Python"), crit) is False


def test_no_required_skills_passes_all():
    crit = {**_BASE_CRITERIA, "required_skills": []}
    assert matches_criteria(_job(), crit) is True


# ── YOE filter ────────────────────────────────────────────────────────────────

def test_yoe_within_limit():
    # description must mention required skill (python) AND be within YOE limit
    job = _job(description="Requires 3+ years of experience with python")
    assert matches_criteria(job, _BASE_CRITERIA) is True


def test_yoe_exceeds_limit():
    job = _job(description="Requires 8+ years of experience in Python")
    assert matches_criteria(job, _BASE_CRITERIA) is False


def test_no_yoe_mentioned_passes():
    job = _job(description="We use Python and ship fast.")
    assert matches_criteria(job, _BASE_CRITERIA) is True


# ── Salary filter ─────────────────────────────────────────────────────────────

def test_salary_max_below_min_salary_rejected():
    crit = {**_BASE_CRITERIA, "required_skills": [], "min_salary": 50000}
    job = _job(salary_max=30000)
    assert matches_criteria(job, crit) is False


def test_salary_min_above_max_salary_rejected():
    crit = {**_BASE_CRITERIA, "required_skills": [], "max_salary": 60000}
    job = _job(salary_min=80000)
    assert matches_criteria(job, crit) is False


def test_missing_salary_passes_salary_filter():
    crit = {**_BASE_CRITERIA, "required_skills": [], "min_salary": 50000}
    job = _job()  # no salary fields
    assert matches_criteria(job, crit) is True
