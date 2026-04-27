# job_scout/scraping/boards/_api.py
"""JSON API-based job board scrapers."""

import httpx
from typing import List, Dict
from job_scout.scraping.base import clean_html, is_remote


class RemoteOKScraper:
    def get_jobs(self) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            data = client.get("https://remoteok.com/api").json()
            return [
                {
                    "title": i.get("position", ""),
                    "company_name": i.get("company", "Unknown"),
                    "location": i.get("location", "Remote"),
                    "is_remote": True,
                    "apply_url": i.get("apply_url") or i.get("url", ""),
                    "description": clean_html(i.get("description", ""))[:5000],
                    "source_board": "remoteok",
                    "salary_min": i.get("salary_min"),
                    "salary_max": i.get("salary_max"),
                    "posted_at": i.get("date"),
                }
                for i in data if i.get("position")
            ]
        except Exception as e:
            print(f"RemoteOK error: {e}")
            return []


class RemotiveScraper:
    def get_jobs(self, category: str = None, limit: int = 200) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            params = {"limit": limit}
            if category:
                params["category"] = category
            data = client.get("https://remotive.com/api/remote-jobs", params=params).json()
            return [
                {
                    "title": i.get("title", ""),
                    "company_name": i.get("company_name", "Unknown"),
                    "location": i.get("candidate_required_location", "Worldwide"),
                    "is_remote": True,
                    "apply_url": i.get("url", ""),
                    "description": clean_html(i.get("description", ""))[:5000],
                    "source_board": "remotive",
                    "salary": i.get("salary", ""),
                    "posted_at": i.get("publication_date"),
                }
                for i in data.get("jobs", [])
            ]
        except Exception as e:
            print(f"Remotive error: {e}")
            return []


class HimalayasScraper:
    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            data = client.get("https://himalayas.app/jobs/api", params={"limit": limit}).json()
            return [
                {
                    "title": i.get("title", ""),
                    "company_name": i.get("companyName", "Unknown"),
                    "location": ", ".join(i.get("locationRestrictions", [])) or "Worldwide",
                    "is_remote": True,
                    "apply_url": i.get("applicationLink") or i.get("guid", ""),
                    "description": clean_html(i.get("description", ""))[:5000],
                    "source_board": "himalayas",
                    "salary_min": i.get("minSalary"),
                    "salary_max": i.get("maxSalary"),
                    "posted_at": i.get("pubDate"),
                }
                for i in data.get("jobs", [])
            ]
        except Exception as e:
            print(f"Himalayas error: {e}")
            return []


class ArbeitnowScraper:
    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            data = client.get("https://arbeitnow.com/api/job-board-api").json()
            return [
                {
                    "title": i.get("title", ""),
                    "company_name": i.get("company_name", "Unknown"),
                    "location": i.get("location", "Remote"),
                    "is_remote": i.get("remote", False) or is_remote(i.get("location", ""), i.get("title", "")),
                    "apply_url": i.get("url", ""),
                    "description": clean_html(i.get("description", ""))[:5000],
                    "source_board": "arbeitnow",
                    "posted_at": i.get("created_at"),
                }
                for i in data.get("data", [])[:limit]
            ]
        except Exception as e:
            print(f"Arbeitnow error: {e}")
            return []


class JobicyScraper:
    def get_jobs(self, limit: int = 50) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            data = client.get(
                "https://jobicy.com/api/v0/remote-jobs",
                params={"count": limit, "geo": "worldwide", "industry": "engineering"},
            ).json()
            return [
                {
                    "title": i.get("jobTitle", ""),
                    "company_name": i.get("companyName", "Unknown"),
                    "location": i.get("jobGeo", "Worldwide"),
                    "is_remote": True,
                    "apply_url": i.get("url", ""),
                    "description": clean_html(i.get("jobDescription", ""))[:5000],
                    "source_board": "jobicy",
                    "salary": i.get("annualSalaryMin", ""),
                    "posted_at": i.get("pubDate"),
                }
                for i in data.get("jobs", [])
            ]
        except Exception as e:
            print(f"Jobicy error: {e}")
            return []


class TheMuseScraper:
    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            data = client.get(
                "https://www.themuse.com/api/public/jobs",
                params={"category": "Engineering", "level": "Entry Level,Mid Level,Senior Level", "page": 0},
            ).json()
            jobs = []
            for i in data.get("results", [])[:limit]:
                locs = [loc.get("name", "") for loc in i.get("locations", [])]
                location = ", ".join(locs) or "Remote"
                jobs.append({
                    "title": i.get("name", ""),
                    "company_name": (i.get("company", {}) or {}).get("name", "Unknown"),
                    "location": location,
                    "is_remote": any("remote" in loc.lower() for loc in locs) or is_remote(location, i.get("name", "")),
                    "apply_url": (i.get("refs", {}) or {}).get("landing_page", ""),
                    "description": clean_html(i.get("contents", ""))[:5000],
                    "source_board": "themuse",
                    "posted_at": i.get("publication_date"),
                })
            return jobs
        except Exception as e:
            print(f"The Muse error: {e}")
            return []


