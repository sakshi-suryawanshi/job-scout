# job_scout/scraping/ats/workable.py
"""
Workable ATS scraper — public subdomain JSON API.

Endpoint: https://{subdomain}.workable.com/api/v1/jobs
No auth required for public job boards.
"""

import httpx
from typing import List, Dict
from job_scout.scraping.base import is_remote

# Known companies using Workable with their subdomain identifier
WORKABLE_SLUGS = [
    "balena",
    "bugsnag",
    "canny",
    "chatwoot",
    "clearbit",
    "cohere",
    "duffel",
    "elastic",
    "forestadmin",
    "ghost",
    "gitbook",
    "hypercontext",
    "infobip",
    "jellyfish",
    "lottiefiles",
    "miro",
    "mixpanel",
    "notion",
    "opal",
    "papercups",
    "paragon",
    "pendo",
    "posthog",
    "productboard",
    "raycast",
    "readme",
    "screenly",
    "smallstep",
    "snyk",
    "sourcegraph",
    "split",
    "stedi",
    "stoplight",
    "supabase",
    "svix",
    "teleport",
    "tooljet",
    "treblle",
    "upvoty",
    "vantage",
]

_HEADERS = {"User-Agent": "JobScout/1.0 (job search tool)"}


class WorkableScraper:
    """Scrape jobs from Workable public boards."""

    BASE_URL = "https://{slug}.workable.com/api/v1/jobs"

    def __init__(self):
        self.client = httpx.Client(timeout=15.0, headers=_HEADERS)

    def get_jobs(self, company_slug: str) -> List[Dict]:
        url = self.BASE_URL.format(slug=company_slug)
        try:
            resp = self.client.get(url, params={"limit": 100})
            if resp.status_code in (404, 410):
                return []
            resp.raise_for_status()
            data = resp.json()
            jobs = data.get("jobs") or data.get("results") or []
            return [self._parse_job(j, company_slug) for j in jobs]
        except Exception:
            return []

    def _parse_job(self, job: Dict, slug: str) -> Dict:
        loc = (job.get("location") or {})
        location_str = loc.get("location_str") or loc.get("city") or ""
        remote = is_remote(location_str, job.get("title", ""), job.get("description", ""))
        return {
            "title":        job.get("title", "").strip(),
            "location":     location_str,
            "is_remote":    remote or bool(job.get("remote")),
            "apply_url":    job.get("url") or job.get("shortlink") or "",
            "description":  job.get("description", ""),
            "ats_type":     "workable",
            "source_board": f"workable:{slug}",
            "department":   (job.get("department") or {}).get("name", ""),
            "employment_type": job.get("employment_type", ""),
        }


def scrape_workable_for_companies(db, slugs: List[str] = None, criteria: Dict = None) -> Dict:
    """Scrape Workable boards for a list of company slugs. Returns stats."""
    from job_scout.scraping.ats._pipeline import _save_jobs
    slugs = slugs or WORKABLE_SLUGS
    scraper = WorkableScraper()
    stats = {"total_scraped": 0, "saved": 0, "errors": 0}
    for slug in slugs:
        try:
            jobs = scraper.get_jobs(slug)
            stats["total_scraped"] += len(jobs)
            stats["saved"] += _save_jobs(db, jobs, criteria or {})
        except Exception as e:
            print(f"  Workable error [{slug}]: {e}")
            stats["errors"] += 1
    return stats
