# worker/scraping/board_scrapers.py
"""
Job Board Scrapers — RemoteOK, Remotive, WWR, HN, Reddit, Himalayas, etc.
All FREE. All return actual job listings (not just companies).
"""

import httpx
import re
import html
import time
import json
import os
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from datetime import datetime, date

# ---------------------------------------------------------------------------
# Board Manager config reader
# ---------------------------------------------------------------------------

_BOARDS_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "boards_config.json",
)


# Boards that are on by default (matches default_on=True in 6_Boards.py ALL_BOARDS)
_DEFAULT_BOARDS = {
    "remoteok", "remotive", "weworkremotely", "himalayas", "arbeitnow", "themuse",
    "justjoin", "hackernews", "hackernews_jobs", "jobicy", "jobicy_all",
    "workingnomads", "jobspresso", "wfhio", "remoteco", "authenticjobs", "nodesk",
    "4dayweek", "dynamitejobs", "freshremote", "remotefirstjobs", "devitjobs",
    "djangojobs", "golangjobs", "cord", "wellfound", "hired", "talentio", "pallet",
}


def _get_enabled_boards(all_keys: list) -> list:
    """Return board keys filtered by boards_config.json. Falls back to default_on boards."""
    try:
        with open(_BOARDS_CONFIG_FILE) as f:
            cfg = json.load(f)
        enabled = cfg.get("enabled_boards")
        if enabled:
            return [k for k in enabled if k in all_keys]
    except Exception:
        pass
    # No config yet — return only default-on boards
    return [k for k in all_keys if k in _DEFAULT_BOARDS]


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

def _clean_html(text: str) -> str:
    """Strip HTML tags, decode entities, normalize whitespace."""
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_remote(location: str, title: str, description: str = "") -> bool:
    text = f"{location} {title} {description}".lower()
    return any(kw in text for kw in [
        "remote", "worldwide", "anywhere", "work from home",
        "distributed", "wfh", "fully remote",
    ])


def _today() -> str:
    return date.today().isoformat()


def _now() -> str:
    return datetime.now().isoformat()


def to_db_job(job: Dict, company_id: Optional[str] = None) -> Dict:
    """Convert a scraped job to the DB jobs table format."""
    from worker.scraping.dedup import generate_job_fingerprint

    title = job.get("title", "")[:500]
    company_name = job.get("company_name", "")
    fingerprint = generate_job_fingerprint(title, company_name) if company_name else None

    # Normalize salary: some boards return salary_min/max, others return salary (text)
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")
    # Jobicy returns annualSalaryMin as "salary" field — promote it
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
        "discovered_date": _today(),
        "discovered_at": _now(),
    }


# ---------------------------------------------------------------------------
# RemoteOK — JSON API, no auth
# ---------------------------------------------------------------------------

class RemoteOKScraper:
    """https://remoteok.com/api — returns ~100 recent remote jobs."""

    def get_jobs(self) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            response = client.get("https://remoteok.com/api")
            response.raise_for_status()
            data = response.json()

            jobs = []
            for item in data:
                # First item is metadata, skip
                if not item.get("position"):
                    continue
                jobs.append({
                    "title": item.get("position", ""),
                    "company_name": item.get("company", "Unknown"),
                    "location": item.get("location", "Remote"),
                    "is_remote": True,  # It's RemoteOK — all remote
                    "apply_url": item.get("apply_url") or item.get("url", ""),
                    "description": _clean_html(item.get("description", ""))[:5000],
                    "source_board": "remoteok",
                    "salary_min": item.get("salary_min"),
                    "salary_max": item.get("salary_max"),
                    "tags": item.get("tags", []),
                    "posted_at": item.get("date"),
                })
            return jobs
        except Exception as e:
            print(f"RemoteOK error: {e}")
            return []


# ---------------------------------------------------------------------------
# Remotive — JSON API, no auth
# ---------------------------------------------------------------------------

class RemotiveScraper:
    """https://remotive.com/api/remote-jobs — free remote job API."""

    def get_jobs(self, category: str = None, limit: int = 200) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            params = {"limit": limit}
            if category:
                params["category"] = category  # software-dev, devops, data, etc.
            response = client.get("https://remotive.com/api/remote-jobs", params=params)
            response.raise_for_status()
            data = response.json()

            jobs = []
            for item in data.get("jobs", []):
                jobs.append({
                    "title": item.get("title", ""),
                    "company_name": item.get("company_name", "Unknown"),
                    "location": item.get("candidate_required_location", "Worldwide"),
                    "is_remote": True,
                    "apply_url": item.get("url", ""),
                    "description": _clean_html(item.get("description", ""))[:5000],
                    "source_board": "remotive",
                    "salary": item.get("salary", ""),
                    "tags": item.get("tags", []),
                    "posted_at": item.get("publication_date"),
                    "job_type": item.get("job_type", ""),
                })
            return jobs
        except Exception as e:
            print(f"Remotive error: {e}")
            return []


# ---------------------------------------------------------------------------
# WeWorkRemotely — RSS feed
# ---------------------------------------------------------------------------

class WeWorkRemotelyScraper:
    """RSS feed from weworkremotely.com — programming + devops categories."""

    FEEDS = [
        "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
        "https://weworkremotely.com/remote-jobs.rss",
    ]

    def get_jobs(self) -> List[Dict]:
        client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
        seen_urls = set()
        jobs = []

        for feed_url in self.FEEDS:
            try:
                response = client.get(feed_url)
                if response.status_code != 200:
                    continue
                root = ET.fromstring(response.content)

                for item in root.findall(".//item"):
                    title_el = item.find("title")
                    link_el = item.find("link")
                    desc_el = item.find("description")

                    if title_el is None or link_el is None:
                        continue

                    url = link_el.text.strip() if link_el.text else ""
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    raw_title = title_el.text or ""
                    description = _clean_html(desc_el.text if desc_el is not None and desc_el.text else "")

                    # Title format: "Company: Job Title"
                    if ":" in raw_title:
                        company_name, job_title = raw_title.split(":", 1)
                    else:
                        company_name, job_title = "Unknown", raw_title

                    jobs.append({
                        "title": job_title.strip(),
                        "company_name": company_name.strip(),
                        "location": "Remote",
                        "is_remote": True,
                        "apply_url": url,
                        "description": description[:5000],
                        "source_board": "weworkremotely",
                        "posted_at": None,
                    })

            except Exception as e:
                print(f"WWR feed error ({feed_url}): {e}")

        return jobs


# ---------------------------------------------------------------------------
# Hacker News Who's Hiring — Algolia API + Firebase API
# ---------------------------------------------------------------------------