class WorkingNomadsScraper:
    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            data = client.get(
                "https://www.workingnomads.com/api/exposed_jobs/",
                params={"category": "development"},
            ).json()
            return [
                {
                    "title": i.get("title", ""),
                    "company_name": i.get("company_name", "Unknown"),
                    "location": i.get("region", "Worldwide"),
                    "is_remote": True,
                    "apply_url": i.get("url", ""),
                    "description": clean_html(i.get("description", ""))[:5000],
                    "source_board": "workingnomads",
                    "posted_at": i.get("pub_date"),
                }
                for i in data[:limit]
            ]
        except Exception as e:
            print(f"WorkingNomads error: {e}")
            return []


class WFHioScraper:
    def get_jobs(self, limit: int = 60) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            jobs, page = [], 1
            while len(jobs) < limit:
                data = client.get("https://wfh.io/api/v2/jobs.json", params={"page": page}).json()
                items = data if isinstance(data, list) else data.get("jobs", [])
                if not items:
                    break
                for i in items:
                    company = i.get("company", {}) or {}
                    jobs.append({
                        "title": i.get("title", ""),
                        "company_name": company.get("name", "Unknown") if isinstance(company, dict) else str(company),
                        "location": "Remote",
                        "is_remote": True,
                        "apply_url": i.get("url", "") or i.get("apply_url", ""),
                        "description": clean_html(i.get("description", ""))[:5000],
                        "source_board": "wfhio",
                        "posted_at": i.get("created_at"),
                    })
                if len(items) < 30:
                    break
                page += 1
            return jobs[:limit]
        except Exception as e:
            print(f"WFH.io error: {e}")
            return []


class DevITJobsScraper:
    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            data = client.get("https://devitjobs.eu/api/JobOffers/short").json()
            jobs = []
            for i in (data if isinstance(data, list) else data.get("data", []))[:limit]:
                sal_min = i.get("salaryFrom") or i.get("salary_min")
                sal_max = i.get("salaryTo") or i.get("salary_max")
                location = i.get("location") or i.get("city") or "EU Remote"
                jobs.append({
                    "title": i.get("title", i.get("position", "")),
                    "company_name": i.get("company", i.get("companyName", "Unknown")),
                    "location": str(location),
                    "is_remote": i.get("remote", False) or is_remote(str(location), i.get("title", "")),
                    "apply_url": i.get("url", i.get("applyUrl", "")),
                    "description": clean_html(i.get("description", ""))[:5000],
                    "source_board": "devitjobs",
                    "salary_min": int(sal_min) if sal_min else None,
                    "salary_max": int(sal_max) if sal_max else None,
                    "posted_at": i.get("publishedAt") or i.get("created_at"),
                })
            return jobs
        except Exception as e:
            print(f"DevITjobs error: {e}")
            return []


class JustJoinScraper:
    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            data = client.get("https://justjoin.it/api/offers", params={"remote": "true"}).json()
            jobs = []
            for i in (data if isinstance(data, list) else [])[:limit]:
                salary = (i.get("employmentTypes") or [{}])[0] if i.get("employmentTypes") else {}
                sal_from = salary.get("fromPln") or salary.get("from")
                sal_to = salary.get("toPln") or salary.get("to")
                jobs.append({
                    "title": i.get("title", ""),
                    "company_name": i.get("companyName", "Unknown"),
                    "location": i.get("city", "Remote") if not i.get("fullyRemote") else "Remote",
                    "is_remote": i.get("fullyRemote", False) or i.get("remoteInterview", False),
                    "apply_url": f"https://justjoin.it/offers/{i.get('id', '')}",
                    "description": clean_html(i.get("body", ""))[:5000],
                    "source_board": "justjoin",
                    "salary_min": int(sal_from * 0.25) if sal_from else None,
                    "salary_max": int(sal_to * 0.25) if sal_to else None,
                    "posted_at": i.get("publishedAt"),
                })
            return jobs
        except Exception as e:
            print(f"JustJoin error: {e}")
            return []


class FourDayWeekScraper:
    def get_jobs(self) -> List[Dict]:
        from job_scout.scraping.boards._rss import parse_rss_feed
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            resp = client.get("https://4dayweek.io/api/jobs", params={"format": "json"})
            if resp.status_code == 200:
                data = resp.json()
                return [
                    {
                        "title": i.get("title", i.get("role", "")),
                        "company_name": (i.get("company", {}) or {}).get("name", "Unknown") if isinstance(i.get("company"), dict) else str(i.get("company", "Unknown")),
                        "location": i.get("location", "Remote"),
                        "is_remote": True,
                        "apply_url": i.get("url", i.get("apply_url", "")),
                        "description": clean_html(i.get("description", ""))[:5000],
                        "source_board": "4dayweek",
                        "posted_at": i.get("published_at") or i.get("created_at"),
                    }
                    for i in (data if isinstance(data, list) else data.get("jobs", []))
                ]
        except Exception:
            pass
        return parse_rss_feed("https://4dayweek.io/remote-jobs.rss", "4dayweek")


