# job_scout/scraping/boards/_extra.py
"""Extra board scrapers added after the notes2.txt audit.

Tier 1 (EASY)   — known RSS feeds or documented JSON endpoints.
Tier 2 (MEDIUM) — probable RSS/feed URLs against sites without an official API.

Every scraper exposes `get_jobs() -> List[Dict]` and never raises:
network errors are swallowed by `parse_rss_feed` / the local try/except
and surface as an empty list with a single log line. This matches the
contract used by `_orchestrator._all_boards_registry`.
"""

import httpx
from typing import List, Dict
from job_scout.scraping.base import clean_html
from job_scout.scraping.boards._rss import parse_rss_feed


# =====================================================================
# Tier 1 — EASY: official RSS feeds & documented JSON APIs
# =====================================================================

class PythonOrgJobsScraper:
    """python.org/jobs — official RSS."""
    def get_jobs(self):
        return parse_rss_feed("https://www.python.org/jobs/feed/rss/", "python_jobs")


class BerlinStartupJobsScraper:
    """berlinstartupjobs.com — official WordPress RSS."""
    def get_jobs(self):
        return parse_rss_feed("https://berlinstartupjobs.com/feed/", "berlin_startup_jobs")


class SkipTheDriveScraper:
    """skipthedrive.com — site-wide WordPress RSS."""
    def get_jobs(self):
        return parse_rss_feed("https://www.skipthedrive.com/feed/", "skipthedrive")


class PyJobsScraper:
    """PyJobs — community Python board, try both .com and .org RSS."""
    def get_jobs(self):
        for url in ("https://www.pyjobs.com/rss", "https://pyjobs.org/feed"):
            jobs = parse_rss_feed(url, "pyjobs")
            if jobs:
                return jobs
        return []


