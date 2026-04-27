# job_scout/db/repositories/jobs.py
"""Job repository — thin wrappers over PostgREST for job entities."""

from typing import List, Dict, Optional
from job_scout.db.client import get_db


def get_jobs(**filters) -> List[Dict]:
    return get_db().get_jobs(**filters)


def get_job_by_fingerprint(fingerprint: str) -> Optional[Dict]:
    return get_db().get_job_by_fingerprint(fingerprint)


def get_apply_queue(limit: int = 500) -> List[Dict]:
    return get_db().get_apply_queue(limit=limit)


def get_follow_ups_due() -> List[Dict]:
    return get_db().get_follow_ups_due()


def upsert_job(job: Dict) -> Optional[Dict]:
    return get_db().upsert_job(job)


def add_jobs_bulk(jobs: List[Dict]) -> int:
    return get_db().add_jobs_bulk(jobs)


def mark_job_action(job_id: str, action: str) -> bool:
    return get_db().mark_job_action(job_id, action)


def mark_job_applied(job_id: str, notes: str = None) -> bool:
    return get_db().mark_job_applied(job_id, notes)


def snooze_follow_up(job_id: str, days: int = 3) -> bool:
    return get_db().snooze_follow_up(job_id, days)