class HackerNewsScraper:
    """
    Scrapes the monthly "Ask HN: Who is hiring?" threads.
    Each top-level comment is a job posting.
    Also scrapes HN's dedicated job stories feed.
    """

    def get_jobs(self, months: int = 2) -> List[Dict]:
        """Get jobs from the latest N months of Who is Hiring threads + job stories."""
        jobs = []
        jobs.extend(self._scrape_who_is_hiring(months))
        jobs.extend(self._scrape_job_stories())
        return jobs

    def _scrape_who_is_hiring(self, months: int) -> List[Dict]:
        """Parse top-level comments from Who is Hiring threads."""
        client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
        jobs = []

        try:
            # Find recent threads
            response = client.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={
                    "query": '"who is hiring"',
                    "tags": "ask_hn",
                    "hitsPerPage": months,
                },
            )
            response.raise_for_status()
            threads = response.json().get("hits", [])

            for thread in threads:
                title = thread.get("title", "")
                if "who is hiring" not in title.lower():
                    continue

                thread_id = thread.get("objectID")
                if not thread_id:
                    continue

                # Get all top-level comments (each is a job post)
                try:
                    item_resp = client.get(
                        f"https://hn.algolia.com/api/v1/items/{thread_id}"
                    )
                    item_resp.raise_for_status()
                    item = item_resp.json()

                    for comment in item.get("children", []):
                        text = comment.get("text", "")
                        if not text or len(text) < 50:
                            continue

                        parsed = self._parse_hn_comment(text, thread_id)
                        if parsed:
                            jobs.append(parsed)

                except Exception as e:
                    print(f"HN thread {thread_id} error: {e}")

                time.sleep(0.5)  # Rate limit

        except Exception as e:
            print(f"HN Algolia error: {e}")

        return jobs

    def _scrape_job_stories(self) -> List[Dict]:
        """Scrape HN's dedicated /jobstories feed (YC companies)."""
        client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
        jobs = []

        try:
            response = client.get("https://hacker-news.firebaseio.com/v0/jobstories.json")
            response.raise_for_status()
            story_ids = response.json()[:50]  # Latest 50

            for story_id in story_ids:
                try:
                    r = client.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
                    r.raise_for_status()
                    item = r.json()

                    title = item.get("title", "")
                    url = item.get("url", "")
                    text = _clean_html(item.get("text", ""))

                    # Parse "Company (YC XX) is hiring Title"
                    company_name, job_title = self._parse_hn_job_title(title)

                    jobs.append({
                        "title": job_title,
                        "company_name": company_name,
                        "location": "Remote" if _is_remote("", title, text) else "Unknown",
                        "is_remote": _is_remote("", title, text),
                        "apply_url": url or f"https://news.ycombinator.com/item?id={story_id}",
                        "description": text[:5000] if text else title,
                        "source_board": "hackernews_jobs",
                        "posted_at": None,
                    })

                    time.sleep(0.1)
                except Exception:
                    continue

        except Exception as e:
            print(f"HN job stories error: {e}")

        return jobs

    def _parse_hn_comment(self, text: str, thread_id: str) -> Optional[Dict]:
        """Parse a Who is Hiring comment into a job dict."""
        clean = _clean_html(text)
        lines = [l.strip() for l in clean.split("\n") if l.strip()]

        if not lines:
            return None

        first_line = lines[0]

        # Common format: "Company | Title | Location | Remote | ..."
        parts = [p.strip() for p in first_line.split("|")]

        company_name = parts[0] if parts else "Unknown"
        job_title = parts[1] if len(parts) > 1 else first_line
        location = ""
        is_remote = False

        for part in parts:
            pl = part.lower()
            if any(kw in pl for kw in ["remote", "worldwide", "anywhere"]):
                is_remote = True
            if any(kw in pl for kw in ["remote", "sf", "nyc", "london", "berlin", "worldwide", "us", "eu", "uk"]):
                location = part.strip()

        # Find apply URL in text
        url_match = re.search(r'https?://[^\s<"]+', text)
        apply_url = url_match.group(0) if url_match else f"https://news.ycombinator.com/item?id={thread_id}"

        return {
            "title": job_title[:200],
            "company_name": company_name[:200],
            "location": location or ("Remote" if is_remote else "Unknown"),
            "is_remote": is_remote or _is_remote("", first_line, clean),
            "apply_url": apply_url,
            "description": clean[:5000],
            "source_board": "hackernews",
            "posted_at": None,
        }

    def _parse_hn_job_title(self, title: str) -> tuple:
        """Parse HN job story title like 'Company (YC XX) Is Hiring Engineers'."""
        # Pattern: "Company (YC XX) is hiring Title"
        m = re.match(r"^(.+?)\s*(?:\(YC\s*\w+\))?\s*(?:is hiring|hiring|–|-)\s*(.+)$", title, re.IGNORECASE)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return title, title


# ---------------------------------------------------------------------------
# Reddit Job Scraper — public JSON API, no auth needed
# ---------------------------------------------------------------------------

class RedditScraper:
    """Scrape job posts from Reddit hiring subreddits."""

    SUBREDDITS = [
        "forhire",        # [Hiring] posts
        "remotejs",       # Remote JS/dev jobs
    ]

    def get_jobs(self, limit_per_sub: int = 50) -> List[Dict]:
        client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0 (job search bot)"})
        jobs = []

        for sub in self.SUBREDDITS:
            try:
                response = client.get(
                    f"https://old.reddit.com/r/{sub}/new.json",
                    params={"limit": limit_per_sub},
                )
                if response.status_code != 200:
                    print(f"Reddit r/{sub}: {response.status_code}")
                    continue

                data = response.json()
                posts = data.get("data", {}).get("children", [])

                for post in posts:
                    pd = post.get("data", {})
                    title = pd.get("title", "")

                    # Only [Hiring] posts
                    if sub == "forhire" and "[hiring]" not in title.lower():
                        continue

                    # Parse title
                    company, job_title = self._parse_reddit_title(title)

                    jobs.append({
                        "title": job_title,
                        "company_name": company,
                        "location": "Remote" if _is_remote("", title, pd.get("selftext", "")) else "Unknown",
                        "is_remote": _is_remote("", title, pd.get("selftext", "")),
                        "apply_url": pd.get("url", ""),
                        "description": (pd.get("selftext", "") or "")[:5000],
                        "source_board": f"reddit_{sub}",
                        "posted_at": None,
                    })

                time.sleep(1)  # Reddit rate limit

            except Exception as e:
                print(f"Reddit r/{sub} error: {e}")

        return jobs

    def _parse_reddit_title(self, title: str) -> tuple:
        """Parse Reddit post title to extract company and job title."""
        # Remove [Hiring], [For Hire], etc.
        clean = re.sub(r"\[.*?\]", "", title).strip()
        # Common format: "Company - Job Title" or "Job Title at Company"
        if " - " in clean:
            parts = clean.split(" - ", 1)
            return parts[0].strip(), parts[1].strip()
        if " at " in clean.lower():
            m = re.match(r"(.+?)\s+at\s+(.+)", clean, re.IGNORECASE)
            if m:
                return m.group(2).strip(), m.group(1).strip()
        return "Unknown", clean


# ---------------------------------------------------------------------------
# Himalayas — JSON API
# ---------------------------------------------------------------------------

