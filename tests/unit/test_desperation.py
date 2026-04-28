"""
Tests for job_scout.enrichment.desperation
"""

import pytest
from job_scout.enrichment.desperation import compute_desperation_score


def test_multi_board_high():
    job = {"title": "Engineer", "description": "", "source_boards": "greenhouse,remoteok,lever,jobicy"}
    result = compute_desperation_score(job)
    assert result["score"] >= 25
    signal_types = {s["type"] for s in result["signals"]}
    assert "multi_board" in signal_types


def test_multi_board_two():
    job = {"title": "Engineer", "description": "", "source_boards": "greenhouse,remoteok"}
    result = compute_desperation_score(job)
    signal_types = {s["type"] for s in result["signals"]}
    assert "multi_board" in signal_types


def test_single_board_no_multi():
    job = {"title": "Engineer", "description": "", "source_boards": "greenhouse"}
    result = compute_desperation_score(job)
    signal_types = {s["type"] for s in result["signals"]}
    assert "multi_board" not in signal_types


def test_urgent_language():
    job = {"title": "Backend Engineer — ASAP hire", "description": "", "source_boards": ""}
    result = compute_desperation_score(job)
    signal_types = {s["type"] for s in result["signals"]}
    assert "urgent_language" in signal_types


def test_small_company_headcount():
    job = {"title": "Engineer", "description": "", "source_boards": ""}
    company = {"headcount": 12}
    result = compute_desperation_score(job, company)
    signal_types = {s["type"] for s in result["signals"]}
    assert "small_company" in signal_types


def test_early_stage_funding():
    job = {"title": "Engineer", "description": "", "source_boards": ""}
    company = {"headcount": None, "funding_stage": "seed"}
    result = compute_desperation_score(job, company)
    signal_types = {s["type"] for s in result["signals"]}
    assert "small_company" in signal_types


def test_score_capped_at_100():
    job = {
        "title": "Engineer — URGENT ASAP IMMEDIATE",
        "description": "Small startup team, series a, desperate to hire",
        "source_boards": "gh,lever,remoteok,jobicy,cord",
        "discovered_at": "2025-01-01",
    }
    company = {"headcount": 5, "funding_stage": "seed"}
    result = compute_desperation_score(job, company)
    assert result["score"] <= 100


def test_empty_job_zero_score():
    result = compute_desperation_score({"title": "", "description": "", "source_boards": ""})
    assert result["score"] == 0
    assert result["signals"] == []


# ── distress / funding signals ────────────────────────────────────────────────

def test_distress_signal_in_company_notes():
    job = {"title": "Engineer", "description": "", "source_boards": ""}
    company = {"notes": "We are desperately looking for someone to join immediately"}
    result = compute_desperation_score(job, company)
    signal_types = {s["type"] for s in result["signals"]}
    assert "distress_signal" in signal_types


def test_distress_signal_urgent_keyword():
    job = {"title": "Engineer", "description": "", "source_boards": ""}
    company = {"notes": "This is urgent — must fill the role in 2 weeks"}
    result = compute_desperation_score(job, company)
    signal_types = {s["type"] for s in result["signals"]}
    assert "distress_signal" in signal_types


def test_funding_signal_serper_source_with_raised():
    job = {"title": "Engineer", "description": "", "source_boards": ""}
    company = {"notes": "Recently raised $4M seed round", "source": "serper"}
    result = compute_desperation_score(job, company)
    signal_types = {s["type"] for s in result["signals"]}
    assert "funding_signal" in signal_types


def test_funding_signal_requires_serper_source():
    """funding_signal only fires when source contains 'serper'."""
    job = {"title": "Engineer", "description": "", "source_boards": ""}
    company = {"notes": "We raised a Series A funding round", "source": "manual"}
    result = compute_desperation_score(job, company)
    signal_types = {s["type"] for s in result["signals"]}
    assert "funding_signal" not in signal_types


# ── Headcount boundary ────────────────────────────────────────────────────────

def test_headcount_exactly_50_gives_10_pts():
    """headcount < 50 → 20 pts; headcount == 50 falls to headcount < 100 → 10 pts."""
    job = {"title": "Engineer", "description": "", "source_boards": ""}
    company = {"headcount": 50}
    result = compute_desperation_score(job, company)
    signal_types = {s["type"] for s in result["signals"]}
    assert "small_company" in signal_types
    weights = [s["weight"] for s in result["signals"] if s["type"] == "small_company"]
    assert weights[0] == 10, f"Expected 10pts for headcount=50, got {weights[0]}"


def test_headcount_49_gives_20_pts():
    job = {"title": "Engineer", "description": "", "source_boards": ""}
    company = {"headcount": 49}
    result = compute_desperation_score(job, company)
    weights = [s["weight"] for s in result["signals"] if s["type"] == "small_company"]
    assert weights[0] == 20, f"Expected 20pts for headcount=49, got {weights[0]}"
