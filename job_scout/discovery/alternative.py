# job_scout/discovery/alternative.py
# Moved from worker/discovery/alternative_scrapers.py
"""Alternative startup discovery: Wellfound RSS, RemoteOK, WeWorkRemotely."""

import httpx
import xml.etree.ElementTree as ET
from typing import List, Dict

try:
    import feedparser
    _HAS_FEEDPARSER = True
except ImportError:
    _HAS_FEEDPARSER = False


class AlternativeScrapers:
    def __init__(self):
        self.client = httpx.Client(timeout=30.0, follow_redirects=True)

    def fetch_wellfound(self, pages: int = 3) -> List[Dict]:
        companies = []
        if not _HAS_FEEDPARSER:
            return companies
        try:
            feed = feedparser.parse("https://wellfound.com/startups/rss")
            for entry in feed.entries[:50]:
                companies.append({
                    "name": entry.get("title", "").split(" - ")[0],
                    "website": entry.get("link"),
                    "description": entry.get("summary", "")[:200],
                    "source_feed": "wellfound",
                })
        except Exception as e:
            print(f"Wellfound error: {e}")
        return companies

    def fetch_remoteok(self) -> List[Dict]:
        companies = []
        try:
            data = self.client.get("https://remoteok.com/api").json()
            for job in data:
                company_name = job.get("company")
                if company_name:
                    companies.append({
                        "name": company_name,
                        "website": job.get("url", "").split("/jobs")[0] if "/jobs" in job.get("url", "") else None,
                        "is_hiring": True,
                        "source_feed": "remoteok",
                    })
        except Exception as e:
            print(f"RemoteOK error: {e}")
        return companies

    def fetch_we_work_remotely(self) -> List[Dict]:
        companies = []
        try:
            response = self.client.get("https://weworkremotely.com/remote-jobs.rss")
            root = ET.fromstring(response.content)
            for item in root.findall(".//item"):
                title = item.find("title")
                if title is not None and ":" in title.text:
                    company_name = title.text.split(":")[0].strip()
                    companies.append({"name": company_name, "is_hiring": True, "source_feed": "weworkremotely"})
        except Exception as e:
            print(f"WWR error: {e}")
        return companies

    def to_db_format(self, company: Dict) -> Dict:
        website = company.get("website")
        career_url = None
        if website:
            domain = website.replace("https://", "").replace("http://", "").rstrip("/")
            career_url = f"https://{domain}/careers"
        return {
            "name": company.get("name"),
            "career_url": career_url,
            "website": website,
            "ats_type": "unknown",
            "source": company.get("source_feed", "job_board"),
            "is_active": True,
            "notes": f"Hiring remote: {company.get('is_hiring')}" if company.get("is_hiring") else None,
            "priority_score": 8 if company.get("is_hiring") else 5,
        }


def fetch_alternative_sources() -> List[Dict]:
    scraper = AlternativeScrapers()
    all_companies = []
    for name, func in [
        ("Wellfound", scraper.fetch_wellfound),
        ("RemoteOK", scraper.fetch_remoteok),
        ("WeWorkRemotely", scraper.fetch_we_work_remotely),
    ]:
        try:
            print(f"  → {name}...")
            companies = func()
            print(f"    Found {len(companies)}")
            all_companies.extend(companies)
        except Exception as e:
            print(f"    Failed: {e}")

    db_companies = [scraper.to_db_format(c) for c in all_companies]
    seen, unique = set(), []
    for c in db_companies:
        name = (c["name"] or "").lower()
        if name and name not in seen:
            seen.add(name)
            unique.append(c)
    print(f"✅ Total unique companies: {len(unique)}")
    return unique
