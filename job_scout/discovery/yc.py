# job_scout/discovery/yc.py
# Moved from worker/discovery/yc_scraper.py — renamed to canonical name.
"""YC company discovery via yclist.com API."""

import httpx
import json
import re
from typing import List, Dict, Optional


class YCScraper:
    def __init__(self):
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    def fetch_from_github(self) -> List[Dict]:
        companies = []
        try:
            response = self.client.get("https://yclist.com/api/companies")
            response.raise_for_status()
            for item in response.json():
                companies.append({
                    "name": item.get("name"),
                    "website": item.get("url"),
                    "batch": item.get("batch"),
                    "status": item.get("status"),
                    "description": item.get("description"),
                })
            print(f"✅ Fetched {len(companies)} from yclist.com")
        except Exception as e:
            print(f"⚠️ yclist failed: {e}")
            companies = self._fetch_from_yc_api()
        return companies

    def _fetch_from_yc_api(self) -> List[Dict]:
        companies = []
        try:
            url = "https://www.ycombinator.com/companies"
            headers = {
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.5",
                "Cache-Control": "max-age=0",
            }
            response = self.client.get(url, headers=headers)
            text = response.text
            json_pattern = r'window\.__INITIAL_STATE__\s*=\s*({.+?});'
            match = re.search(json_pattern, text, re.DOTALL)
            if match:
                json.loads(match.group(1))
            company_pattern = r'"name":"([^"]+)","slug":"([^"]+)","batch":"([^"]*)"'
            for name, slug, batch in re.findall(company_pattern, text):
                companies.append({"name": name, "slug": slug, "batch": batch,
                                   "website": f"https://www.ycombinator.com/companies/{slug}"})
        except Exception as e:
            print(f"⚠️ YC API failed: {e}")
        return companies

    def fetch_by_batch(self, batch: str) -> List[Dict]:
        all_companies = self.fetch_from_github()
        filtered = [c for c in all_companies if c.get("batch") == batch]
        print(f"Filtered {len(filtered)} companies from batch {batch}")
        return filtered

    def to_db_format(self, company: Dict) -> Dict:
        website = company.get("website") or company.get("url")
        career_url = None
        if website:
            domain = website.replace("https://", "").replace("http://", "").rstrip("/")
            if "." in domain:
                career_url = f"https://{domain}/careers"

        batch = company.get("batch", "")
        funding_stage = None
        if batch:
            try:
                year = 2000 + int(batch[1:]) if len(batch) >= 2 else 2024
                if year >= 2024:
                    funding_stage = "seed"
                elif year >= 2022:
                    funding_stage = "series_a"
                else:
                    funding_stage = "series_b"
            except Exception:
                funding_stage = "seed"

        return {
            "name": company.get("name"),
            "career_url": career_url,
            "website": website,
            "ats_type": "unknown",
            "funding_stage": funding_stage,
            "source": "yc_directory",
            "is_active": True,
            "notes": f"YC Batch: {batch}, Status: {company.get('status', 'active')}" if batch else None,
            "priority_score": 10 if funding_stage in ["seed", "pre-seed"] else 5,
        }


def fetch_yc_companies(batch: Optional[str] = None, limit: int = 100, enrich: bool = False) -> List[Dict]:
    """Fetch YC companies. enrich=True is a no-op placeholder for future ATS-slug enrichment."""
    scraper = YCScraper()
    raw = scraper.fetch_by_batch(batch) if batch else scraper.fetch_from_github()
    db_companies = [scraper.to_db_format(c) for c in raw]
    valid = [c for c in db_companies if c.get("name") and c.get("career_url")]
    print(f"✅ Returning {len(valid)} valid companies (requested limit: {limit})")
    return valid[:limit]


# Backward-compat aliases
fetch_yc_companies_v2 = fetch_yc_companies
YCScraperV2 = YCScraper
