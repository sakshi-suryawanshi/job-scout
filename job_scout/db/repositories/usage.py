# job_scout/db/repositories/usage.py
"""API usage repository — DB-backed quota tracking (replaces broken JSON files)."""

from datetime import date
from typing import Dict
from job_scout.db.client import get_db


def record_usage(provider: str, count: int = 1) -> None:
    """Increment usage counter for provider in the api_usage table."""
    db = get_db()
    period_key = date.today().isoformat()
    try:
        # Try update first (upsert via merge-duplicates)
        payload = {"provider": provider, "period_key": period_key, "count": count,
                   "last_call_at": date.today().isoformat()}
        db._request("POST", "api_usage", json=payload,
                    headers={**db.headers, "Prefer": "resolution=merge-duplicates,return=representation"})
    except Exception:
        # Fallback: just log silently — never crash the main pipeline over quota tracking
        pass


def get_usage_today(provider: str) -> Dict:
    """Return {calls, remaining, limit} for provider today."""
    db = get_db()
    limits = {"gemini": 1500, "serper": 2500, "gmail": 500}
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
