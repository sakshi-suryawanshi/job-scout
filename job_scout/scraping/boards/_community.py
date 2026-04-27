# job_scout/scraping/boards/_community.py
"""Community platform scrapers: Hacker News (Algolia + Firebase) and Reddit."""

import re
import time
import httpx
from typing import List, Dict, Optional
from job_scout.scraping.base import clean_html, is_remote


def _parse_hn_title(title: str) -> tuple:
    m = re.match(r"^(.+?)\s*(?:\(YC\s*\w+\))?\s*(?:is hiring|hiring|–|-)\s*(.+)$", title, re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return title, title


class HackerNewsScraper:
    """Scrapes monthly 'Ask HN: Who is hiring?' threads + HN job stories feed."""

    def get_jobs(self, months: int = 2) -> List[Dict]:
        jobs = []
        jobs.extend(self._scrape_who_is_hiring(months))
        jobs.extend(self._scrape_job_stories())
        return jobs

    def _scrape_who_is_hiring(self, months: int) -> List[Dict]:
        client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
        jobs = []
        try:
            response = client.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={"query": '"who is hiring"', "tags": "ask_hn", "hitsPerPage": months},
            )
            response.raise_for_status()
            for thread in response.json().get("hits", []):
                if "who is hiring" not in thread.get("title", "").lower():
                    continue
                thread_id = thread.get("objectID")
                if not thread_id:
                    continue
                try:
                    item_resp = client.get(f"https://hn.algolia.com/api/v1/items/{thread_id}")
                    item_resp.raise_for_status()
                    for comment in item_resp.json().get("children", []):
                        text = comment.get("text", "")
                        if not text or len(text) < 50:
                            continue
                        parsed = self._parse_hn_comment(text, thread_id)
                        if parsed:
                            jobs.append(parsed)
                except Exception as e:
                    print(f"HN thread {thread_id} error: {e}")
                time.sleep(0.5)
        except Exception as e:
            print(f"HN Algolia error: {e}")
        return jobs

    def _scrape_job_stories(self) -> List[Dict]:
        client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
        jobs = []
        try:
            story_ids = client.get("https://hacker-news.firebaseio.com/v0/jobstories.json").json()[:50]
            for story_id in story_ids:
                try:
                    item = client.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json").json()
                    title = item.get("title", "")
                    url = item.get("url", "")
                    text = clean_html(item.get("text", ""))
                    company_name, job_title = _parse_hn_title(title)
                    jobs.append({
                        "title": job_title,
                        "company_name": company_name,
                        "location": "Remote" if is_remote("", title, text) else "Unknown",
                        "is_remote": is_remote("", title, text),
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
        clean = clean_html(text)
        lines = [line.strip() for line in clean.split("\n") if line.strip()]
        if not lines:
            return None
        first_line = lines[0]
        parts = [p.strip() for p in first_line.split("|")]
        company_name = parts[0] if parts else "Unknown"
        job_title = parts[1] if len(parts) > 1 else first_line
        location, is_rem = "", False
        for part in parts:
            pl = part.lower()
            if any(kw in pl for kw in ["remote", "worldwide", "anywhere"]):
                is_rem = True
            if any(kw in pl for kw in ["remote", "sf", "nyc", "london", "berlin", "worldwide", "us", "eu", "uk"]):
                location = part.strip()
        url_match = re.search(r'https?://[^\s<"]+', text)
        apply_url = url_match.group(0) if url_match else f"https://news.ycombinator.com/item?id={thread_id}"
        return {
            "title": job_title[:200],
            "company_name": company_name[:200],
            "location": location or ("Remote" if is_rem else "Unknown"),
            "is_remote": is_rem or is_remote("", first_line, clean),
            "apply_url": apply_url,
            "description": clean[:5000],
            "source_board": "hackernews",
            "posted_at": None,
        }


class RedditScraper:
    SUBREDDITS = ["forhire", "remotejs"]

    def get_jobs(self, limit_per_sub: int = 50) -> List[Dict]:
        jobs = []
        for sub in self.SUBREDDITS:
            jobs.extend(self._scrape_subreddit(sub, limit_per_sub))
        return jobs

    def _scrape_subreddit(self, sub: str, limit: int = 50) -> List[Dict]:
        client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0 (job search bot)"})
        try:
            response = client.get(f"https://old.reddit.com/r/{sub}/new.json", params={"limit": limit})
            if response.status_code != 200:
                return []
            jobs = []
            for post in response.json().get("data", {}).get("children", []):
                pd = post.get("data", {})
                title = pd.get("title", "")
                if sub == "forhire" and "[hiring]" not in title.lower():
                    continue
                company, job_title = self._parse_reddit_title(title)
                jobs.append({
                    "title": job_title,
                    "company_name": company,
                    "location": "Remote" if is_remote("", title, pd.get("selftext", "")) else "Unknown",
                    "is_remote": is_remote("", title, pd.get("selftext", "")),
                    "apply_url": pd.get("url", ""),
                    "description": (pd.get("selftext", "") or "")[:5000],
                    "source_board": f"reddit_{sub}",
                    "posted_at": None,
                })
            time.sleep(1)
            return jobs
        except Exception:
            return []

    def _parse_reddit_title(self, title: str) -> tuple:
        clean = re.sub(r"\[.*?\]", "", title).strip()
        if " - " in clean:
            parts = clean.split(" - ", 1)
            return parts[0].strip(), parts[1].strip()
        if " at " in clean.lower():
            m = re.match(r"(.+?)\s+at\s+(.+)", clean, re.IGNORECASE)
            if m:
                return m.group(2).strip(), m.group(1).strip()
        return "Unknown", clean
