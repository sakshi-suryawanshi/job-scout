# worker/scraping/ats_scrapers.py
"""
ATS Job Scrapers — Greenhouse, Lever, Ashby.
All use FREE public APIs. No auth needed.
Returns actual job listings, not just companies.
"""

import httpx
import re
import time
from typing import List, Dict, Optional
from datetime import datetime, date


# ---------------------------------------------------------------------------
# Greenhouse Scraper
# Public API: https://developers.greenhouse.io/job-board.html
# ---------------------------------------------------------------------------

class GreenhouseScraper:
    """Scrape jobs from Greenhouse boards. FREE public API."""

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self):
        self.client = httpx.Client(
            timeout=15.0,
            headers={"User-Agent": "JobScout/1.0"},
        )

    def get_jobs(self, company_slug: str) -> List[Dict]:
        """Fetch all jobs for a company. Returns [] if board doesn't exist."""
        url = f"{self.BASE_URL}/{company_slug}/jobs"
        try:
            response = self.client.get(url, params={"content": "true"})
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()
            jobs = data.get("jobs", [])
            return [self._parse_job(j, company_slug) for j in jobs]
        except httpx.HTTPStatusError:
            return []
        except Exception:
            return []

    def is_active(self, company_slug: str) -> bool:
        """Quick check if a board exists (HEAD-like, no content)."""
        url = f"{self.BASE_URL}/{company_slug}/jobs"
        try:
            response = self.client.get(url, timeout=5.0)
            if response.status_code == 200:
                return len(response.json().get("jobs", [])) > 0
        except Exception:
            pass
        return False

    def _parse_job(self, raw: Dict, company_slug: str) -> Dict:
        location = raw.get("location", {}).get("name", "")
        title = raw.get("title", "")

        content = raw.get("content", "")
        description = re.sub(r"<[^>]+>", " ", content)
        description = re.sub(r"\s+", " ", description).strip()

        return {
            "title": title,
            "company_name": company_slug.replace("-", " ").replace("_", " ").title(),
            "company_slug": company_slug,
            "location": location,
            "is_remote": _is_remote(location, title, description),
            "apply_url": raw.get("absolute_url", f"https://boards.greenhouse.io/{company_slug}/jobs/{raw.get('id')}"),
            "description": description[:5000],
            "source_board": "greenhouse",
            "external_id": str(raw.get("id", "")),
            "posted_at": raw.get("updated_at"),
        }


# ---------------------------------------------------------------------------
# Lever Scraper
# Public API — most companies have migrated away, but some remain.
# ---------------------------------------------------------------------------

class LeverScraper:
    """Scrape jobs from Lever postings. FREE public API."""

    BASE_URL = "https://api.lever.co/v0/postings"

    def __init__(self):
        self.client = httpx.Client(
            timeout=15.0,
            headers={"User-Agent": "JobScout/1.0"},
        )

    def get_jobs(self, company_slug: str) -> List[Dict]:
        url = f"{self.BASE_URL}/{company_slug}"
        try:
            response = self.client.get(url)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                return []
            # Skip "we moved" placeholder postings
            real_jobs = [j for j in data if "moved" not in j.get("text", "").lower() or len(data) > 2]
            return [self._parse_job(j, company_slug) for j in real_jobs]
        except httpx.HTTPStatusError:
            return []
        except Exception:
            return []

    def _parse_job(self, raw: Dict, company_slug: str) -> Dict:
        title = raw.get("text", "")
        categories = raw.get("categories", {})
        location = categories.get("location", "") or raw.get("workplaceType", "")

        description_parts = []
        for section in raw.get("lists", []):
            description_parts.append(section.get("text", ""))
            for item in section.get("content", "").split("<li>"):
                clean = re.sub(r"<[^>]+>", "", item).strip()
                if clean:
                    description_parts.append(clean)

        additional = raw.get("additional", "")
        if additional:
            description_parts.append(re.sub(r"<[^>]+>", " ", additional))

        description = re.sub(r"\s+", " ", " ".join(description_parts)).strip()

        return {
            "title": title,
            "company_name": company_slug.replace("-", " ").replace("_", " ").title(),
            "company_slug": company_slug,
            "location": location,
            "is_remote": _is_remote(location, title, description),
            "apply_url": raw.get("hostedUrl", f"https://jobs.lever.co/{company_slug}/{raw.get('id')}"),
            "description": description[:5000],
            "source_board": "lever",
            "external_id": raw.get("id", ""),
            "posted_at": None,
        }


