# worker/scraping/board_scrapers.py
"""
Job Board Scrapers — RemoteOK, Remotive, WWR, HN, Reddit, Himalayas, etc.
All FREE. All return actual job listings (not just companies).
"""

import httpx
import re
import html
import time
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from datetime import datetime, date


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
    return {
        "company_id": company_id,
        "title": job.get("title", "")[:500],
        "location": job.get("location", "")[:500],
        "is_remote": job.get("is_remote", False),
        "apply_url": job.get("apply_url", ""),
        "source_board": job.get("source_board", "unknown"),
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
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    location = (job.get("location") or "").lower()
    text = f"{title} {description} {location}"

    if criteria.get("remote_only") and not job.get("is_remote"):
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
    }

    if boards is None:
        boards = list(all_boards.keys())

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
                if db.add_job(db_job):
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
