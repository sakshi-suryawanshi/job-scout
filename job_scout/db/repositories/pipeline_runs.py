# job_scout/db/repositories/pipeline_runs.py
"""Pipeline run repository."""

from datetime import datetime
from typing import List, Dict, Optional
from job_scout.db.client import get_db


def create_run(triggered_by: str = "manual") -> Optional[Dict]:
    db = get_db()
    try:
        result = db._request("POST", "pipeline_runs", json={
            "triggered_by": triggered_by, "started_at": datetime.now().isoformat(), "status": "running"
        })
        return result[0] if isinstance(result, list) else result
    except Exception as e:
        print(f"Error creating pipeline run: {e}")
        return None


def complete_run(run_id: str, status: str = "success", stats: Dict = None, digest_html: str = None, error_log: str = None) -> bool:
    db = get_db()
    try:
        db._request("PATCH", f"pipeline_runs?id=eq.{run_id}", json={
            "completed_at": datetime.now().isoformat(), "status": status,
            "stats": stats, "digest_html": digest_html, "error_log": error_log,
        })
        return True
    except Exception as e:
        print(f"Error completing run: {e}")
        return False


def get_recent_runs(limit: int = 30) -> List[Dict]:
    db = get_db()
    try:
        return db._request("GET", "pipeline_runs", params={
            "order": "started_at.desc", "limit": limit
        }) or []
    except Exception as e:
        print(f"Error getting runs: {e}")
        return []


def add_stage_result(run_id: str, stage_name: str, status: str, stats: Dict = None, error: str = None) -> None:
    db = get_db()
    try:
        db._request("POST", "pipeline_stage_results", json={
            "run_id": run_id, "stage_name": stage_name, "status": status,
            "stats": stats, "error": error,
            "completed_at": datetime.now().isoformat(),
        })
    except Exception:
        pass
