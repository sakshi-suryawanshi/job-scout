# job_scout/db/repositories/usage.py
"""API usage repository — DB-backed quota tracking (replaces broken JSON files)."""

from datetime import date
from typing import Dict
from job_scout.db.client import get_db


def record_usage(provider: str, count: int = 1) -> None:
    """Increment usage counter for provider in the api_usage table.

    Uses read-then-write (GET + PATCH, or POST on first call).
    merge-duplicates REPLACES the row so we must compute the new total ourselves.
    Race condition risk is negligible for a single-user pipeline.
    """
    db = get_db()
    period_key = date.today().isoformat()
    try:
        existing = db._request("GET", "api_usage", params={
            "provider": f"eq.{provider}",
            "period_key": f"eq.{period_key}",
            "limit": 1,
        })
        if existing:
            new_count = (existing[0].get("count") or 0) + count
            db._request("PATCH", "api_usage", params={
                "provider": f"eq.{provider}",
                "period_key": f"eq.{period_key}",
            }, json={"count": new_count, "last_call_at": period_key})
        else:
            db._request("POST", "api_usage", json={
                "provider": provider,
                "period_key": period_key,
                "count": count,
                "last_call_at": period_key,
            })
    except Exception:
        pass  # Never crash the pipeline over quota tracking


def get_usage_today(provider: str) -> Dict:
    """Return {calls, remaining, limit} for provider today."""
    db = get_db()
    # Serper daily budget: 2500/month ÷ 30 days ≈ 83 queries/day
    limits = {"gemini": 1500, "serper": 83, "gmail": 500}
    period_key = date.today().isoformat()
    try:
        result = db._request("GET", "api_usage", params={
            "provider": f"eq.{provider}", "period_key": f"eq.{period_key}", "limit": 1
        })
        calls = result[0]["count"] if result else 0
    except Exception:
        calls = 0
    limit = limits.get(provider, 9999)
    return {"calls": calls, "remaining": max(0, limit - calls), "limit": limit}


def get_usage_monthly(provider: str) -> Dict:
    """Return {calls, remaining, limit} for provider this month."""
    db = get_db()
    limits_monthly = {"serper": 2500}
    period_key = date.today().strftime("%Y-%m")
    try:
        result = db._request("GET", "api_usage", params={
            "provider": f"eq.{provider}",
            "period_key": f"like.{period_key}%",
            "select": "count",
        })
        calls = sum(r.get("count", 0) for r in (result or []))
    except Exception:
        calls = 0
    limit = limits_monthly.get(provider, 9999)
    return {"calls": calls, "remaining": max(0, limit - calls), "limit": limit}