class HimalayasScraper:
    """https://himalayas.app/jobs/api — remote jobs API."""

    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            response = client.get(
                "https://himalayas.app/jobs/api",
                params={"limit": limit},
            )
            response.raise_for_status()
            data = response.json()

            jobs = []
            for item in data.get("jobs", []):
                location = ", ".join(item.get("locationRestrictions", [])) or "Worldwide"
                jobs.append({
                    "title": item.get("title", ""),
                    "company_name": item.get("companyName", "Unknown"),
                    "location": location,
                    "is_remote": True,  # Himalayas is remote-only
                    "apply_url": item.get("applicationLink") or item.get("guid", ""),
                    "description": _clean_html(item.get("description", ""))[:5000],
                    "source_board": "himalayas",
                    "salary_min": item.get("minSalary"),
                    "salary_max": item.get("maxSalary"),
                    "seniority": item.get("seniority", ""),
                    "posted_at": item.get("pubDate"),
                })
            return jobs
        except Exception as e:
            print(f"Himalayas error: {e}")
            return []


# ---------------------------------------------------------------------------
# HN Jobs (Firebase) — YC startup dedicated job posts
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Arbeitnow — free REST API, strong EU + worldwide remote coverage
# ---------------------------------------------------------------------------

class ArbeitnowScraper:
    """https://arbeitnow.com/api/job-board-api — free, no auth, EU+remote focus."""

    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            response = client.get("https://arbeitnow.com/api/job-board-api")
            response.raise_for_status()
            data = response.json()

            jobs = []
            for item in data.get("data", [])[:limit]:
                tags = item.get("tags", [])
                is_remote = item.get("remote", False) or _is_remote(
                    item.get("location", ""), item.get("title", "")
                )
                jobs.append({
                    "title": item.get("title", ""),
                    "company_name": item.get("company_name", "Unknown"),
                    "location": item.get("location", "Remote"),
                    "is_remote": is_remote,
                    "apply_url": item.get("url", ""),
                    "description": _clean_html(item.get("description", ""))[:5000],
                    "source_board": "arbeitnow",
                    "tags": tags,
                    "posted_at": item.get("created_at"),
                })
            return jobs
        except Exception as e:
            print(f"Arbeitnow error: {e}")
            return []


# ---------------------------------------------------------------------------
# Jobicy — free API, small board = less competition
# ---------------------------------------------------------------------------

class JobicyScraper:
    """https://jobicy.com/api/v0/remote-jobs — free, remote-only."""

    def get_jobs(self, limit: int = 50) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            response = client.get(
                "https://jobicy.com/api/v0/remote-jobs",
                params={"count": limit, "geo": "worldwide", "industry": "engineering"},
            )
            response.raise_for_status()
            data = response.json()

            jobs = []
            for item in data.get("jobs", []):
                jobs.append({
                    "title": item.get("jobTitle", ""),
                    "company_name": item.get("companyName", "Unknown"),
                    "location": item.get("jobGeo", "Worldwide"),
                    "is_remote": True,
                    "apply_url": item.get("url", ""),
                    "description": _clean_html(item.get("jobDescription", ""))[:5000],
                    "source_board": "jobicy",
                    "salary": item.get("annualSalaryMin", ""),
                    "posted_at": item.get("pubDate"),
                })
            return jobs
        except Exception as e:
            print(f"Jobicy error: {e}")
            return []


# ---------------------------------------------------------------------------
# The Muse — free public API, startup + mid-size company focus
# ---------------------------------------------------------------------------

class TheMuseScraper:
    """https://www.themuse.com/api/public/jobs — free, startup/mid-size companies."""

    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            response = client.get(
                "https://www.themuse.com/api/public/jobs",
                params={
                    "category": "Engineering",
                    "level": "Entry Level,Mid Level,Senior Level",
                    "page": 0,
                },
            )
            response.raise_for_status()
            data = response.json()

            jobs = []
            for item in data.get("results", [])[:limit]:
                locations = item.get("locations", [])
                loc_names = [l.get("name", "") for l in locations]
                location = ", ".join(loc_names) or "Remote"
                is_remote = any("remote" in l.lower() for l in loc_names) or _is_remote(
                    location, item.get("name", "")
                )

                company = item.get("company", {})
                apply_url = item.get("refs", {}).get("landing_page", "")

                jobs.append({
                    "title": item.get("name", ""),
                    "company_name": company.get("name", "Unknown"),
                    "location": location,
                    "is_remote": is_remote,
                    "apply_url": apply_url,
                    "description": _clean_html(item.get("contents", ""))[:5000],
                    "source_board": "themuse",
                    "posted_at": item.get("publication_date"),
                })
            return jobs
        except Exception as e:
            print(f"The Muse error: {e}")
            return []


# ---------------------------------------------------------------------------
# WorkingNomads — free REST API, small board = less competition
# ---------------------------------------------------------------------------

class WorkingNomadsScraper:
    """https://www.workingnomads.com/api/exposed_jobs/ — free, remote-only."""

    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            response = client.get(
                "https://www.workingnomads.com/api/exposed_jobs/",
                params={"category": "development"},
            )
            response.raise_for_status()
            data = response.json()

            jobs = []
            for item in data[:limit]:
                jobs.append({
                    "title": item.get("title", ""),
                    "company_name": item.get("company_name", "Unknown"),
                    "location": item.get("region", "Worldwide"),
                    "is_remote": True,
                    "apply_url": item.get("url", ""),
                    "description": _clean_html(item.get("description", ""))[:5000],
                    "source_board": "workingnomads",
                    "posted_at": item.get("pub_date"),
                })
            return jobs
        except Exception as e:
            print(f"WorkingNomads error: {e}")
            return []


# ---------------------------------------------------------------------------
# Jobspresso — curated remote jobs RSS, small board, very low competition
# ---------------------------------------------------------------------------

class JobspressoScraper:
    """https://jobspresso.co — curated remote dev jobs, WordPress RSS feed."""

    def get_jobs(self, limit: int = 50) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            response = client.get("https://jobspresso.co/feed/?post_type=job_listing")
            response.raise_for_status()
            root = ET.fromstring(response.content)

            jobs = []
            for item in root.findall(".//item")[:limit]:
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")
                date_el = item.find("pubDate")

                if title_el is None or link_el is None:
                    continue

                raw_title = title_el.text or ""
                url = link_el.text.strip() if link_el.text else ""
                description = _clean_html(desc_el.text if desc_el is not None else "")

                # Title format is usually "Job Title at Company"
                company_name = "Unknown"
                job_title = raw_title
                if " at " in raw_title:
                    parts = raw_title.rsplit(" at ", 1)
                    job_title = parts[0].strip()
                    company_name = parts[1].strip()

                jobs.append({
                    "title": job_title[:200],
                    "company_name": company_name[:200],
                    "location": "Remote",
                    "is_remote": True,
                    "apply_url": url,
                    "description": description[:5000],
                    "source_board": "jobspresso",
                    "posted_at": date_el.text if date_el is not None else None,
                })
            return jobs
        except Exception as e:
            print(f"Jobspresso error: {e}")
            return []


