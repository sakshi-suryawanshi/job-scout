# worker/scraping/career_scraper.py
"""
Generic Career Page Scraper — works on ANY company website.
Uses httpx + BeautifulSoup to extract job listings from career pages.
Falls back to regex patterns when structure is unknown.
Optionally uses Gemini 2.0 Flash for AI-powered extraction.
"""

import httpx
import re
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Career Page Fetcher
# ---------------------------------------------------------------------------

class CareerPageScraper:
    """Scrape job listings from any company career page."""

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
        """Fetch a career page. Returns HTML or None."""
        try:
            response = self.client.get(url)
            if response.status_code == 200:
                return response.text
            return None
        except Exception as e:
            print(f"  Fetch error ({url}): {e}")
            return None

    def find_career_url(self, website: str) -> Optional[str]:
        """Try common career page paths for a website."""
        if not website:
            return None

        domain = website.rstrip("/")
        if not domain.startswith("http"):
            domain = f"https://{domain}"

        paths = [
            "/careers", "/jobs", "/hiring", "/work-with-us",
            "/join-us", "/open-positions", "/career",
            "/about/careers", "/company/careers", "/team/join",
        ]

        for path in paths:
            url = f"{domain}{path}"
            try:
                response = self.client.head(url, timeout=8)
                if response.status_code == 200:
                    return url
                # Also check GET for redirects
                if response.status_code in (301, 302, 307, 308):
                    return url
            except Exception:
                continue

        return None

    def extract_jobs_from_html(self, html_content: str, base_url: str, company_name: str) -> List[Dict]:
        """
        Extract job listings from career page HTML using pattern matching.
        Works without AI — uses common HTML patterns found on career pages.
        """
        soup = BeautifulSoup(html_content, "lxml")
        jobs = []

        # Strategy 1: Find job listing links (most common pattern)
        jobs.extend(self._extract_from_links(soup, base_url, company_name))

        # Strategy 2: Find structured job cards/items
        if not jobs:
            jobs.extend(self._extract_from_cards(soup, base_url, company_name))

        # Strategy 3: Find job titles in headings
        if not jobs:
            jobs.extend(self._extract_from_headings(soup, base_url, company_name))

        # Deduplicate by URL
        seen = set()
        unique = []
        for j in jobs:
            url = j.get("apply_url", "")
            if url and url not in seen:
                seen.add(url)
                unique.append(j)

        return unique

    def _extract_from_links(self, soup: BeautifulSoup, base_url: str, company_name: str) -> List[Dict]:
        """Extract jobs from anchor tags that look like job listings."""
        jobs = []
        job_link_patterns = re.compile(
            r"(/jobs?/|/positions?/|/openings?/|/careers?/|/roles?/|/apply/|/vacancies?/)"
            r"[a-z0-9\-_]+",
            re.IGNORECASE,
        )

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)

            if not text or len(text) < 3 or len(text) > 200:
                continue

            # Check if href looks like a job posting URL
            full_url = urljoin(base_url, href)
            is_job_link = bool(job_link_patterns.search(href))

            # Also check if link text looks like a job title
            title_keywords = [
                "engineer", "developer", "designer", "manager", "analyst",
                "architect", "specialist", "coordinator", "lead", "intern",
                "scientist", "devops", "sre", "backend", "frontend", "fullstack",
                "python", "golang", "java", "react", "node",
            ]
            has_job_title = any(kw in text.lower() for kw in title_keywords)

            if is_job_link or has_job_title:
                # Try to extract location from nearby text
                parent = link.parent
                location = ""
                if parent:
                    parent_text = parent.get_text(" ", strip=True)
                    loc_match = re.search(
                        r"(remote|worldwide|on-?site|hybrid|"
                        r"(?:san francisco|new york|london|berlin|tokyo|"
                        r"united states|europe|asia|worldwide)[\w\s,]*)",
                        parent_text, re.IGNORECASE,
                    )
                    if loc_match:
                        location = loc_match.group(1).strip()

                jobs.append({
                    "title": text,
                    "company_name": company_name,
                    "location": location or "Unknown",
                    "is_remote": _is_remote(location, text, ""),
                    "apply_url": full_url,
                    "description": "",
                    "source_board": "career_page",
                })

        return jobs

    def _extract_from_cards(self, soup: BeautifulSoup, base_url: str, company_name: str) -> List[Dict]:
        """Extract jobs from common card/list item patterns."""
        jobs = []

        # Common CSS class patterns for job cards
        card_selectors = [
            {"class_": re.compile(r"job|position|opening|vacancy|role|career", re.I)},
            {"attrs": {"data-job": True}},
            {"attrs": {"data-position": True}},
        ]

        for selector in card_selectors:
            elements = soup.find_all(["div", "li", "article", "section"], **selector)
            for el in elements:
                title_el = el.find(["h2", "h3", "h4", "a", "strong"])
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                if len(title) < 3 or len(title) > 200:
                    continue

                # Find link
                link = el.find("a", href=True)
                apply_url = urljoin(base_url, link["href"]) if link else base_url

                # Find location
                el_text = el.get_text(" ", strip=True)
                location = ""
                loc_match = re.search(r"(remote|worldwide|hybrid|on-?site|[\w\s]+,\s*\w{2,})", el_text, re.I)
                if loc_match:
                    location = loc_match.group(1).strip()[:100]

                jobs.append({
                    "title": title,
                    "company_name": company_name,
                    "location": location or "Unknown",
                    "is_remote": _is_remote(location, title, el_text),
                    "apply_url": apply_url,
                    "description": el_text[:1000],
                    "source_board": "career_page",
                })

        return jobs

    def _extract_from_headings(self, soup: BeautifulSoup, base_url: str, company_name: str) -> List[Dict]:
        """Fallback: extract from any heading that looks like a job title."""
        jobs = []
        job_title_pattern = re.compile(
            r"(engineer|developer|designer|manager|analyst|architect|"
            r"specialist|coordinator|lead|scientist|devops|sre|"
            r"backend|frontend|fullstack|intern)",
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
                    "is_remote": _is_remote("", text, ""),
                    "apply_url": apply_url,
                    "description": "",
                    "source_board": "career_page",
                })

        return jobs

    def scrape_company(self, career_url: str, company_name: str) -> List[Dict]:
        """Scrape a single company's career page for jobs."""
        html = self.fetch_page(career_url)
        if not html:
            return []
        return self.extract_jobs_from_html(html, career_url, company_name)


