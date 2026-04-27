# job_scout/scraping/ats/lever.py
"""Lever ATS scraper — free public API."""

import httpx
import re
from typing import List, Dict
from job_scout.scraping.base import is_remote

LEVER_SLUGS = [
    "plaid", "neon", "mistral",
    "timescale", "wealthsimple", "braze", "contentful",
    "benchling", "labelbox", "hex", "hightouch",
    "meilisearch", "questdb", "parseable", "peerdb",
]


class LeverScraper:
    """Scrape jobs from Lever postings. FREE public API."""

    BASE_URL = "https://api.lever.co/v0/postings"

    def __init__(self):
        self.client = httpx.Client(timeout=15.0, headers={"User-Agent": "JobScout/1.0"})

    def get_jobs(self, company_slug: str) -> List[Dict]:
        url = f"{self.BASE_URL}/{company_slug}"
        try:
            response = self.client.get(url)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                return []
            real_jobs = [j for j in data if "moved" not in j.get("text", "").lower() or len(data) > 2]
            return [self._parse_job(j, company_slug) for j in real_jobs]
        except Exception:
            return []

    def _parse_job(self, raw: Dict, company_slug: str) -> Dict:
        title = raw.get("text", "")
        categories = raw.get("categories", {})
        location = categories.get("location", "") or raw.get("workplaceType", "")

        description_parts = []
        for section in raw.get("lists", []):
            description_parts.append(section.get("text", ""))
            for item in section.get("content", "").split("<li>"):
                clean = re.sub(r"<[^>]+>", "", item).strip()
                if clean:
                    description_parts.append(clean)
        additional = raw.get("additional", "")
        if additional:
            description_parts.append(re.sub(r"<[^>]+>", " ", additional))
        description = re.sub(r"\s+", " ", " ".join(description_parts)).strip()

        return {
            "title": title,
            "company_name": company_slug.replace("-", " ").replace("_", " ").title(),
            "company_slug": company_slug,
            "location": location,
            "is_remote": is_remote(location, title, description),
            "apply_url": raw.get("hostedUrl", f"https://jobs.lever.co/{company_slug}/{raw.get('id')}"),
            "description": description[:5000],
            "source_board": "lever",
            "external_id": raw.get("id", ""),
            "posted_at": None,
        }
