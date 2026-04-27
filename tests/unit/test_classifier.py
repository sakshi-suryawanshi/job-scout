"""
Tests for job_scout.enrichment.classifier
"""

import pytest
from job_scout.enrichment.classifier import classify_job


def _cats(job, company=None):
    return {c["category"] for c in classify_job(job, company)}


def test_yc_company_tagged():
    job = {"title": "Backend Engineer", "description": "YC W24 startup"}
    assert "yc" in _cats(job)


def test_yc_source_tagged():
    job = {"title": "Backend Engineer", "description": ""}
    company = {"source": "yc_directory"}
    assert "yc" in _cats(job, company)


def test_asap_language_tagged():
    job = {"title": "Backend Engineer (ASAP hire)", "description": ""}
    assert "asap" in _cats(job)


def test_urgent_asap():
    job = {"title": "Software Engineer", "description": "We need someone urgently."}
    assert "asap" in _cats(job)


def test_salary_transparent_from_data():
    job = {"title": "Engineer", "description": "", "salary_min": 50000, "salary_max": 80000}
    assert "salary_transparent" in _cats(job)


def test_salary_transparent_from_board():
    job = {"title": "Engineer", "description": "", "source_board": "cord"}
    assert "salary_transparent" in _cats(job)


def test_no_salary_no_transparent():
    job = {"title": "Engineer", "description": "We don't share salary."}
    assert "salary_transparent" not in _cats(job)


def test_small_company_startup():
    job = {"title": "Engineer", "description": ""}
    company = {"headcount": 10, "funding_stage": "seed"}
    result = _cats(job, company)
    assert "startup" in result


def test_funding_keyword_in_description():
    job = {"title": "Engineer", "description": "We just raised a Series A round."}
    assert "funding" in _cats(job)


def test_hidden_gem_africa():
    job = {"title": "Engineer", "description": "Remote role, team based in Kenya."}
    assert "hidden_gem" in _cats(job)


def test_hidden_gem_latam():
    job = {"title": "Engineer", "description": "Work with our team in Latin America."}
    assert "hidden_gem" in _cats(job)


def test_recommended_high_score():
    job = {"title": "Engineer", "description": "", "match_score": 85}
    assert "recommended" in _cats(job)


def test_not_recommended_low_score():
    job = {"title": "Engineer", "description": "", "match_score": 50}
    assert "recommended" not in _cats(job)


def test_desperation_high_score():
    job = {"title": "Engineer", "description": "", "desperation_score": 75}
    assert "desperation" in _cats(job)


def test_no_duplicate_categories():
    job = {"title": "Engineer", "description": "YC W24 ASAP hire urgently.",
           "salary_min": 60000, "match_score": 90, "desperation_score": 80}
    cats = [c["category"] for c in classify_job(job)]
    assert len(cats) == len(set(cats))