# ---------------------------------------------------------------------------
# Ashby Scraper — Updated GraphQL schema (March 2026)
# ---------------------------------------------------------------------------

class AshbyScraper:
    """Scrape jobs from Ashby job boards. FREE public GraphQL API."""

    API_URL = "https://jobs.ashbyhq.com/api/non-user-graphql"

    QUERY = """
        query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
            jobBoard: jobBoardWithTeams(
                organizationHostedJobsPageName: $organizationHostedJobsPageName
            ) {
                teams {
                    id
                    name
                    parentTeamId
                }
                jobPostings {
                    id
                    title
                    teamId
                    locationId
                    locationName
                    employmentType
                    workplaceType
                    compensationTierSummary
                }
            }
        }
    """

    def __init__(self):
        self.client = httpx.Client(
            timeout=15.0,
            headers={
                "User-Agent": "JobScout/1.0",
                "Content-Type": "application/json",
            },
        )

    def get_jobs(self, company_slug: str) -> List[Dict]:
        """Fetch all jobs for a company from Ashby via GraphQL."""
        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "variables": {"organizationHostedJobsPageName": company_slug},
            "query": self.QUERY,
        }

        try:
            response = self.client.post(self.API_URL, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("errors"):
                return []

            job_board = data.get("data", {}).get("jobBoard")
            if not job_board:
                return []

            # Build team lookup
            teams = {t["id"]: t["name"] for t in job_board.get("teams", [])}

            jobs = []
            for raw_job in job_board.get("jobPostings", []):
                team_name = teams.get(raw_job.get("teamId"), "")
                jobs.append(self._parse_job(raw_job, company_slug, team_name))
            return jobs

        except Exception:
            return []

    def _parse_job(self, raw: Dict, company_slug: str, team_name: str) -> Dict:
        title = raw.get("title", "")
        location = raw.get("locationName", "")
        workplace = raw.get("workplaceType", "")
        compensation = raw.get("compensationTierSummary", "")

        # Ashby uses workplaceType enum: "Remote", "Hybrid", "On-site"
        is_remote = (workplace.lower() == "remote") or _is_remote(location, title, "")

        return {
            "title": title,
            "company_name": company_slug.replace("-", " ").replace("_", " ").title(),
            "company_slug": company_slug,
            "location": f"{location} ({workplace})" if workplace else location,
            "is_remote": is_remote,
            "apply_url": f"https://jobs.ashbyhq.com/{company_slug}/{raw.get('id')}",
            "description": f"Team: {team_name}. Compensation: {compensation}" if compensation else f"Team: {team_name}",
            "source_board": "ashby",
            "external_id": raw.get("id", ""),
            "posted_at": None,
            "team": team_name,
            "employment_type": raw.get("employmentType", ""),
            "compensation": compensation,
        }


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def _is_remote(location: str, title: str, description: str) -> bool:
    """Check if a job is remote based on location/title/description."""
    text = f"{location} {title} {description}".lower()
    remote_keywords = [
        "remote", "worldwide", "anywhere", "work from home",
        "distributed", "global", "wfh", "fully remote",
    ]
    return any(kw in text for kw in remote_keywords)


# ---------------------------------------------------------------------------
# Keyword Filter
# ---------------------------------------------------------------------------

def matches_criteria(job: Dict, criteria: Dict) -> bool:
    """
    Check if a job matches user criteria.

    criteria = {
        "title_keywords": ["backend", "developer", "engineer", "python", "go"],
        "required_skills": ["python", "go", "postgresql", "django", "fastapi"],
        "exclude_keywords": ["senior staff", "principal", "director", "vp"],
        "remote_only": True,
        "max_yoe": 5,
    }
    """
    from worker.scraping.dedup import is_globally_remote

    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    location = (job.get("location") or "").lower()
    text = f"{title} {description} {location}"

    # Remote filter
    if criteria.get("remote_only") and not job.get("is_remote"):
        return False

    # Global remote filter (exclude US-only, India-based)
    if criteria.get("global_remote_only") and not is_globally_remote(job):
        return False

    # Title must match at least one keyword
    title_keywords = criteria.get("title_keywords", [])
    if title_keywords:
        if not any(kw.lower() in title for kw in title_keywords):
            return False

    # Exclude keywords
    exclude = criteria.get("exclude_keywords", [])
    if exclude:
        if any(kw.lower() in title for kw in exclude):
            return False

    # Skills: at least one required skill mentioned in title or description
    skills = criteria.get("required_skills", [])
    if skills:
        if not any(skill.lower() in text for skill in skills):
            return False

    # YOE filter
    max_yoe = criteria.get("max_yoe")
    if max_yoe is not None:
        yoe_patterns = re.findall(r"(\d+)\+?\s*(?:years|yrs)", description)
        if yoe_patterns:
            min_mentioned = min(int(y) for y in yoe_patterns)
            if min_mentioned > max_yoe:
                return False

    return True


# ---------------------------------------------------------------------------
# Slug Lists — Verified active as of early 2026
# Focus: startups, remote-friendly, dev-hiring
# ---------------------------------------------------------------------------

GREENHOUSE_SLUGS = [
    # Verified active with >0 jobs
    "axiom", "buildkite", "chainguard", "clickhouse", "cockroachlabs",
    "cribl", "encore", "fastly", "figma", "vercel",
    # Likely active (popular dev-tool companies on Greenhouse)
    "grafana", "posthog", "snyk", "datadoghq", "drata",
    "temporal", "rudderstack", "semgrep", "livekit", "deepgram",
    "dopplerhq", "cal-com", "prisma", "planetscale", "tinybird",
    "redpanda-data", "materialize", "edgedb", "turso", "xata",
    "novu", "inngest", "trigger-dev", "windmill-dev", "infisical",
    "mintlify", "appsmith", "baserow", "metabase", "retool",
    "hasura", "supabase", "nhost", "clerk", "stytch",
    "replicate", "modal-labs", "fireworks-ai", "bentoml",
    "deno", "fly", "railway", "render", "stackblitz",
    "zed-industries", "gitpod", "codesandbox", "replicatedhq",
    "teleport", "localstack", "steampipe", "onepassword",
    "langchain", "dagster", "prefect", "resend", "svix",
    "hookdeck", "knock", "permit-io", "unkey", "upstash",
    "tigerbeetle", "typesense", "cloudquery", "betterstack",
    "highlight-io", "incident-io", "komodor", "groundcover",
    "foxglove", "formkit", "liveblocks", "whimsical",
]

LEVER_SLUGS = [
    # Verified still active on Lever (most companies migrated away)
    "plaid", "neon", "mistral",
    # May still be active
    "timescale", "wealthsimple", "braze", "contentful",
    "benchling", "labelbox", "hex", "hightouch",
    "meilisearch", "questdb", "parseable", "peerdb",
]

ASHBY_SLUGS = [
    # Verified active with updated GraphQL schema
    "ramp", "notion", "figma", "verkada", "anthropic",
    # Likely active
    "airbyte", "aiven", "alchemy", "baseten",
    "cal-com", "chainguard", "chronosphere", "commonroom",
    "dagger", "dagster", "dbt-labs", "deepinfra",
    "fern", "fivetran", "fly-io", "goldsky",
    "gitpod", "grafana", "incident", "inngest",
    "knock", "lago", "langchain", "linear", "liveblocks",
    "mintlify", "mixpanel", "modal", "nango", "netbird",
    "onepassword", "permit", "plane", "plausible",
    "railway", "readme", "redpanda", "render", "replicate",
    "resend", "retool", "sequin", "snyk", "stytch",
    "supabase", "teleport", "temporal", "tigerbeetle",
    "tinybird", "trigger", "turso", "unkey", "upstash",
    "vercel", "vitally", "warp", "windmill", "xata", "zed",
    "anyscale", "coreweave", "sambanova",
]


def get_slugs_from_db(db, ats_type: str) -> List[str]:
    """Get company slugs from the database for a given ATS type."""
    companies = db.get_companies(active_only=True, limit=5000)
    slugs = []

    url_patterns = {
        "greenhouse": r"boards\.greenhouse\.io/([^/]+)",
        "lever": r"jobs\.lever\.co/([^/]+)",
        "ashby": r"jobs\.ashbyhq\.com/([^/]+)",
    }

    pattern = url_patterns.get(ats_type)
    if not pattern:
        return []

    for c in companies:
        if c.get("ats_type") != ats_type:
            continue
        career_url = c.get("career_url", "") or ""
        match = re.search(pattern, career_url)
        if match:
            slugs.append(match.group(1))

    return list(set(slugs))


def get_all_slugs(db, ats_type: str) -> List[str]:
    """Combine DB slugs + hardcoded slugs, deduplicated."""
    hardcoded = {
        "greenhouse": GREENHOUSE_SLUGS,
        "lever": LEVER_SLUGS,
        "ashby": ASHBY_SLUGS,
    }

    db_slugs = get_slugs_from_db(db, ats_type)
    all_slugs = list(set(db_slugs + hardcoded.get(ats_type, [])))
    return all_slugs


# ---------------------------------------------------------------------------
# Unified Job Pipeline
# ---------------------------------------------------------------------------

def to_db_job(job: Dict, company_id: Optional[str] = None) -> Dict:
    """Convert a scraped job to the DB jobs table format."""
    from worker.scraping.dedup import generate_job_fingerprint

    title = job.get("title", "")[:500]
    company_name = job.get("company_name", "")
    fingerprint = generate_job_fingerprint(title, company_name) if company_name else None

    return {
        "company_id": company_id,
        "title": title,
        "location": job.get("location", "")[:500],
        "is_remote": job.get("is_remote", False),
        "apply_url": job.get("apply_url", ""),
        "source_board": job.get("source_board", "unknown"),
        "fingerprint": fingerprint,
        "match_score": 0,
        "is_new": True,
        "is_recommended": False,
        "discovered_date": date.today().isoformat(),
        "discovered_at": datetime.now().isoformat(),
    }


def scrape_ats_jobs(
    db,
    ats_types: List[str] = None,
    criteria: Dict = None,
    max_slugs_per_ats: int = None,
    progress_callback=None,
) -> Dict:
    """
    Main entry point: scrape jobs from ATS boards, filter, save to DB.

    Returns:
        {"total_scraped": int, "matched": int, "saved": int, "errors": int, "by_ats": {}}
    """
    if ats_types is None:
        ats_types = ["greenhouse", "lever", "ashby"]

    if criteria is None:
        criteria = {
            "title_keywords": ["backend", "developer", "engineer", "software", "python", "golang", "full stack", "fullstack"],
            "required_skills": [],
            "exclude_keywords": ["staff", "principal", "director", "vp", "head of", "lead architect"],
            "remote_only": True,
            "max_yoe": 5,
        }

    scrapers = {
        "greenhouse": GreenhouseScraper(),
        "lever": LeverScraper(),
        "ashby": AshbyScraper(),
    }

    stats = {"total_scraped": 0, "matched": 0, "saved": 0, "errors": 0, "by_ats": {}}

    for ats_type in ats_types:
        scraper = scrapers.get(ats_type)
        if not scraper:
            continue

        slugs = get_all_slugs(db, ats_type)
        if max_slugs_per_ats:
            slugs = slugs[:max_slugs_per_ats]

        ats_stats = {"scraped": 0, "matched": 0, "saved": 0}

        if progress_callback:
            progress_callback(f"Scraping {ats_type}: {len(slugs)} companies...", 0)

        for i, slug in enumerate(slugs):
            try:
                jobs = scraper.get_jobs(slug)
                ats_stats["scraped"] += len(jobs)

                # Filter
                matching = [j for j in jobs if matches_criteria(j, criteria)]
                ats_stats["matched"] += len(matching)

                # Save to DB
                for job in matching:
                    company_defaults = {
                        "career_url": job.get("apply_url", "").rsplit("/", 1)[0] if "/" in job.get("apply_url", "") else None,
                        "ats_type": ats_type,
                    }
                    company_id = db.find_or_create_company(
                        job["company_name"], defaults=company_defaults
                    )
                    db_job = to_db_job(job, company_id)
                    if db.upsert_job(db_job):
                        ats_stats["saved"] += 1

                # Rate limiting between companies
                if i < len(slugs) - 1:
                    time.sleep(0.2)

            except Exception as e:
                stats["errors"] += 1
                print(f"  Error scraping {slug}: {e}")

            if progress_callback and len(slugs) > 0:
                progress_callback(
                    f"Scraping {ats_type}: {slug} ({i+1}/{len(slugs)}) — {ats_stats['matched']} matches",
                    (i + 1) / len(slugs),
                )

        stats["by_ats"][ats_type] = ats_stats
        stats["total_scraped"] += ats_stats["scraped"]
        stats["matched"] += ats_stats["matched"]
        stats["saved"] += ats_stats["saved"]

        print(f"\n{ats_type}: scraped={ats_stats['scraped']}, matched={ats_stats['matched']}, saved={ats_stats['saved']}")

    return stats
