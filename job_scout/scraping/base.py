# job_scout/scraping/base.py
# Shared utilities used by every scraper.
"""
Shared helpers: HTML cleaning, remote detection, DB job format conversion.
"""

import html
import re
from datetime import datetime, date
from typing import Dict, Optional


def clean_html(text: str) -> str:
    """Strip HTML tags, decode entities, normalize whitespace."""
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_remote(location: str, title: str, description: str = "") -> bool:
    text = f"{location} {title} {description}".lower()
    return any(kw in text for kw in [
        "remote", "worldwide", "anywhere", "work from home",
        "distributed", "wfh", "fully remote",
    ])


def today() -> str:
    return date.today().isoformat()


def now() -> str:
    return datetime.now().isoformat()


def to_db_job(job: Dict, company_id: Optional[str] = None) -> Dict:
    """Convert a scraped job dict to the DB jobs table format."""
    from job_scout.enrichment.dedup import generate_job_fingerprint

    title = job.get("title", "")[:500]
    company_name = job.get("company_name", "")
    fingerprint = generate_job_fingerprint(title, company_name) if company_name else None

    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")
    if salary_min is None and job.get("salary"):
        try:
            salary_min = int(job["salary"])
        except (ValueError, TypeError):
            pass

    return {
        "company_id": company_id,
        "title": title,
        "location": job.get("location", "")[:500],
        "is_remote": job.get("is_remote", False),
        "apply_url": job.get("apply_url", ""),
        "source_board": job.get("source_board", "unknown"),
        "fingerprint": fingerprint,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "match_score": 0,
        "is_new": True,
        "is_recommended": False,
        "discovered_date": today(),
        "discovered_at": now(),
    }