def _is_remote(location: str, title: str, description: str) -> bool:
    text = f"{location} {title} {description}".lower()
    return any(kw in text for kw in [
        "remote", "worldwide", "anywhere", "work from home",
        "distributed", "wfh", "fully remote",
    ])


# ---------------------------------------------------------------------------
# Pipeline: scrape career pages from DB companies
# ---------------------------------------------------------------------------

def scrape_career_pages(
    db,
    criteria: Dict = None,
    max_companies: int = 50,
    progress_callback=None,
) -> Dict:
    """
    Scrape career pages of companies in the database.
    Only scrapes companies with ats_type='custom' or 'unknown' (not on ATS boards).
    """
    if criteria is None:
        criteria = {
            "title_keywords": ["backend", "developer", "engineer", "software", "python", "golang", "full stack", "fullstack"],
            "required_skills": [],
            "exclude_keywords": ["staff", "principal", "director", "vp", "head of", "lead architect"],
            "remote_only": True,
            "max_yoe": 5,
        }

    companies = db.get_companies(active_only=True, limit=5000)
    # Only scrape companies not already covered by ATS scrapers
    targets = [
        c for c in companies
        if c.get("ats_type") in ("custom", "unknown", None)
        and c.get("career_url")
    ][:max_companies]

    if not targets:
        print("No career pages to scrape")
        return {"total_scraped": 0, "matched": 0, "saved": 0, "errors": 0}

    scraper = CareerPageScraper()
    stats = {"total_scraped": 0, "matched": 0, "saved": 0, "errors": 0}

    from board_scrapers import matches_criteria, to_db_job

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
                company_id = company.get("id")
                db_job = to_db_job(job, company_id)
                if db.add_job(db_job):
                    stats["saved"] += 1

            # Update last_scraped
            db.update_company(company["id"], {"last_scraped": datetime.now().isoformat()})

            time.sleep(0.5)

        except Exception as e:
            stats["errors"] += 1
            print(f"  Error scraping {name}: {e}")

    print(f"\nCareer pages: {stats['total_scraped']} scraped, {stats['matched']} matched, {stats['saved']} saved")
    return stats
