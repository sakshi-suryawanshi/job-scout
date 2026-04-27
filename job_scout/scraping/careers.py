# job_scout/scraping/careers.py
# Moved from worker/scraping/career_scraper.py — no behavior change.
"""Generic career page scraper for any company website."""

import httpx
import re
import time
from typing import List, Dict, Optional
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from job_scout.scraping.base import is_remote


class CareerPageScraper:
    def __init__(self):
        self.client = httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )

    def fetch_page(self, url: str) -> Optional[str]:
        try:
            response = self.client.get(url)
            return response.text if response.status_code == 200 else None
        except Exception as e:
            print(f"  Fetch error ({url}): {e}")
            return None

    def find_career_url(self, website: str) -> Optional[str]:
        if not website:
            return None
        domain = website.rstrip("/")
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        for path in ["/careers", "/jobs", "/hiring", "/work-with-us", "/join-us",
                     "/open-positions", "/career", "/about/careers", "/company/careers", "/team/join"]:
            url = f"{domain}{path}"
            try:
                response = self.client.head(url, timeout=8)
                if response.status_code in (200, 301, 302, 307, 308):
                    return url
            except Exception:
                continue
        return None

    def extract_jobs_from_html(self, html_content: str, base_url: str, company_name: str) -> List[Dict]:
        soup = BeautifulSoup(html_content, "lxml")
        jobs = self._extract_from_links(soup, base_url, company_name)
        if not jobs:
            jobs = self._extract_from_cards(soup, base_url, company_name)
        if not jobs:
            jobs = self._extract_from_headings(soup, base_url, company_name)
        seen, unique = set(), []
        for j in jobs:
            url = j.get("apply_url", "")
            if url and url not in seen:
                seen.add(url)
                unique.append(j)
        return unique

    def _extract_from_links(self, soup, base_url, company_name) -> List[Dict]:
        jobs = []
        job_link_patterns = re.compile(
            r"(/jobs?/|/positions?/|/openings?/|/careers?/|/roles?/|/apply/|/vacancies?/)[a-z0-9\-_]+",
            re.IGNORECASE,
        )
        title_keywords = ["engineer", "developer", "designer", "manager", "analyst",
                          "architect", "specialist", "coordinator", "lead", "intern",
                          "scientist", "devops", "sre", "backend", "frontend", "fullstack",
                          "python", "golang", "java", "react", "node"]
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)
            if not text or len(text) < 3 or len(text) > 200:
                continue
            full_url = urljoin(base_url, href)
            is_job_link = bool(job_link_patterns.search(href))
            has_job_title = any(kw in text.lower() for kw in title_keywords)
            if is_job_link or has_job_title:
                parent = link.parent
                location = ""
                if parent:
                    parent_text = parent.get_text(" ", strip=True)
                    loc_match = re.search(
                        r"(remote|worldwide|on-?site|hybrid|(?:san francisco|new york|london|berlin|tokyo|united states|europe|asia|worldwide)[\w\s,]*)",
                        parent_text, re.IGNORECASE,
                    )
                    if loc_match:
                        location = loc_match.group(1).strip()
                jobs.append({
                    "title": text,
                    "company_name": company_name,
                    "location": location or "Unknown",
                    "is_remote": is_remote(location, text, ""),
                    "apply_url": full_url,
                    "description": "",
                    "source_board": "career_page",
                })
        return jobs

    def _extract_from_cards(self, soup, base_url, company_name) -> List[Dict]:
        jobs = []
        for selector in [
            {"class_": re.compile(r"job|position|opening|vacancy|role|career", re.I)},
            {"attrs": {"data-job": True}},
            {"attrs": {"data-position": True}},
        ]:
            for el in soup.find_all(["div", "li", "article", "section"], **selector):
                title_el = el.find(["h2", "h3", "h4", "a", "strong"])
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 3 or len(title) > 200:
                    continue
                link = el.find("a", href=True)
                apply_url = urljoin(base_url, link["href"]) if link else base_url
                el_text = el.get_text(" ", strip=True)
                location = ""
                loc_match = re.search(r"(remote|worldwide|hybrid|on-?site|[\w\s]+,\s*\w{2,})", el_text, re.I)
                if loc_match:
                    location = loc_match.group(1).strip()[:100]
                jobs.append({
                    "title": title,
                    "company_name": company_name,
                    "location": location or "Unknown",
                    "is_remote": is_remote(location, title, el_text),
                    "apply_url": apply_url,
                    "description": el_text[:1000],
                    "source_board": "career_page",
                })
        return jobs

    def _extract_from_headings(self, soup, base_url, company_name) -> List[Dict]:
        jobs = []
        job_title_pattern = re.compile(
            r"(engineer|developer|designer|manager|analyst|architect|specialist|coordinator|lead|scientist|devops|sre|backend|frontend|fullstack|intern)",
            re.IGNORECASE,
        )
        for heading in soup.find_all(["h2", "h3", "h4"]):
            text = heading.get_text(strip=True)
            if job_title_pattern.search(text) and 5 < len(text) < 150:
                link = heading.find("a", href=True) or heading.find_parent("a", href=True)
                apply_url = urljoin(base_url, link["href"]) if link else base_url
                jobs.append({
                    "title": text,
                    "company_name": company_name,
                    "location": "Unknown",
                    "is_remote": is_remote("", text, ""),
                    "apply_url": apply_url,
                    "description": "",
                    "source_board": "career_page",
                })
        return jobs

    def scrape_company(self, career_url: str, company_name: str) -> List[Dict]:
        html = self.fetch_page(career_url)
        if not html:
            return []
        return self.extract_jobs_from_html(html, career_url, company_name)


def scrape_career_pages(db, criteria: Dict = None, max_companies: int = 50, progress_callback=None) -> Dict:
    """Scrape career pages of companies in the DB with ats_type custom/unknown."""
    if criteria is None:
        criteria = {
            "title_keywords": ["backend", "developer", "engineer", "software", "python", "golang", "full stack", "fullstack"],
            "required_skills": [],
            "exclude_keywords": ["staff", "principal", "director", "vp", "head of", "lead architect"],
            "remote_only": True,
            "max_yoe": 5,
        }

    companies = db.get_companies(active_only=True, limit=5000)
    targets = [
        c for c in companies
        if c.get("ats_type") in ("custom", "unknown", None) and c.get("career_url")
    ][:max_companies]

    if not targets:
        return {"total_scraped": 0, "matched": 0, "saved": 0, "errors": 0}

    from job_scout.enrichment.filters import matches_criteria
    from job_scout.scraping.base import to_db_job

    scraper = CareerPageScraper()
    stats = {"total_scraped": 0, "matched": 0, "saved": 0, "errors": 0}

    for i, company in enumerate(targets):
        name = company.get("name", "Unknown")
        url = company.get("career_url", "")
        if progress_callback:
            progress_callback(f"Scraping {name}...", (i + 1) / len(targets))
        try:
            jobs = scraper.scrape_company(url, name)
            stats["total_scraped"] += len(jobs)
            matching = [j for j in jobs if matches_criteria(j, criteria)]
            stats["matched"] += len(matching)
            for job in matching:
                db_job = to_db_job(job, company.get("id"))
                if db.upsert_job(db_job):
                    stats["saved"] += 1
            db.update_company(company["id"], {"last_scraped": datetime.now().isoformat()})
            time.sleep(0.5)
        except Exception as e:
            stats["errors"] += 1
            print(f"  Error scraping {name}: {e}")

    print(f"\nCareer pages: {stats['total_scraped']} scraped, {stats['matched']} matched, {stats['saved']} saved")
    return stats