# ---------------------------------------------------------------------------
# WFH.io — free JSON API, niche remote board, minimal competition
# ---------------------------------------------------------------------------

class WFHioScraper:
    """https://wfh.io/api/v2/jobs.json — free, no auth, niche remote board."""

    def get_jobs(self, limit: int = 60) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            jobs = []
            page = 1

            while len(jobs) < limit:
                response = client.get(
                    "https://wfh.io/api/v2/jobs.json",
                    params={"page": page},
                )
                response.raise_for_status()
                data = response.json()

                items = data if isinstance(data, list) else data.get("jobs", [])
                if not items:
                    break

                for item in items:
                    company = item.get("company", {}) or {}
                    jobs.append({
                        "title": item.get("title", ""),
                        "company_name": company.get("name", "Unknown") if isinstance(company, dict) else str(company),
                        "location": "Remote",
                        "is_remote": True,
                        "apply_url": item.get("url", "") or item.get("apply_url", ""),
                        "description": _clean_html(item.get("description", ""))[:5000],
                        "source_board": "wfhio",
                        "posted_at": item.get("created_at"),
                    })

                if len(items) < 30:  # Last page
                    break
                page += 1

            return jobs[:limit]
        except Exception as e:
            print(f"WFH.io error: {e}")
            return []


# ---------------------------------------------------------------------------
# Generic RSS/Atom Job Feed Parser
# ---------------------------------------------------------------------------

def _parse_rss_feed(feed_url: str, source_board: str, limit: int = 80) -> List[Dict]:
    """
    Parse any standard RSS 2.0 or Atom feed for job listings.
    Handles both RSS <item> and Atom <entry> formats.
    """
    NS_ATOM = "http://www.w3.org/2005/Atom"
    try:
        client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
        response = client.get(feed_url)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        # Support RSS <item> and Atom <entry>
        items = root.findall(".//item")
        if not items:
            items = root.findall(f".//{{{NS_ATOM}}}entry")

        jobs = []
        for item in items[:limit]:
            def _t(tag):
                el = item.find(tag) or item.find(f"{{{NS_ATOM}}}{tag}")
                return (el.text or "").strip() if el is not None else ""

            raw_title = _t("title")
            url = _t("link")
            # Atom <link href="...">
            if not url:
                link_el = item.find(f"{{{NS_ATOM}}}link")
                if link_el is not None:
                    url = link_el.get("href", "")
            desc = _clean_html(_t("description") or _t("summary") or _t("content"))

            # Parse "Job Title at Company" or "Job Title - Company"
            company = "Unknown"
            job_title = raw_title
            for sep in (" at ", " @ ", " | ", " — ", " – "):
                if sep in raw_title:
                    parts = raw_title.rsplit(sep, 1)
                    if len(parts) == 2 and parts[1].strip():
                        job_title = parts[0].strip()
                        company = parts[1].strip()
                        break

            jobs.append({
                "title": job_title[:200],
                "company_name": company[:200],
                "location": "Remote" if _is_remote("", raw_title, desc) else "Unknown",
                "is_remote": _is_remote("", raw_title, desc),
                "apply_url": url,
                "description": desc[:5000],
                "source_board": source_board,
                "posted_at": _t("pubDate") or _t("published") or _t("updated") or None,
            })
        return jobs
    except Exception as e:
        print(f"{source_board} RSS error ({feed_url}): {e}")
        return []


# ---------------------------------------------------------------------------
# Remote.co — curated remote-only board, RSS, smaller than RemoteOK
# ---------------------------------------------------------------------------
class RemoteCo:
    def get_jobs(self): return _parse_rss_feed("https://remote.co/remote-jobs/feed/", "remoteco")


# ---------------------------------------------------------------------------
# Authentic Jobs — web/dev/design jobs RSS (10+ years, indie/agency focused)
# ---------------------------------------------------------------------------
class AuthenticJobsScraper:
    def get_jobs(self): return _parse_rss_feed("https://authenticjobs.com/feed/", "authenticjobs")


# ---------------------------------------------------------------------------
# DjangoJobs.net — Python/Django specific, very niche, near-zero competition
# ---------------------------------------------------------------------------
class DjangoJobsScraper:
    def get_jobs(self): return _parse_rss_feed("https://djangojobs.net/jobs/feed/rss/", "djangojobs")


# ---------------------------------------------------------------------------
# LaraJobs.com — PHP/Laravel ecosystem, small companies, global remote
# ---------------------------------------------------------------------------
class LaraJobsScraper:
    def get_jobs(self): return _parse_rss_feed("https://larajobs.com/feed", "larajobs")


# ---------------------------------------------------------------------------
# NodeDesk — curated remote jobs (very small board, very low applicants)
# ---------------------------------------------------------------------------
class NodeDeskScraper:
    def get_jobs(self): return _parse_rss_feed("https://nodesk.co/remote-work/rss.xml", "nodesk")


# ---------------------------------------------------------------------------
# 4DayWeek.io — 4-day work week remote jobs, ultra-niche, tiny applicant pool
# ---------------------------------------------------------------------------
class FourDayWeekScraper:
    def get_jobs(self):
        # Try JSON API first, fall back to RSS
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            resp = client.get("https://4dayweek.io/api/jobs", params={"format": "json"})
            if resp.status_code == 200:
                data = resp.json()
                jobs = []
                for item in (data if isinstance(data, list) else data.get("jobs", [])):
                    jobs.append({
                        "title": item.get("title", item.get("role", "")),
                        "company_name": item.get("company", {}).get("name", "Unknown") if isinstance(item.get("company"), dict) else str(item.get("company", "Unknown")),
                        "location": item.get("location", "Remote"),
                        "is_remote": True,
                        "apply_url": item.get("url", item.get("apply_url", "")),
                        "description": _clean_html(item.get("description", ""))[:5000],
                        "source_board": "4dayweek",
                        "posted_at": item.get("published_at") or item.get("created_at"),
                    })
                return jobs
        except Exception:
            pass
        return _parse_rss_feed("https://4dayweek.io/remote-jobs.rss", "4dayweek")


# ---------------------------------------------------------------------------
# VueJobs.com — Vue.js developer jobs RSS
# ---------------------------------------------------------------------------
class VueJobsScraper:
    def get_jobs(self): return _parse_rss_feed("https://vuejobs.com/feed.atom", "vuejobs")


# ---------------------------------------------------------------------------
# GolangJobs.xyz — Go/Golang specific, niche, small applicant pool
# ---------------------------------------------------------------------------
class GolangJobsScraper:
    def get_jobs(self): return _parse_rss_feed("https://golangjobs.xyz/feed/", "golangjobs")


