"""
Tests for job_scout.enrichment.dedup
Bug-driven: covers the exact cases that caused dedup failures in V1.
"""

import pytest
from job_scout.enrichment.dedup import normalize_text, generate_job_fingerprint, is_globally_remote


# ── normalize_text ────────────────────────────────────────────────────────────

def test_normalize_strips_company_suffixes():
    assert "acme" == normalize_text("Acme Inc.")
    assert "acme" == normalize_text("Acme LLC")
    assert "acme" == normalize_text("ACME Ltd.")


def test_normalize_strips_yc_batch():
    assert "vercel" == normalize_text("Vercel (YC W21)")
    assert "linear" == normalize_text("Linear (YC S20)")


def test_normalize_lowercases_and_collapses_whitespace():
    result = normalize_text("  Senior  Backend  Engineer  ")
    assert result == "senior backend engineer"


def test_normalize_removes_punctuation():
    result = normalize_text("C++, Python & Go")
    assert "c" in result
    assert "+" not in result


# ── generate_job_fingerprint ──────────────────────────────────────────────────

def test_fingerprint_same_job_same_company():
    fp1 = generate_job_fingerprint("Backend Engineer", "Vercel")
    fp2 = generate_job_fingerprint("Backend Engineer", "Vercel")
    assert fp1 == fp2


def test_fingerprint_different_title_different_hash():
    fp1 = generate_job_fingerprint("Backend Engineer", "Vercel")
    fp2 = generate_job_fingerprint("Frontend Engineer", "Vercel")
    assert fp1 != fp2


def test_fingerprint_different_company_different_hash():
    fp1 = generate_job_fingerprint("Backend Engineer", "Vercel")
    fp2 = generate_job_fingerprint("Backend Engineer", "Linear")
    assert fp1 != fp2


def test_fingerprint_ignores_suffix_noise():
    """Companies with and without 'Inc.' should produce the same fingerprint."""
    fp1 = generate_job_fingerprint("Software Engineer", "Acme Inc.")
    fp2 = generate_job_fingerprint("Software Engineer", "Acme")
    assert fp1 == fp2


def test_fingerprint_ignores_yc_batch():
    """YC batch tag should not change the fingerprint."""
    fp1 = generate_job_fingerprint("Software Engineer", "Linear (YC S20)")
    fp2 = generate_job_fingerprint("Software Engineer", "Linear")
    assert fp1 == fp2


def test_fingerprint_is_32_chars():
    fp = generate_job_fingerprint("Engineer", "Acme")
    assert len(fp) == 32


# ── is_globally_remote ────────────────────────────────────────────────────────

def test_globally_remote_worldwide_location():
    job = {"location": "Worldwide", "is_remote": True, "title": "", "description": ""}
    assert is_globally_remote(job) is True


def test_globally_remote_rejects_us_only():
    job = {"location": "Remote", "is_remote": True,
           "title": "", "description": "US only — must be authorized to work in the US"}
    assert is_globally_remote(job) is False


def test_globally_remote_rejects_india_location():
    job = {"location": "Bangalore, India", "is_remote": False, "title": "", "description": ""}
    assert is_globally_remote(job) is False


def test_globally_remote_rejects_eu_only():
    job = {"location": "Remote", "is_remote": True,
           "title": "", "description": "EU only — candidates must be EU residents"}
    assert is_globally_remote(job) is False


def test_globally_remote_accepts_plain_remote():
    job = {"location": "Remote", "is_remote": True, "title": "", "description": ""}
    assert is_globally_remote(job) is True


def test_globally_remote_accepts_work_from_anywhere():
    job = {"location": "Work from anywhere", "is_remote": True, "title": "", "description": ""}
    assert is_globally_remote(job) is True


def test_globally_remote_empty_location_marked_remote():
    job = {"location": "", "is_remote": True, "title": "", "description": ""}
    assert is_globally_remote(job) is True
