# job_scout/scraping/boards/_salary.py
"""Salary-transparent job board scrapers: Cord, Wellfound, Hired, Talent.io, Pallet."""

import httpx
from typing import List, Dict
from job_scout.scraping.base import clean_html
from job_scout.scraping.boards._rss import parse_rss_feed


class CordScraper:
    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0", "Accept": "application/json"})
            resp = client.get("https://cord.co/api/jobs", params={"remote": "true", "limit": limit})
            if resp.status_code == 200:
                data = resp.json()
                jobs = []
                for i in (data if isinstance(data, list) else data.get("jobs", data.get("results", [])))[:limit]:
                    company = i.get("company", {}) or {}
                    sal = i.get("salary", {}) or {}
                    jobs.append({
                        "title": i.get("title", i.get("role", "")),
                        "company_name": company.get("name", i.get("company_name", "Unknown")),
                        "location": i.get("location", "Remote"),
                        "is_remote": i.get("remote", True),
                        "apply_url": i.get("url", i.get("apply_url", "")),
                        "description": clean_html(i.get("description", ""))[:5000],
                        "source_board": "cord",
                        "salary_min": sal.get("min") or sal.get("minimum") or i.get("salary_min"),
                        "salary_max": sal.get("max") or sal.get("maximum") or i.get("salary_max"),
                        "posted_at": i.get("created_at") or i.get("published_at"),
                    })
                return jobs
        except Exception:
            pass
        return parse_rss_feed("https://cord.co/jobs/remote.rss", "cord", limit)


class WellfoundScraper:
    def get_jobs(self, limit: int = 100) -> List[Dict]:
        for url in [
            "https://wellfound.com/jobs/software-engineer.rss",
            "https://angel.co/job_listings.rss",
            "https://wellfound.com/jobs.rss",
        ]:
            jobs = parse_rss_feed(url, "wellfound", limit)
            if jobs:
                return jobs
        return []


class HiredScraper:
    def get_jobs(self, limit: int = 80) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0", "Accept": "application/json"})
            resp = client.get("https://hired.com/api/v1/job_listings", params={"remote": 1, "limit": limit})
            if resp.status_code == 200:
                data = resp.json()
                return [
                    {
                        "title": i.get("title", i.get("job_function", "")),
                        "company_name": (i.get("company", {}) or {}).get("name", "Unknown") if isinstance(i.get("company"), dict) else str(i.get("company", "Unknown")),
                        "location": (i.get("locations") or ["Remote"])[0],
                        "is_remote": i.get("remote", False) or "remote" in str(i.get("locations", [])).lower(),
                        "apply_url": i.get("url", ""),
                        "description": clean_html(i.get("description", ""))[:5000],
                        "source_board": "hired",
                        "salary_min": i.get("salary_min") or i.get("min_salary"),
                        "salary_max": i.get("salary_max") or i.get("max_salary"),
                        "posted_at": i.get("created_at"),
                    }
                    for i in (data if isinstance(data, list) else data.get("job_listings", []))[:limit]
                ]
        except Exception:
            pass
        return parse_rss_feed("https://hired.com/jobs/rss", "hired", limit)


class TalentioScraper:
    def get_jobs(self, limit: int = 80) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0", "Accept": "application/json"})
            resp = client.get(
                "https://api.talent.io/api/v1/public/jobs",
                params={"remote": "true", "limit": limit, "type": "permanent"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return [
                    {
                        "title": i.get("title", i.get("name", "")),
                        "company_name": (i.get("company", {}) or {}).get("name", "Unknown"),
                        "location": i.get("location", "Remote"),
                        "is_remote": i.get("remote", True),
                        "apply_url": i.get("url", i.get("apply_url", "")),
                        "description": clean_html(i.get("description", ""))[:5000],
                        "source_board": "talentio",
                        "salary_min": (i.get("salary", {}) or i.get("compensation", {}) or {}).get("min") or (i.get("salary", {}) or i.get("compensation", {}) or {}).get("minimum"),
                        "salary_max": (i.get("salary", {}) or i.get("compensation", {}) or {}).get("max") or (i.get("salary", {}) or i.get("compensation", {}) or {}).get("maximum"),
                        "posted_at": i.get("created_at") or i.get("published_at"),
                    }
                    for i in (data if isinstance(data, list) else data.get("jobs", data.get("results", [])))[:limit]
                ]
        except Exception as e:
            print(f"Talent.io error: {e}")
        return []


class PalletScraper:
    BOARDS = [
        "pragmaticengineer", "levels", "lenny", "techleadhub", "highgrowthengineer",
        "remotepython", "devtoolsdigest", "swizec", "buildspace", "the-open-source-observer",
    ]

    def get_jobs(self, limit: int = 100) -> List[Dict]:
        jobs = []
        for board in self.BOARDS:
            jobs.extend(parse_rss_feed(f"https://{board}.pallet.xyz/jobs/rss", "pallet", limit=20))
            if len(jobs) >= limit:
                break
        return jobs[:limit]
