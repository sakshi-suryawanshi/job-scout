# job_scout/scraping/ats/smartrecruiters.py
"""
SmartRecruiters ATS scraper — public JSON API.

Endpoint: https://api.smartrecruiters.com/v1/companies/{companyId}/postings
No auth required for public postings.
"""

import httpx
from typing import List, Dict
from job_scout.scraping.base import is_remote

# Known companies using SmartRecruiters with their companyId
SMARTRECRUITERS_IDS = [
    "Atlassian",
    "Automattic",
    "Brainware",
    "Buffer",
    "Canonical",
    "CircleCI",
    "CloudFlare",
    "Contentful",
    "Doist",
    "Dropbox",
    "Elastic",
    "GitLab",
    "Hashicorp",
    "Hotjar",
    "Hubspot",
    "IFTTT",
    "Invision",
    "Loom",
    "Mapbox",
    "MongoDB",
    "Netlify",
    "NewRelic",
    "Okta",
    "PagerDuty",
    "Pivotal",
    "Postman",
    "Productboard",
    "Rancher",
    "Shopify",
    "Skechers",
    "Splitio",
    "Square",
    "Stripe",
    "SumoLogic",
    "Talend",
    "TIBCO",
    "Twilio",
    "Typeform",
    "Zapier",
    "Zendesk",
]

_HEADERS = {"User-Agent": "JobScout/1.0 (job search tool)"}
_API_BASE = "https://api.smartrecruiters.com/v1/companies/{company}/postings"


class SmartRecruitersScraper:
    """Scrape jobs from SmartRecruiters public API."""

    def __init__(self):
        self.client = httpx.Client(timeout=15.0, headers=_HEADERS)

    def get_jobs(self, company_id: str) -> List[Dict]:
        url = _API_BASE.format(company=company_id)
        try:
            resp = self.client.get(url, params={"limit": 100, "status": "PUBLIC"})
            if resp.status_code in (404, 410):
                return []
            resp.raise_for_status()
            data = resp.json()
            postings = data.get("content") or []
            return [self._parse_job(p, company_id) for p in postings]
        except Exception:
            return []

    def _parse_job(self, posting: Dict, company_id: str) -> Dict:
        loc = posting.get("location") or {}
        city = loc.get("city") or ""
        country = loc.get("country") or ""
        location_str = f"{city}, {country}".strip(", ")
        remote = loc.get("remote", False)
        if not remote:
            remote = is_remote(location_str, posting.get("name", ""), "")
        return {
            "title":        posting.get("name", "").strip(),
            "location":     location_str,
            "is_remote":    remote,
            "apply_url":    posting.get("ref") or f"https://jobs.smartrecruiters.com/{company_id}/{posting.get('id', '')}",
            "description":  posting.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", ""),
            "ats_type":     "smartrecruiters",
            "source_board": f"smartrecruiters:{company_id}",
            "department":   (posting.get("department") or {}).get("label", ""),
            "employment_type": (posting.get("typeOfEmployment") or {}).get("label", ""),
        }


def scrape_smartrecruiters_for_companies(db, company_ids: List[str] = None, criteria: Dict = None) -> Dict:
    """Scrape SmartRecruiters boards. Returns stats."""
    from job_scout.scraping.ats._pipeline import _save_jobs
    company_ids = company_ids or SMARTRECRUITERS_IDS
    scraper = SmartRecruitersScraper()
    stats = {"total_scraped": 0, "saved": 0, "errors": 0}
    for company_id in company_ids:
        try:
            jobs = scraper.get_jobs(company_id)
            stats["total_scraped"] += len(jobs)
            stats["saved"] += _save_jobs(db, jobs, criteria or {})
        except Exception as e:
            print(f"  SmartRecruiters error [{company_id}]: {e}")
            stats["errors"] += 1
    return stats
