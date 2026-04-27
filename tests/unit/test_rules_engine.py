"""
Tests for job_scout.pipeline.rules_engine
Covers the condition tree evaluation logic.
"""

import pytest
from job_scout.pipeline.rules_engine import match_rule, find_matching_rule, _eval_condition


_JOB = {
    "match_score": 85,
    "is_remote_global": True,
    "ats_type": "greenhouse",
    "desperation_score": 60,
    "categories": ["startup", "desperation"],
    "title": "Backend Engineer",
}

_RULE_HIGH_SCORE = {
    "name": "High-confidence backend",
    "is_active": True,
    "priority": 10,
    "conditions": {
        "all_of": [
            {"field": "match_score", "op": ">=", "value": 80},
            {"field": "is_remote_global", "op": "==", "value": True},
            {"field": "ats_type", "op": "in", "value": ["greenhouse", "lever", "ashby"]},
        ]
    },
    "action": {"type": "auto_apply", "tier": 1},
}


# ── _eval_condition ───────────────────────────────────────────────────────────

def test_gte_passes():
    assert _eval_condition({"match_score": 85}, {"field": "match_score", "op": ">=", "value": 80})


def test_gte_fails():
    assert not _eval_condition({"match_score": 70}, {"field": "match_score", "op": ">=", "value": 80})


def test_in_passes():
    assert _eval_condition({"ats_type": "lever"}, {"field": "ats_type", "op": "in", "value": ["greenhouse", "lever"]})


def test_in_fails():
    assert not _eval_condition({"ats_type": "workday"}, {"field": "ats_type", "op": "in", "value": ["greenhouse", "lever"]})


def test_any_in_list():
    assert _eval_condition(
        {"categories": ["startup", "desperation"]},
        {"field": "categories", "op": "any_in", "value": ["desperation", "funding"]},
    )


def test_any_in_fails():
    assert not _eval_condition(
        {"categories": ["salary_transparent"]},
        {"field": "categories", "op": "any_in", "value": ["desperation", "funding"]},
    )


def test_eq_passes():
    assert _eval_condition({"is_remote_global": True}, {"field": "is_remote_global", "op": "==", "value": True})


# ── match_rule ────────────────────────────────────────────────────────────────

def test_rule_matches_high_score_job():
    assert match_rule(_JOB, _RULE_HIGH_SCORE) is True


def test_rule_fails_low_score():
    job = {**_JOB, "match_score": 70}
    assert match_rule(job, _RULE_HIGH_SCORE) is False


def test_inactive_rule_never_matches():
    rule = {**_RULE_HIGH_SCORE, "is_active": False}
    assert match_rule(_JOB, rule) is False


def test_rule_fails_wrong_ats():
    job = {**_JOB, "ats_type": "workday"}
    assert match_rule(job, _RULE_HIGH_SCORE) is False


def test_rule_any_of_condition():
    rule = {
        "name": "Desperate or funded",
        "is_active": True,
        "priority": 5,
        "conditions": {
            "any_of": [
                {"field": "desperation_score", "op": ">=", "value": 70},
                {"field": "match_score", "op": ">=", "value": 90},
            ]
        },
        "action": {"type": "auto_apply"},
    }
    job_desperate = {**_JOB, "desperation_score": 80, "match_score": 60}
    job_high_score = {**_JOB, "desperation_score": 20, "match_score": 95}
    job_neither    = {**_JOB, "desperation_score": 20, "match_score": 60}

    assert match_rule(job_desperate, rule) is True
    assert match_rule(job_high_score, rule) is True
    assert match_rule(job_neither, rule) is False


# ── find_matching_rule ────────────────────────────────────────────────────────

def test_find_first_matching_rule():
    low_priority  = {**_RULE_HIGH_SCORE, "name": "low", "priority": 1}
    high_priority = {**_RULE_HIGH_SCORE, "name": "high", "priority": 10}
    result = find_matching_rule(_JOB, [low_priority, high_priority])
    assert result is not None
    assert result["name"] == "high"


def test_find_no_matching_rule():
    job_bad = {**_JOB, "match_score": 30, "ats_type": "workday"}
    result = find_matching_rule(job_bad, [_RULE_HIGH_SCORE])
    assert result is None


def test_empty_rules_returns_none():
    assert find_matching_rule(_JOB, []) is None