# ---------------------------------------------------------------------------
# Dynamite Jobs — location-independent remote jobs, entrepreneur-focused
# ---------------------------------------------------------------------------
class DynamiteJobsScraper:
    def get_jobs(self): return _parse_rss_feed("https://dynamitejobs.com/remote-jobs.rss", "dynamitejobs")


# ---------------------------------------------------------------------------
# Smashing Magazine Jobs — front-end/dev focused, small but high quality
# ---------------------------------------------------------------------------
class SmashingMagJobsScraper:
    def get_jobs(self): return _parse_rss_feed("https://jobs.smashingmagazine.com/jobs/rss", "smashingmag")


# ---------------------------------------------------------------------------
# DevITjobs.eu — free JSON API, EU developer jobs (many globally remote)
# ---------------------------------------------------------------------------
class DevITJobsScraper:
    """https://devitjobs.eu/api/JobOffers/short — no auth needed, EU tech jobs."""

    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            response = client.get("https://devitjobs.eu/api/JobOffers/short")
            response.raise_for_status()
            data = response.json()

            jobs = []
            for item in (data if isinstance(data, list) else data.get("data", []))[:limit]:
                salary_min = item.get("salaryFrom") or item.get("salary_min")
                salary_max = item.get("salaryTo") or item.get("salary_max")
                location = item.get("location") or item.get("city") or "EU Remote"
                is_remote = item.get("remote", False) or _is_remote(str(location), item.get("title", ""))
                jobs.append({
                    "title": item.get("title", item.get("position", "")),
                    "company_name": item.get("company", item.get("companyName", "Unknown")),
                    "location": str(location),
                    "is_remote": is_remote,
                    "apply_url": item.get("url", item.get("applyUrl", "")),
                    "description": _clean_html(item.get("description", ""))[:5000],
                    "source_board": "devitjobs",
                    "salary_min": int(salary_min) if salary_min else None,
                    "salary_max": int(salary_max) if salary_max else None,
                    "posted_at": item.get("publishedAt") or item.get("created_at"),
                })
            return jobs
        except Exception as e:
            print(f"DevITjobs error: {e}")
            return []


# ---------------------------------------------------------------------------
# CryptoJobsList — web3/blockchain startups, remote-first, small teams
# ---------------------------------------------------------------------------
class CryptoJobsListScraper:
    """https://cryptojobslist.com — blockchain startups, often small + remote + desperate."""

    def get_jobs(self, limit: int = 60) -> List[Dict]:
        # Try JSON API first
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0", "Accept": "application/json"})
            resp = client.get("https://cryptojobslist.com/api/jobs")
            if resp.status_code == 200:
                data = resp.json()
                jobs = []
                for item in (data if isinstance(data, list) else data.get("jobs", []))[:limit]:
                    jobs.append({
                        "title": item.get("title", item.get("role", "")),
                        "company_name": item.get("company", "Unknown"),
                        "location": item.get("location", "Remote"),
                        "is_remote": True,
                        "apply_url": item.get("url", item.get("apply_url", "")),
                        "description": _clean_html(item.get("description", ""))[:5000],
                        "source_board": "cryptojobslist",
                        "posted_at": item.get("created_at"),
                    })
                return jobs
        except Exception:
            pass
        return _parse_rss_feed("https://cryptojobslist.com/remote.rss", "cryptojobslist", limit)


# ---------------------------------------------------------------------------
# Web3.career — blockchain/crypto companies hiring engineers
# ---------------------------------------------------------------------------
class Web3CareerScraper:
    def get_jobs(self): return _parse_rss_feed("https://web3.career/remote-jobs-rss", "web3career")


# ---------------------------------------------------------------------------
# ClimateBase — climate tech startups, mission-driven, often remote + urgent
# ---------------------------------------------------------------------------
class ClimateBaseScraper:
    """https://climatebase.org — climate tech startups, remote, desperate to hire devs."""

    def get_jobs(self, limit: int = 60) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0", "Accept": "application/json"})
            resp = client.get(
                "https://climatebase.org/api/jobs",
                params={"remote": "true", "limit": limit},
            )
            if resp.status_code == 200:
                data = resp.json()
                jobs = []
                for item in (data if isinstance(data, list) else data.get("results", data.get("jobs", [])))[:limit]:
                    org = item.get("organization", {}) or {}
                    jobs.append({
                        "title": item.get("title", item.get("role", "")),
                        "company_name": org.get("name", item.get("company", "Unknown")),
                        "location": item.get("location", "Remote"),
                        "is_remote": item.get("remote", True),
                        "apply_url": item.get("url", item.get("apply_url", "")),
                        "description": _clean_html(item.get("description", ""))[:5000],
                        "source_board": "climatebase",
                        "posted_at": item.get("created_at") or item.get("published_at"),
                    })
                return jobs
        except Exception:
            pass
        return _parse_rss_feed("https://climatebase.org/jobs.rss", "climatebase", limit)


# ---------------------------------------------------------------------------
# JustJoin.it — Polish/EU tech jobs, many fully remote, large & active
# ---------------------------------------------------------------------------
class JustJoinScraper:
    """https://justjoin.it — biggest EU tech job board, many remote-friendly."""

    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            resp = client.get("https://justjoin.it/api/offers", params={"remote": "true"})
            resp.raise_for_status()
            data = resp.json()

            jobs = []
            for item in (data if isinstance(data, list) else [])[:limit]:
                salary = item.get("employmentTypes", [{}])[0] if item.get("employmentTypes") else {}
                sal_from = salary.get("fromPln") or salary.get("from")
                sal_to = salary.get("toPln") or salary.get("to")
                # Convert PLN to USD approximately (1 PLN ≈ 0.25 USD)
                salary_min = int(sal_from * 0.25) if sal_from else None
                salary_max = int(sal_to * 0.25) if sal_to else None

                jobs.append({
                    "title": item.get("title", ""),
                    "company_name": item.get("companyName", "Unknown"),
                    "location": item.get("city", "Remote") if not item.get("fullyRemote") else "Remote",
                    "is_remote": item.get("fullyRemote", False) or item.get("remoteInterview", False),
                    "apply_url": f"https://justjoin.it/offers/{item.get('id', '')}",
                    "description": _clean_html(item.get("body", ""))[:5000],
                    "source_board": "justjoin",
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "posted_at": item.get("publishedAt"),
                })
            return jobs
        except Exception as e:
            print(f"JustJoin error: {e}")
            return []


# ---------------------------------------------------------------------------
# Remotive (multi-category) — extra categories beyond software-dev
# ---------------------------------------------------------------------------
class RemotiveDevOpsScraper:
    def get_jobs(self): return RemotiveScraper().get_jobs(category="devops-sysadmin", limit=100)

class RemotiveDataScraper:
    def get_jobs(self): return RemotiveScraper().get_jobs(category="data", limit=100)


# ---------------------------------------------------------------------------
# WorkingNomads (multi-category)
# ---------------------------------------------------------------------------
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
                "description": _clean_html(i.get("description", ""))[:5000],
                "source_board": "workingnomads",
                "posted_at": i.get("pub_date"),
            } for i in r.json()[:80]]
        except Exception as e:
            print(f"WorkingNomads DevOps error: {e}")
            return []


