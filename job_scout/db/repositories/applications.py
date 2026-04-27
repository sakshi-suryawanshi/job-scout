# job_scout/db/repositories/applications.py
"""Application repository — query the applications + application_events tables."""

from typing import List, Dict, Optional
from job_scout.db.client import get_db


def get_applications(status: str = None, limit: int = 500) -> List[Dict]:
    db = get_db()
    params = {"limit": limit, "order": "created_at.desc",
              "select": "*,jobs(title,apply_url,company_id,companies(name))"}
    if status:
        params["status"] = f"eq.{status}"
    try:
        return db._request("GET", "applications", params=params) or []
    except Exception as e:
        print(f"Error getting applications: {e}")
        return []


def get_application_by_job(job_id: str) -> Optional[Dict]:
    db = get_db()
    try:
        result = db._request("GET", "applications", params={"job_id": f"eq.{job_id}", "limit": 1})
        return result[0] if result else None
    except Exception:
        return None


def upsert_application(job_id: str, status: str, **extra) -> Optional[Dict]:
    db = get_db()
    payload = {"job_id": job_id, "status": status, **extra}
    try:
        result = db._request("POST", "applications", json=payload,
                              headers={**db.headers, "Prefer": "resolution=merge-duplicates,return=representation"})
        return result[0] if isinstance(result, list) else result
    except Exception as e:
        print(f"Error upserting application: {e}")
        return None


def get_follow_ups_due(limit: int = 100) -> List[Dict]:
    from datetime import datetime
    db = get_db()
    try:
        return db._request("GET", "applications", params={
            "status": "eq.applied",
            "follow_up_due_at": f"lte.{datetime.now().isoformat()}",
            "order": "follow_up_due_at.asc",
            "limit": limit,
            "select": "*,jobs(title,apply_url,companies(name))",
        }) or []
    except Exception as e:
        print(f"Error getting follow-ups: {e}")
        return []
