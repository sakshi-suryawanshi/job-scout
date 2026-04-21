# worker/discovery/serper_dorking.py
"""
Serper.dev Google Dorking for startup discovery.
Finds hidden gem companies via targeted search queries.
Free tier: 2,500 searches/month.
"""

import os
import json
import httpx
import re
from datetime import date, datetime
from typing import List, Dict, Optional
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass


SERPER_API_URL = "https://google.serper.dev/search"

# ---------------------------------------------------------------------------
# Serper usage + cooldown tracking
# ---------------------------------------------------------------------------

_SERPER_USAGE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), ".streamlit", "serper_usage.json")

_COOLDOWN_DAYS = 7  # Don't re-run same category within 7 days


def _load_serper_usage() -> dict:
    try:
        with open(_SERPER_USAGE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"monthly": {}, "category_last_run": {}}


def _save_serper_usage(data: dict):
    try:
        os.makedirs(os.path.dirname(_SERPER_USAGE_FILE), exist_ok=True)
        with open(_SERPER_USAGE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def get_serper_usage() -> dict:
    """Return monthly query counts and category cooldown status."""
    data = _load_serper_usage()
    month_key = date.today().strftime("%Y-%m")
    monthly_calls = data.get("monthly", {}).get(month_key, 0)
    remaining = max(0, 2500 - monthly_calls)

    cooldowns = {}
    for cat, last_run in data.get("category_last_run", {}).items():
        try:
            days_ago = (date.today() - date.fromisoformat(last_run)).days
            cooldowns[cat] = {"last_run": last_run, "days_ago": days_ago, "on_cooldown": days_ago < _COOLDOWN_DAYS}
        except Exception:
            pass

    return {"calls_this_month": monthly_calls, "remaining": remaining, "limit": 2500, "cooldowns": cooldowns}


def _record_serper_calls(count: int, category: str):
    data = _load_serper_usage()
    month_key = date.today().strftime("%Y-%m")
    monthly = data.get("monthly", {})
    monthly[month_key] = monthly.get(month_key, 0) + count
    data["monthly"] = monthly
    data.setdefault("category_last_run", {})[category] = date.today().isoformat()
    _save_serper_usage(data)


def is_category_on_cooldown(category: str) -> tuple:
    """Returns (on_cooldown: bool, days_ago: int)."""
    data = _load_serper_usage()
    last_run = data.get("category_last_run", {}).get(category)
    if not last_run:
        return False, None
    try:
        days_ago = (date.today() - date.fromisoformat(last_run)).days
        return days_ago < _COOLDOWN_DAYS, days_ago
    except Exception:
        return False, None

# --- Dork query templates ---
# Each returns a list of (query_string, category) tuples.
# Categories help prioritize and tag discovered companies.

def _build_dork_queries() -> dict:
    """Build dork queries with dynamic year so they never go stale."""
    from datetime import datetime
    y = datetime.now().year
    yr = f"{y} OR {y + 1}"

    return {
        "ats_hiring": [
            ('site:boards.greenhouse.io "remote" "engineer"', "greenhouse"),
            ('site:boards.greenhouse.io "worldwide" "developer"', "greenhouse"),
            ('site:boards.greenhouse.io "backend" "startup"', "greenhouse"),
            ('site:boards.greenhouse.io "python" OR "golang" remote', "greenhouse"),
            ('site:jobs.lever.co "remote" "engineer"', "lever"),
            ('site:jobs.lever.co "backend" "python" OR "go"', "lever"),
            ('site:jobs.ashbyhq.com "remote" "engineer"', "ashby"),
            ('site:jobs.ashbyhq.com "backend" OR "fullstack"', "ashby"),
            ('site:jobs.ashbyhq.com "worldwide" "developer"', "ashby"),
        ],
        "job_boards": [
            ('site:wellfound.com "1-10 employees" "remote" "engineer"', "wellfound"),
            ('site:wellfound.com "11-50 employees" "remote" "backend"', "wellfound"),
            ('site:wellfound.com "seed" "hiring" "remote"', "wellfound"),
            ('site:wellfound.com "pre-seed" "engineer" "remote"', "wellfound"),
            ('site:weworkremotely.com "startup" "backend" OR "python"', "weworkremotely"),
            ('site:himalayas.app "startup" "engineer" "remote"', "himalayas"),
            ('site:arbeitnow.com "remote" "engineer" "startup"', "arbeitnow"),
            ('site:jobicy.com "remote" "developer" "startup"', "jobicy"),
        ],
        "career_pages": [
            ('intitle:"careers" "we are hiring" "remote" "seed" "startup"', "career_page"),
            ('intitle:"jobs" "join our team" "remote" "series a" "engineer"', "career_page"),
            ('intitle:"careers" "small team" "remote" "developer" -enterprise', "career_page"),
            ('intitle:"open positions" "remote" "startup" "backend"', "career_page"),
            ('"we\'re hiring" "remote" "early stage" "engineer" -linkedin', "career_page"),
            ('"join us" "remote" "seed funded" "developer"', "career_page"),
        ],
        "distress_signals": [
            ('site:news.ycombinator.com "who is hiring" "remote" "backend"', "hackernews"),
            ('site:news.ycombinator.com "who is hiring" "remote" "python"', "hackernews"),
            ('site:indiehackers.com "looking for" "developer" OR "engineer"', "indiehackers"),
            ('site:indiehackers.com "need help" "developer" "growing"', "indiehackers"),
            ('"growing fast" "need engineer" "remote" "startup" -enterprise', "distress"),
        ],
        "funding_signals": [
            (f'"raised" "seed" "million" "hiring" "remote" {yr}', "funding"),
            (f'"series a" "raised" "hiring" "engineer" "remote" {yr}', "funding"),
            ('"pre-seed" "funding" "hiring" "developer" "remote"', "funding"),
            (f'site:techcrunch.com "raises" "seed" {yr} "remote"', "funding"),
            (f'"just raised" "hiring" "engineer" "remote" {yr}', "funding"),
            (f'"recently funded" "hiring" "developer" "remote" {yr}', "funding"),
        ],
        "hidden_gems": [
            ('"hiring" "remote" "developer" "africa" startup -linkedin', "hidden"),
            ('"hiring" "remote" "engineer" "southeast asia" startup -linkedin', "hidden"),
            ('"hiring" "remote" "developer" "latin america" startup -linkedin', "hidden"),
            ('site:wellfound.com "1-10 employees" "remote" "backend"', "hidden"),
            ('intitle:"careers" "remote" "emerging markets" OR "developing countries" "engineer"', "hidden"),
            ('"hiring" "remote" "impact" "startup" "engineer" -google -meta -amazon -apple', "hidden"),
        ],
        "github_signals": [
            ('site:github.com "we are hiring" "remote" "backend" "startup"', "github"),
            ('site:github.com "join our team" "remote" "engineer" "hiring"', "github"),
        ],
        "regional_gems": [
            ('"hiring" "remote" "engineer" "japan" "startup"', "regional"),
            ('"hiring" "remote" "developer" "kenya" OR "nigeria" OR "ghana" startup', "regional"),
            ('"hiring" "remote" "developer" "estonia" OR "portugal" OR "poland" startup', "regional"),
            ('"hiring" "remote" "engineer" "singapore" OR "indonesia" startup', "regional"),
        ],
        "yc_latest": [
            (f'site:news.ycombinator.com "YC W{str(y)[-2:]} OR YC S{str(y)[-2:]}" "hiring" "remote"', "yc"),
            ('site:boards.greenhouse.io "YC" "remote" "engineer" "seed"', "yc"),
            ('site:jobs.ashbyhq.com "YC" "remote" "backend"', "yc"),
        ],
        "twitter_x": [
            ('site:x.com "hiring" "remote" "backend engineer" "startup" "apply"', "twitter"),
            ('site:x.com "we are hiring" "remote" "developer" "startup"', "twitter"),
            ('site:x.com "job opening" "remote" "engineer" "startup" "DM"', "twitter"),
            ('site:twitter.com "hiring" "remote" "backend" "startup" "apply now"', "twitter"),
            ('site:x.com "looking for" "engineer" "remote" "seed" OR "series a"', "twitter"),
        ],
        "salary_targeted": [
            ('site:wellfound.com "$50k" OR "$60k" "backend" "remote"', "wellfound"),
            ('site:wellfound.com "$40k" OR "$70k" "engineer" "remote" "startup"', "wellfound"),
            ('"$50,000" OR "$60,000" "backend developer" "remote" -glassdoor -indeed', "salary"),
            ('"annual salary" "50" OR "60" "remote" "backend" OR "fullstack" "startup"', "salary"),
            ('site:jobs.lever.co "compensation" "remote" "engineer" "startup"', "lever"),
        ],
    }

DORK_QUERIES = _build_dork_queries()


class SerperDorker:
    """Google dorking via Serper.dev API for startup discovery."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("SERPER_API_KEY")
        if not self.api_key:
            raise ValueError("SERPER_API_KEY must be set in environment or .env")
        self.client = httpx.Client(timeout=30.0)
        self.queries_used = 0

    def search(self, query: str, num_results: int = 10) -> List[Dict]:
        """Execute a single Serper.dev search query."""
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "q": query,
            "num": num_results,
        }

        try:
            response = self.client.post(SERPER_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            self.queries_used += 1
            data = response.json()
            return data.get("organic", [])
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                print("Serper.dev rate limit hit - pausing")
            elif e.response.status_code == 403:
                print("Serper.dev API key invalid or quota exceeded")
            else:
                print(f"Serper.dev HTTP error: {e.response.status_code}")
            return []
        except Exception as e:
            print(f"Serper.dev error: {e}")
            return []

    def extract_company_from_greenhouse(self, url: str, title: str) -> Optional[Dict]:
        """Extract company info from Greenhouse URL."""
        # URL pattern: https://boards.greenhouse.io/companyname/jobs/...
        match = re.search(r"boards\.greenhouse\.io/([^/]+)", url)
        if match:
            slug = match.group(1)
            name = slug.replace("-", " ").replace("_", " ").title()
            return {
                "name": name,
                "career_url": f"https://boards.greenhouse.io/{slug}",
                "ats_type": "greenhouse",
                "job_title_hint": title,
            }
        return None

    def extract_company_from_lever(self, url: str, title: str) -> Optional[Dict]:
        """Extract company info from Lever URL."""
        # URL pattern: https://jobs.lever.co/companyname/...
        match = re.search(r"jobs\.lever\.co/([^/]+)", url)
        if match:
            slug = match.group(1)
            name = slug.replace("-", " ").replace("_", " ").title()
            return {
                "name": name,
                "career_url": f"https://jobs.lever.co/{slug}",
                "ats_type": "lever",
                "job_title_hint": title,
            }
        return None

    def extract_company_from_ashby(self, url: str, title: str) -> Optional[Dict]:
        """Extract company info from Ashby URL."""
        match = re.search(r"jobs\.ashbyhq\.com/([^/]+)", url)
        if match:
            slug = match.group(1)
            name = slug.replace("-", " ").replace("_", " ").title()
            return {
                "name": name,
                "career_url": f"https://jobs.ashbyhq.com/{slug}",
                "ats_type": "ashby",
                "job_title_hint": title,
            }
        return None

    def extract_company_from_wellfound(self, url: str, title: str, snippet: str) -> Optional[Dict]:
        """Extract company info from Wellfound/AngelList URL."""
        match = re.search(r"wellfound\.com/company/([^/]+)", url)
        if match:
            slug = match.group(1)
            name = slug.replace("-", " ").replace("_", " ").title()
            return {
                "name": name,
                "website": f"https://wellfound.com/company/{slug}",
                "career_url": f"https://wellfound.com/company/{slug}/jobs",
                "ats_type": "unknown",
                "job_title_hint": title,
            }
        return None

    def extract_company_from_generic(self, url: str, title: str, snippet: str) -> Optional[Dict]:
        """Extract company info from generic career/jobs pages."""
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")

        # Skip big job boards and social media
        skip_domains = {
            "linkedin.com", "indeed.com", "glassdoor.com", "monster.com",
            "ziprecruiter.com", "google.com", "facebook.com", "twitter.com",
            "reddit.com", "medium.com", "youtube.com", "wikipedia.org",
            "github.com", "stackoverflow.com", "news.ycombinator.com",
            "techcrunch.com", "crunchbase.com",
        }
        if any(skip in domain for skip in skip_domains):
            return None

        # Try to extract company name from title
        # Common patterns: "Company - Careers", "Jobs at Company", "Company | Open Positions"
        name = None
        for pattern in [
            r"^(.+?)\s*[-|]\s*(?:careers|jobs|hiring|open positions|work with us)",
            r"(?:jobs|careers)\s+(?:at|@)\s+(.+?)(?:\s*[-|]|$)",
            r"^(.+?)\s+(?:is hiring|hiring|careers|jobs)",
        ]:
            m = re.search(pattern, title, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
                break

        if not name:
            # Use domain name as fallback
            name = domain.split(".")[0].replace("-", " ").replace("_", " ").title()

        # Determine career URL
        career_url = url
        if not any(kw in url.lower() for kw in ["career", "job", "hiring", "position", "work-with"]):
            career_url = f"https://{domain}/careers"

        return {
            "name": name,
            "website": f"https://{domain}",
            "career_url": career_url,
            "ats_type": "custom",
            "job_title_hint": title,
        }

    def parse_results(self, results: List[Dict], category: str) -> List[Dict]:
        """Parse search results into company records."""
        companies = []

        for result in results:
            url = result.get("link", "")
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            company = None

            if "boards.greenhouse.io" in url:
                company = self.extract_company_from_greenhouse(url, title)
            elif "jobs.lever.co" in url:
                company = self.extract_company_from_lever(url, title)
            elif "jobs.ashbyhq.com" in url:
                company = self.extract_company_from_ashby(url, title)
            elif "wellfound.com" in url:
                company = self.extract_company_from_wellfound(url, title, snippet)
            elif category in ("career_page", "hidden", "regional", "distress", "funding", "twitter", "yc", "indiehackers", "hackernews"):
                company = self.extract_company_from_generic(url, title, snippet)

            if company:
                company["source_category"] = category
                company["search_snippet"] = snippet[:300]
                companies.append(company)

        return companies

    def to_db_format(self, company: Dict) -> Dict:
        """Convert parsed company to database schema."""
        notes_parts = []
        if company.get("job_title_hint"):
            notes_parts.append(f"Found via: {company['job_title_hint'][:100]}")
        if company.get("search_snippet"):
            notes_parts.append(f"Context: {company['search_snippet'][:150]}")
        if company.get("source_category"):
            notes_parts.append(f"Discovery: {company['source_category']}")

        # Priority scoring based on discovery category
        priority_map = {
            "greenhouse": 8,
            "lever": 8,
            "ashby": 8,
            "wellfound": 7,
            "career_page": 7,
            "distress": 9,    # Desperate companies = high priority
            "funding": 8,
            "hidden": 9,      # Hidden gems = highest
            "regional": 9,
            "hackernews": 7,
            "indiehackers": 7,
            "github": 6,
            "weworkremotely": 6,
            "remoteok": 6,
            "remotive": 6,
            "himalayas": 6,
            "justremote": 6,
            "yc": 9,
            "arbeitnow": 6,
            "jobicy": 6,
            "twitter": 8,
        }

        return {
            "name": company["name"],
            "career_url": company.get("career_url"),
            "website": company.get("website"),
            "ats_type": company.get("ats_type", "unknown"),
            "source": "serper",
            "is_active": True,
            "notes": " | ".join(notes_parts) if notes_parts else None,
            "priority_score": priority_map.get(company.get("source_category"), 5),
        }

    def run_dork_category(
        self, category: str, max_queries: int = None, results_per_query: int = 10,
        force: bool = False,
    ) -> List[Dict]:
        """Run all dork queries for a category. Skips if on cooldown unless force=True."""
        on_cooldown, days_ago = is_category_on_cooldown(category)
        if on_cooldown and not force:
            print(f"  [{category}] on cooldown (ran {days_ago}d ago) — skipping to save quota")
            return []

        live_queries = _build_dork_queries()
        queries = live_queries.get(category, [])
        if not queries:
            print(f"Unknown category: {category}")
            return []

        if max_queries:
            queries = queries[:max_queries]

        all_companies = []
        queries_fired = 0
        for query_str, cat in queries:
            print(f"  Dorking: {query_str[:60]}...")
            results = self.search(query_str, num_results=results_per_query)
            companies = self.parse_results(results, cat)
            all_companies.extend(companies)
            queries_fired += 1
            print(f"    Found {len(companies)} companies")

        if queries_fired:
            _record_serper_calls(queries_fired, category)

        return all_companies

    def run_discovery(
        self,
        categories: List[str] = None,
        max_queries_per_category: int = None,
        results_per_query: int = 10,
    ) -> List[Dict]:
        """
        Run full dorking discovery across categories.
        Returns deduplicated list of companies in DB format.
        """
        if categories is None:
            categories = list(DORK_QUERIES.keys())

        all_companies = []

        for category in categories:
            print(f"\n--- Category: {category} ---")
            companies = self.run_dork_category(
                category,
                max_queries=max_queries_per_category,
                results_per_query=results_per_query,
            )
            all_companies.extend(companies)

        # Convert to DB format
        db_companies = [self.to_db_format(c) for c in all_companies]

        # Deduplicate by name (case-insensitive)
        seen = set()
        unique = []
        for c in db_companies:
            name_key = c["name"].lower().strip()
            if name_key and name_key not in seen and len(name_key) > 1:
                seen.add(name_key)
                unique.append(c)

        print(f"\nTotal unique companies from dorking: {len(unique)}")
        print(f"Serper queries used this session: {self.queries_used}")

        return unique


def fetch_serper_companies(
    categories: List[str] = None,
    max_queries_per_category: int = None,
    results_per_query: int = 10,
) -> List[Dict]:
    """
    Convenience function to run Serper.dev dorking discovery.
    Returns list of companies in DB-ready format.
    """
    dorker = SerperDorker()
    return dorker.run_discovery(
        categories=categories,
        max_queries_per_category=max_queries_per_category,
        results_per_query=results_per_query,
    )


def create_signal_from_result(company: Dict, dorker_category: str) -> Dict:
    """Create a signal record from a dorking result for the signals table."""
    signal_type_map = {
        "funding": "funding",
        "distress": "distress",
        "hackernews": "distress",
        "indiehackers": "distress",
        "github": "github_activity",
        "hidden": "hiring",
        "regional": "hiring",
        "greenhouse": "hiring",
        "lever": "hiring",
        "ashby": "hiring",
    }

    return {
        "signal_type": signal_type_map.get(dorker_category, "hiring"),
        "confidence_score": 0.7,
        "source_signal": f"serper_dorking:{dorker_category}",
        "metadata": {
            "query_category": dorker_category,
            "company_name": company.get("name"),
            "snippet": company.get("search_snippet", "")[:200],
        },
        "processed": False,
    }