# ---------------------------------------------------------------------------
# WeWorkRemotely extra categories
# ---------------------------------------------------------------------------
class WWRDevOpsScraper:
    def get_jobs(self):
        return _parse_rss_feed(
            "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
            "weworkremotely",
        )

class WWRFrontendScraper:
    def get_jobs(self):
        return _parse_rss_feed(
            "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
            "weworkremotely",
        )


# ---------------------------------------------------------------------------
# Reddit (extra subreddits)
# ---------------------------------------------------------------------------
class RedditRemoteJSScraper:
    def get_jobs(self):
        return RedditScraper()._scrape_subreddit("remotejs", limit=50)


# Monkey-patch helper so RedditScraper can be called per subreddit
def _reddit_scrape_sub(self, sub: str, limit: int = 50) -> List[Dict]:
    client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0 (job search bot)"})
    try:
        response = client.get(
            f"https://old.reddit.com/r/{sub}/new.json",
            params={"limit": limit},
        )
        if response.status_code != 200:
            return []
        data = response.json()
        posts = data.get("data", {}).get("children", [])
        jobs = []
        for post in posts:
            pd_ = post.get("data", {})
            title = pd_.get("title", "")
            if sub == "forhire" and "[hiring]" not in title.lower():
                continue
            company, job_title = self._parse_reddit_title(title)
            jobs.append({
                "title": job_title,
                "company_name": company,
                "location": "Remote" if _is_remote("", title, pd_.get("selftext", "")) else "Unknown",
                "is_remote": _is_remote("", title, pd_.get("selftext", "")),
                "apply_url": pd_.get("url", ""),
                "description": (pd_.get("selftext", "") or "")[:5000],
                "source_board": f"reddit_{sub}",
                "posted_at": None,
            })
        return jobs
    except Exception:
        return []

RedditScraper._scrape_subreddit = _reddit_scrape_sub


# ---------------------------------------------------------------------------
# Jobicy engineering (no category filter — catches all engineering roles)
# ---------------------------------------------------------------------------
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
                "description": _clean_html(i.get("jobDescription", ""))[:5000],
                "source_board": "jobicy",
                "salary": i.get("annualSalaryMin"),
                "posted_at": i.get("pubDate"),
            } for i in resp.json().get("jobs", [])]
        except Exception as e:
            print(f"Jobicy all error: {e}")
            return []


# ---------------------------------------------------------------------------
# Freshremote.work — aggregator focused on fully-remote companies
# ---------------------------------------------------------------------------
class FreshRemoteScraper:
    def get_jobs(self): return _parse_rss_feed("https://freshremote.work/feed/", "freshremote")


# ---------------------------------------------------------------------------
# PowerToFly — inclusive remote tech hiring, many small/mid startups
# ---------------------------------------------------------------------------
class PowerToFlyScraper:
    def get_jobs(self): return _parse_rss_feed("https://powertofly.com/jobs/feed/", "powertofly")


# ---------------------------------------------------------------------------
# Remote First Jobs — exclusively remote-first companies
# ---------------------------------------------------------------------------
class RemoteFirstJobsScraper:
    def get_jobs(self):
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            resp = client.get("https://remotefirstjobs.com/api/jobs")
            if resp.status_code == 200:
                data = resp.json()
                jobs = []
                for item in (data if isinstance(data, list) else data.get("jobs", [])):
                    jobs.append({
                        "title": item.get("title", ""),
                        "company_name": item.get("company", "Unknown"),
                        "location": "Remote",
                        "is_remote": True,
                        "apply_url": item.get("url", ""),
                        "description": _clean_html(item.get("description", ""))[:5000],
                        "source_board": "remotefirstjobs",
                        "posted_at": item.get("created_at"),
                    })
                return jobs
        except Exception:
            pass
        return _parse_rss_feed("https://remotefirstjobs.com/feed/", "remotefirstjobs")


# ---------------------------------------------------------------------------
# Cord.co — UK/global startup jobs, salary always shown, verified companies
# ---------------------------------------------------------------------------
class CordScraper:
    """https://cord.co — startup jobs with transparent salary. Free public API."""

    def get_jobs(self, limit: int = 100) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={
                "User-Agent": "JobScout/1.0",
                "Accept": "application/json",
            })
            resp = client.get(
                "https://cord.co/api/jobs",
                params={"remote": "true", "limit": limit},
            )
            if resp.status_code == 200:
                data = resp.json()
                jobs = []
                for item in (data if isinstance(data, list) else data.get("jobs", data.get("results", [])))[:limit]:
                    company = item.get("company", {}) or {}
                    sal = item.get("salary", {}) or {}
                    sal_min = sal.get("min") or sal.get("minimum") or item.get("salary_min")
                    sal_max = sal.get("max") or sal.get("maximum") or item.get("salary_max")
                    jobs.append({
                        "title": item.get("title", item.get("role", "")),
                        "company_name": company.get("name", item.get("company_name", "Unknown")),
                        "location": item.get("location", "Remote"),
                        "is_remote": item.get("remote", True),
                        "apply_url": item.get("url", item.get("apply_url", "")),
                        "description": _clean_html(item.get("description", ""))[:5000],
                        "source_board": "cord",
                        "salary_min": int(sal_min) if sal_min else None,
                        "salary_max": int(sal_max) if sal_max else None,
                        "posted_at": item.get("created_at") or item.get("published_at"),
                    })
                return jobs
        except Exception:
            pass
        # RSS fallback
        return _parse_rss_feed("https://cord.co/jobs/remote.rss", "cord", limit)


# ---------------------------------------------------------------------------
# Wellfound (AngelList) — startup jobs via RSS, salary shown on many listings
# ---------------------------------------------------------------------------
class WellfoundScraper:
    """Wellfound.com startup job listings — salary-transparent, verified startups."""

    def get_jobs(self, limit: int = 100) -> List[Dict]:
        # Try multiple Wellfound RSS/API endpoints
        for url in [
            "https://wellfound.com/jobs/software-engineer.rss",
            "https://angel.co/job_listings.rss",
            "https://wellfound.com/jobs.rss",
        ]:
            jobs = _parse_rss_feed(url, "wellfound", limit)
            if jobs:
                return jobs
        return []