class CryptoJobsListScraper:
    def get_jobs(self, limit: int = 60) -> List[Dict]:
        from job_scout.scraping.boards._rss import parse_rss_feed
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0", "Accept": "application/json"})
            resp = client.get("https://cryptojobslist.com/api/jobs")
            if resp.status_code == 200:
                data = resp.json()
                return [
                    {
                        "title": i.get("title", i.get("role", "")),
                        "company_name": i.get("company", "Unknown"),
                        "location": i.get("location", "Remote"),
                        "is_remote": True,
                        "apply_url": i.get("url", i.get("apply_url", "")),
                        "description": clean_html(i.get("description", ""))[:5000],
                        "source_board": "cryptojobslist",
                        "posted_at": i.get("created_at"),
                    }
                    for i in (data if isinstance(data, list) else data.get("jobs", []))[:limit]
                ]
        except Exception:
            pass
        return parse_rss_feed("https://cryptojobslist.com/remote.rss", "cryptojobslist", limit)


class ClimateBaseScraper:
    def get_jobs(self, limit: int = 60) -> List[Dict]:
        from job_scout.scraping.boards._rss import parse_rss_feed
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0", "Accept": "application/json"})
            resp = client.get("https://climatebase.org/api/jobs", params={"remote": "true", "limit": limit})
            if resp.status_code == 200:
                data = resp.json()
                return [
                    {
                        "title": i.get("title", i.get("role", "")),
                        "company_name": (i.get("organization", {}) or {}).get("name", i.get("company", "Unknown")),
                        "location": i.get("location", "Remote"),
                        "is_remote": i.get("remote", True),
                        "apply_url": i.get("url", i.get("apply_url", "")),
                        "description": clean_html(i.get("description", ""))[:5000],
                        "source_board": "climatebase",
                        "posted_at": i.get("created_at") or i.get("published_at"),
                    }
                    for i in (data if isinstance(data, list) else data.get("results", data.get("jobs", [])))[:limit]
                ]
        except Exception:
            pass
        return parse_rss_feed("https://climatebase.org/jobs.rss", "climatebase", limit)


class RemoteFirstJobsScraper:
    def get_jobs(self) -> List[Dict]:
        from job_scout.scraping.boards._rss import parse_rss_feed
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            resp = client.get("https://remotefirstjobs.com/api/jobs")
            if resp.status_code == 200:
                data = resp.json()
                return [
                    {
                        "title": i.get("title", ""),
                        "company_name": i.get("company", "Unknown"),
                        "location": "Remote",
                        "is_remote": True,
                        "apply_url": i.get("url", ""),
                        "description": clean_html(i.get("description", ""))[:5000],
                        "source_board": "remotefirstjobs",
                        "posted_at": i.get("created_at"),
                    }
                    for i in (data if isinstance(data, list) else data.get("jobs", []))
                ]
        except Exception:
            pass
        return parse_rss_feed("https://remotefirstjobs.com/feed/", "remotefirstjobs")


class Web3CareerScraper:
    def get_jobs(self):
        from job_scout.scraping.boards._rss import parse_rss_feed
        return parse_rss_feed("https://web3.career/remote-jobs-rss", "web3career")


class RemotiveDevOpsScraper:
    def get_jobs(self): return RemotiveScraper().get_jobs(category="devops-sysadmin", limit=100)

class RemotiveDataScraper:
    def get_jobs(self): return RemotiveScraper().get_jobs(category="data", limit=100)

class WorkingNomadsDevOpsScraper:
    def get_jobs(self):
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            r = client.get("https://www.workingnomads.com/api/exposed_jobs/", params={"category": "devops-sysadmin"})
            r.raise_for_status()
            return [{
                "title": i.get("title", ""),
                "company_name": i.get("company_name", "Unknown"),
                "location": i.get("region", "Worldwide"),
                "is_remote": True,
                "apply_url": i.get("url", ""),
                "description": clean_html(i.get("description", ""))[:5000],
                "source_board": "workingnomads",
                "posted_at": i.get("pub_date"),
            } for i in r.json()[:80]]
        except Exception as e:
            print(f"WorkingNomads DevOps error: {e}")
            return []

class JobicyAllScraper:
    def get_jobs(self):
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            resp = client.get("https://jobicy.com/api/v0/remote-jobs", params={"count": 50, "geo": "worldwide"})
            resp.raise_for_status()
            return [{
                "title": i.get("jobTitle", ""),
                "company_name": i.get("companyName", "Unknown"),
                "location": i.get("jobGeo", "Worldwide"),
                "is_remote": True,
                "apply_url": i.get("url", ""),
                "description": clean_html(i.get("jobDescription", ""))[:5000],
                "source_board": "jobicy",
                "salary": i.get("annualSalaryMin"),
                "posted_at": i.get("pubDate"),
            } for i in resp.json().get("jobs", [])]
        except Exception as e:
            print(f"Jobicy all error: {e}")
            return []