class HiringCafeScraper:
    """hiring.cafe — unofficial JSON search endpoint (POST-based)."""
    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(
                timeout=30,
                headers={
                    "User-Agent": "JobScout/1.0",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            resp = client.post(
                "https://hiring.cafe/api/search-jobs",
                json={"size": limit, "searchState": {"workplaceTypes": ["Remote"]}},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            items = data.get("results") or data.get("jobs") or data.get("hits") or []
            jobs = []
            for i in items[:limit]:
                company = i.get("company")
                company_name = (
                    company.get("name") if isinstance(company, dict)
                    else (i.get("companyName") or i.get("company_name") or "Unknown")
                )
                jobs.append({
                    "title": i.get("title", i.get("role", "")),
                    "company_name": company_name or "Unknown",
                    "location": i.get("location", "Remote"),
                    "is_remote": True,
                    "apply_url": i.get("apply_url") or i.get("url", ""),
                    "description": clean_html(i.get("description", ""))[:5000],
                    "source_board": "hiring_cafe",
                    "posted_at": i.get("created_at") or i.get("posted_at"),
                })
            return jobs
        except Exception as e:
            print(f"Hiring.cafe error: {e}")
            return []


class EchoJobsScraper:
    """echojobs.io — Supabase-backed aggregator; falls back to RSS."""
    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(
                timeout=30,
                headers={"User-Agent": "JobScout/1.0", "Accept": "application/json"},
            )
            resp = client.get("https://echojobs.io/api/jobs", params={"limit": limit})
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("jobs", data.get("data", []))
                return [
                    {
                        "title": i.get("title", ""),
                        "company_name": i.get("company", i.get("company_name", "Unknown")),
                        "location": i.get("location", "Remote"),
                        "is_remote": i.get("remote", True),
                        "apply_url": i.get("url") or i.get("apply_url", ""),
                        "description": clean_html(i.get("description", ""))[:5000],
                        "source_board": "echojobs",
                        "salary_min": i.get("salary_min"),
                        "salary_max": i.get("salary_max"),
                        "posted_at": i.get("created_at"),
                    }
                    for i in items[:limit]
                ]
        except Exception:
            pass
        return parse_rss_feed("https://echojobs.io/rss", "echojobs", limit)


class LandingJobsScraper:
    """landing.jobs — public listings JSON used by their own frontend."""
    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(
                timeout=30,
                headers={"User-Agent": "JobScout/1.0", "Accept": "application/json"},
            )
            resp = client.get(
                "https://landing.jobs/jobs.json",
                params={"remote": "true", "limit": limit},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            items = data if isinstance(data, list) else data.get("jobs", data.get("data", []))
            jobs = []
            for i in items[:limit]:
                company = i.get("company")
                company_name = (
                    company.get("name") if isinstance(company, dict)
                    else str(i.get("company", "Unknown"))
                )
                jobs.append({
                    "title": i.get("title", ""),
                    "company_name": company_name or "Unknown",
                    "location": "Remote" if i.get("remote") else i.get("city", "EU"),
                    "is_remote": bool(i.get("remote", False)),
                    "apply_url": i.get("apply_url") or f"https://landing.jobs/jobs/{i.get('id', '')}",
                    "description": clean_html(i.get("description", ""))[:5000],
                    "source_board": "landing_jobs",
                    "salary_min": i.get("gross_salary_low"),
                    "salary_max": i.get("gross_salary_high"),
                    "posted_at": i.get("published_at"),
                })
            return jobs
        except Exception as e:
            print(f"Landing.jobs error: {e}")
            return []


# =====================================================================
# Tier 2 — MEDIUM: probable RSS/feed URLs (one-liners on parse_rss_feed)
# If a URL turns out to be wrong, the call returns [] and prints once.
# Verify any zero-job boards by visiting the site and finding its feed.
# =====================================================================

class TheHubScraper:
    def get_jobs(self): return parse_rss_feed("https://thehub.io/jobs/rss", "the_hub")

class StartupJobsCZScraper:
    def get_jobs(self): return parse_rss_feed("https://www.startupjobs.com/rss", "startupjobs_cz")

class GermanTechJobsScraper:
    def get_jobs(self): return parse_rss_feed("https://germantechjobs.de/feed.xml", "germantechjobs")

class SwissDevJobsScraper:
    def get_jobs(self): return parse_rss_feed("https://swissdevjobs.ch/rss", "swissdevjobs")

class RelocateMeScraper:
    """Relocation/visa-sponsoring jobs — high value for non-EU/US candidates."""
    def get_jobs(self): return parse_rss_feed("https://relocate.me/jobs.rss", "relocate_me")

class CryptocurrencyJobsCoScraper:
    """Different site from cryptojobslist.com (already integrated)."""
    def get_jobs(self): return parse_rss_feed("https://cryptocurrencyjobs.co/rss/", "cryptocurrencyjobs_co")

class DiversifyTechScraper:
    def get_jobs(self): return parse_rss_feed("https://www.diversifytech.com/jobs.rss", "diversify_tech")

class StartupSuchtScraper:
    def get_jobs(self): return parse_rss_feed("https://www.startup-sucht.com/feed", "startup_sucht")

class JustRemoteScraper:
    def get_jobs(self): return parse_rss_feed("https://justremote.co/rss", "justremote")

class DailyRemoteScraper:
    def get_jobs(self): return parse_rss_feed("https://dailyremote.com/feed/all", "dailyremote")

class RemoteYeahScraper:
    def get_jobs(self): return parse_rss_feed("https://remoteyeah.com/rss", "remoteyeah")

class RemoteBackendJobsScraper:
    def get_jobs(self): return parse_rss_feed("https://remotebackendjobs.com/feed", "remote_backend_jobs")

class RemoteFrontendJobsScraper:
    def get_jobs(self): return parse_rss_feed("https://remotefrontendjobs.com/feed", "remote_frontend_jobs")

class RealWorkFromAnywhereScraper:
    """Strictly worldwide-remote — matches the "no India-restricted" filter well."""
    def get_jobs(self): return parse_rss_feed("https://www.realworkfromanywhere.com/feed", "realworkfromanywhere")

class RemoteesScraper:
    def get_jobs(self): return parse_rss_feed("https://remotees.com/feed", "remotees")

class OSSJobsScraper:
    def get_jobs(self): return parse_rss_feed("https://ossjobs.dev/feed", "ossjobs")

class JSPythonGoRemotelyScraper:
    """JS Remotely + Python Remotely + Go Remotely share one template."""
    def get_jobs(self):
        jobs = []
        for stack, url in (
            ("js",     "https://jsremotely.com/rss"),
            ("python", "https://pythonremotely.com/rss"),
            ("go",     "https://goremotely.net/rss"),
        ):
            jobs.extend(parse_rss_feed(url, f"{stack}_remotely"))
        return jobs

class BuiltInScraper:
    def get_jobs(self): return parse_rss_feed("https://builtin.com/jobs/remote/feed", "builtin")

class Remote100kScraper:
    def get_jobs(self): return parse_rss_feed("https://remote100k.com/feed", "remote100k")

class TechHireScraper:
    def get_jobs(self): return parse_rss_feed("https://techhire.ai/feed", "techhire")

class JobanniScraper:
    def get_jobs(self): return parse_rss_feed("https://jobanni.com/feed", "jobanni")

class FindJobsDevScraper:
    def get_jobs(self): return parse_rss_feed("https://findjobs.dev/rss", "findjobs_dev")

class DevJobsProScraper:
    def get_jobs(self): return parse_rss_feed("https://devjobs.pro/feed", "devjobs_pro")

class OneRemoteJobsScraper:
    def get_jobs(self): return parse_rss_feed("https://oneremotejobs.com/feed", "oneremotejobs")

class JobsRemoteAIScraper:
    def get_jobs(self): return parse_rss_feed("https://jobsremote.ai/feed", "jobsremote_ai")

class SlasifyScraper:
    def get_jobs(self): return parse_rss_feed("https://slasify.com/jobs/rss", "slasify")

class PangianScraper:
    def get_jobs(self): return parse_rss_feed("https://pangian.com/job-types/remote-job/feed/", "pangian")