# ---------------------------------------------------------------------------
# Hired.com — salary-first marketplace, companies apply to you
# ---------------------------------------------------------------------------
class HiredScraper:
    """https://hired.com — salary-first job marketplace. Companies bid on you."""

    def get_jobs(self, limit: int = 80) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0", "Accept": "application/json"})
            resp = client.get(
                "https://hired.com/api/v1/job_listings",
                params={"remote": 1, "limit": limit},
            )
            if resp.status_code == 200:
                data = resp.json()
                jobs = []
                for item in (data if isinstance(data, list) else data.get("job_listings", []))[:limit]:
                    jobs.append({
                        "title": item.get("title", item.get("job_function", "")),
                        "company_name": item.get("company", {}).get("name", "Unknown") if isinstance(item.get("company"), dict) else str(item.get("company", "Unknown")),
                        "location": item.get("locations", ["Remote"])[0] if item.get("locations") else "Remote",
                        "is_remote": item.get("remote", False) or "remote" in str(item.get("locations", [])).lower(),
                        "apply_url": item.get("url", ""),
                        "description": _clean_html(item.get("description", ""))[:5000],
                        "source_board": "hired",
                        "salary_min": item.get("salary_min") or item.get("min_salary"),
                        "salary_max": item.get("salary_max") or item.get("max_salary"),
                        "posted_at": item.get("created_at"),
                    })
                return jobs
        except Exception:
            pass
        return _parse_rss_feed("https://hired.com/jobs/rss", "hired", limit)


# ---------------------------------------------------------------------------
# Talent.io — EU tech jobs, salary always shown upfront, verified companies
# ---------------------------------------------------------------------------
class TalentioScraper:
    """https://www.talent.io — EU tech job marketplace, transparent salary."""

    def get_jobs(self, limit: int = 80) -> List[Dict]:
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0", "Accept": "application/json"})
            resp = client.get(
                "https://api.talent.io/api/v1/public/jobs",
                params={"remote": "true", "limit": limit, "type": "permanent"},
            )
            if resp.status_code == 200:
                data = resp.json()
                jobs = []
                for item in (data if isinstance(data, list) else data.get("jobs", data.get("results", [])))[:limit]:
                    sal = item.get("salary", {}) or item.get("compensation", {}) or {}
                    jobs.append({
                        "title": item.get("title", item.get("name", "")),
                        "company_name": (item.get("company", {}) or {}).get("name", "Unknown"),
                        "location": item.get("location", "Remote"),
                        "is_remote": item.get("remote", True),
                        "apply_url": item.get("url", item.get("apply_url", "")),
                        "description": _clean_html(item.get("description", ""))[:5000],
                        "source_board": "talentio",
                        "salary_min": sal.get("min") or sal.get("minimum"),
                        "salary_max": sal.get("max") or sal.get("maximum"),
                        "posted_at": item.get("created_at") or item.get("published_at"),
                    })
                return jobs
        except Exception as e:
            print(f"Talent.io error: {e}")
        return []


# ---------------------------------------------------------------------------
# Pallet.xyz — hundreds of indie startup job boards in one
# ---------------------------------------------------------------------------
class PalletScraper:
    """Pallet.xyz — small startup job boards (many indie devs/startups use this)."""

    # Known active Pallet board slugs — each is a separate startup community board
    BOARDS = [
        "pragmaticengineer", "levels", "lenny", "techleadhub", "highgrowthengineer",
        "remotepython", "devtoolsdigest", "swizec", "buildspace", "the-open-source-observer",
    ]

    def get_jobs(self, limit: int = 100) -> List[Dict]:
        jobs = []
        for board in self.BOARDS:
            board_jobs = _parse_rss_feed(
                f"https://{board}.pallet.xyz/jobs/rss",
                "pallet",
                limit=20,
            )
            jobs.extend(board_jobs)
            if len(jobs) >= limit:
                break
        return jobs[:limit]


class HNJobStoriesScraper:
    """Dedicated HN /jobstories — YC company job posts."""

    def get_jobs(self, limit: int = 50) -> List[Dict]:
        client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
        jobs = []

        try:
            response = client.get("https://hacker-news.firebaseio.com/v0/jobstories.json")
            response.raise_for_status()
            story_ids = response.json()[:limit]

            for story_id in story_ids:
                try:
                    r = client.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
                    r.raise_for_status()
                    item = r.json()

                    title = item.get("title", "")
                    url = item.get("url", "")
                    text = _clean_html(item.get("text", ""))

                    company_name, job_title = _parse_hn_title(title)

                    jobs.append({
                        "title": job_title,
                        "company_name": company_name,
                        "location": "Remote" if _is_remote("", title, text) else "Unknown",
                        "is_remote": _is_remote("", title, text),
                        "apply_url": url or f"https://news.ycombinator.com/item?id={story_id}",
                        "description": text[:5000] if text else title,
                        "source_board": "hackernews_jobs",
                        "posted_at": None,
                    })
                    time.sleep(0.1)
                except Exception:
                    continue

        except Exception as e:
            print(f"HN job stories error: {e}")

        return jobs


def _parse_hn_title(title: str) -> tuple:
    """Parse 'Company (YC XX) Is Hiring Title' into (company, title)."""
    m = re.match(r"^(.+?)\s*(?:\(YC\s*\w+\))?\s*(?:is hiring|hiring|–|-)\s*(.+)$", title, re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return title, title


# ---------------------------------------------------------------------------
# Keyword Filter (shared with ats_scrapers)
# ---------------------------------------------------------------------------

def matches_criteria(job: Dict, criteria: Dict) -> bool:
    """Check if a job matches user criteria."""
    from worker.scraping.dedup import is_globally_remote

    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    location = (job.get("location") or "").lower()
    text = f"{title} {description} {location}"

    if criteria.get("remote_only") and not job.get("is_remote"):
        return False

    if criteria.get("global_remote_only") and not is_globally_remote(job):
        return False

    title_keywords = criteria.get("title_keywords", [])
    if title_keywords:
        if not any(kw.lower() in title for kw in title_keywords):
            return False

    exclude = criteria.get("exclude_keywords", [])
    if exclude:
        if any(kw.lower() in title for kw in exclude):
            return False

    skills = criteria.get("required_skills", [])
    if skills:
        if not any(skill.lower() in text for skill in skills):
            return False

    max_yoe = criteria.get("max_yoe")
    if max_yoe is not None:
        yoe_patterns = re.findall(r"(\d+)\+?\s*(?:years|yrs)", description)
        if yoe_patterns:
            min_mentioned = min(int(y) for y in yoe_patterns)
            if min_mentioned > max_yoe:
                return False

    # Salary filter — only reject if we have hard data that doesn't fit
    # (many jobs don't publish salary, so we let them through)
    min_salary = criteria.get("min_salary")  # e.g. 40000
    max_salary = criteria.get("max_salary")  # e.g. 100000
    if min_salary and job.get("salary_max") and job["salary_max"] < min_salary:
        return False
    if max_salary and job.get("salary_min") and job["salary_min"] > max_salary:
        return False

    return True


# ---------------------------------------------------------------------------
# Unified Pipeline — scrape all boards, filter, save to DB
# ---------------------------------------------------------------------------

def scrape_board_jobs(
    db,
    boards: List[str] = None,
    criteria: Dict = None,
    progress_callback=None,
) -> Dict:
    """
    Scrape jobs from all job boards, filter, save to DB.

    Args:
        db: Database instance
        boards: Which boards to scrape (None = all)
        criteria: Filter criteria
        progress_callback: fn(message, progress) for UI updates

    Returns:
        {"total_scraped": int, "matched": int, "saved": int, "by_board": {}}
    """
    if criteria is None:
        criteria = {
            "title_keywords": ["backend", "developer", "engineer", "software", "python", "golang", "full stack", "fullstack"],
            "required_skills": [],
            "exclude_keywords": ["staff", "principal", "director", "vp", "head of", "lead architect"],
            "remote_only": True,
            "max_yoe": 5,
        }

    all_boards = {
        "remoteok": ("RemoteOK", lambda: RemoteOKScraper().get_jobs()),
        "remotive": ("Remotive", lambda: RemotiveScraper().get_jobs(category="software-dev", limit=200)),
        "weworkremotely": ("WeWorkRemotely", lambda: WeWorkRemotelyScraper().get_jobs()),
        "hackernews": ("HN Who's Hiring", lambda: HackerNewsScraper().get_jobs(months=2)),
        "hackernews_jobs": ("HN Job Stories", lambda: HNJobStoriesScraper().get_jobs(limit=50)),
        "reddit": ("Reddit", lambda: RedditScraper().get_jobs(limit_per_sub=50)),
        "himalayas": ("Himalayas", lambda: HimalayasScraper().get_jobs(limit=100)),
        "arbeitnow": ("Arbeitnow", lambda: ArbeitnowScraper().get_jobs(limit=100)),
        "jobicy": ("Jobicy", lambda: JobicyScraper().get_jobs(limit=50)),
        "themuse": ("The Muse", lambda: TheMuseScraper().get_jobs(limit=100)),
        "workingnomads": ("WorkingNomads", lambda: WorkingNomadsScraper().get_jobs(limit=100)),
        "jobspresso": ("Jobspresso", lambda: JobspressoScraper().get_jobs(limit=50)),
        "wfhio": ("WFH.io", lambda: WFHioScraper().get_jobs(limit=60)),
        # --- NEW LOW-COMPETITION BOARDS ---
        "remoteco": ("Remote.co", lambda: RemoteCo().get_jobs()),
        "authenticjobs": ("Authentic Jobs", lambda: AuthenticJobsScraper().get_jobs()),
        "djangojobs": ("DjangoJobs", lambda: DjangoJobsScraper().get_jobs()),
        "larajobs": ("LaraJobs", lambda: LaraJobsScraper().get_jobs()),
        "nodesk": ("NodeDesk", lambda: NodeDeskScraper().get_jobs()),
        "4dayweek": ("4DayWeek", lambda: FourDayWeekScraper().get_jobs()),
        "vuejobs": ("VueJobs", lambda: VueJobsScraper().get_jobs()),
        "golangjobs": ("GolangJobs", lambda: GolangJobsScraper().get_jobs()),
        "dynamitejobs": ("Dynamite Jobs", lambda: DynamiteJobsScraper().get_jobs()),
        "smashingmag": ("Smashing Mag Jobs", lambda: SmashingMagJobsScraper().get_jobs()),
        "devitjobs": ("DevITjobs EU", lambda: DevITJobsScraper().get_jobs(limit=100)),
        "cryptojobslist": ("CryptoJobsList", lambda: CryptoJobsListScraper().get_jobs(limit=60)),
        "web3career": ("Web3.career", lambda: Web3CareerScraper().get_jobs()),
        "climatebase": ("ClimateBase", lambda: ClimateBaseScraper().get_jobs(limit=60)),
        "justjoin": ("JustJoin.it", lambda: JustJoinScraper().get_jobs(limit=100)),
        "remotive_devops": ("Remotive DevOps", lambda: RemotiveDevOpsScraper().get_jobs()),
        "remotive_data": ("Remotive Data", lambda: RemotiveDataScraper().get_jobs()),
        "workingnomads_devops": ("WorkingNomads DevOps", lambda: WorkingNomadsDevOpsScraper().get_jobs()),
        "wwr_devops": ("WWR DevOps", lambda: WWRDevOpsScraper().get_jobs()),
        "wwr_frontend": ("WWR Frontend", lambda: WWRFrontendScraper().get_jobs()),
        "reddit_remotejs": ("Reddit RemoteJS", lambda: RedditScraper()._scrape_subreddit("remotejs", 50)),
        "jobicy_all": ("Jobicy (all)", lambda: JobicyAllScraper().get_jobs()),
        "freshremote": ("Fresh Remote", lambda: FreshRemoteScraper().get_jobs()),
        "powertofly": ("PowerToFly", lambda: PowerToFlyScraper().get_jobs()),
        "remotefirstjobs": ("Remote First Jobs", lambda: RemoteFirstJobsScraper().get_jobs()),
        # --- SALARY-TRANSPARENT / LOW-FRAUD BOARDS ---
        "cord": ("Cord.co", lambda: CordScraper().get_jobs(limit=100)),
        "wellfound": ("Wellfound", lambda: WellfoundScraper().get_jobs(limit=100)),
        "hired": ("Hired.com", lambda: HiredScraper().get_jobs(limit=80)),
        "talentio": ("Talent.io", lambda: TalentioScraper().get_jobs(limit=80)),
        "pallet": ("Pallet Boards", lambda: PalletScraper().get_jobs(limit=100)),
    }

    if boards is None:
        boards = _get_enabled_boards(list(all_boards.keys()))

    stats = {"total_scraped": 0, "matched": 0, "saved": 0, "errors": 0, "by_board": {}}
    total_boards = len(boards)

    for i, board_key in enumerate(boards):
        if board_key not in all_boards:
            continue

        board_name, fetch_fn = all_boards[board_key]

        if progress_callback:
            progress_callback(f"Scraping {board_name}...", i / total_boards)

        board_stats = {"scraped": 0, "matched": 0, "saved": 0}

        try:
            print(f"\n--- {board_name} ---")
            jobs = fetch_fn()
            board_stats["scraped"] = len(jobs)
            print(f"  Fetched {len(jobs)} jobs")

            # Filter
            matching = [j for j in jobs if matches_criteria(j, criteria)]
            board_stats["matched"] = len(matching)
            print(f"  {len(matching)} match criteria")

            # Save to DB
            for job in matching:
                company_id = db.find_or_create_company(
                    job["company_name"],
                    defaults={
                        "source": "job_board",
                        "ats_type": "unknown",
                    },
                )
                db_job = to_db_job(job, company_id)
                if db.upsert_job(db_job):
                    board_stats["saved"] += 1

            print(f"  Saved {board_stats['saved']} new jobs")

        except Exception as e:
            stats["errors"] += 1
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()

        stats["by_board"][board_key] = board_stats
        stats["total_scraped"] += board_stats["scraped"]
        stats["matched"] += board_stats["matched"]
        stats["saved"] += board_stats["saved"]

    if progress_callback:
        progress_callback("Done!", 1.0)

    print(f"\nBoard scraping complete: {stats['total_scraped']} scraped, {stats['matched']} matched, {stats['saved']} saved")
    return stats
