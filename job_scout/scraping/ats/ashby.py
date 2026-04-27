# job_scout/scraping/ats/ashby.py
"""Ashby ATS scraper — free public GraphQL API."""

import httpx
from typing import List, Dict
from job_scout.scraping.base import is_remote

ASHBY_SLUGS = [
    "ramp", "notion", "figma", "verkada", "anthropic",
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

_QUERY = """
    query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
        jobBoard: jobBoardWithTeams(
            organizationHostedJobsPageName: $organizationHostedJobsPageName
        ) {
            teams { id name parentTeamId }
            jobPostings {
                id title teamId locationId locationName
                employmentType workplaceType compensationTierSummary
            }
        }
    }
"""


class AshbyScraper:
    """Scrape jobs from Ashby job boards. FREE public GraphQL API."""

    API_URL = "https://jobs.ashbyhq.com/api/non-user-graphql"

    def __init__(self):
        self.client = httpx.Client(
            timeout=15.0,
            headers={"User-Agent": "JobScout/1.0", "Content-Type": "application/json"},
        )

    def get_jobs(self, company_slug: str) -> List[Dict]:
        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "variables": {"organizationHostedJobsPageName": company_slug},
            "query": _QUERY,
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
            teams = {t["id"]: t["name"] for t in job_board.get("teams", [])}
            return [
                self._parse_job(j, company_slug, teams.get(j.get("teamId"), ""))
                for j in job_board.get("jobPostings", [])
            ]
        except Exception:
            return []

    def _parse_job(self, raw: Dict, company_slug: str, team_name: str) -> Dict:
        title = raw.get("title", "")
        location = raw.get("locationName", "")
        workplace = raw.get("workplaceType", "")
        compensation = raw.get("compensationTierSummary", "")

        return {
            "title": title,
            "company_name": company_slug.replace("-", " ").replace("_", " ").title(),
            "company_slug": company_slug,
            "location": f"{location} ({workplace})" if workplace else location,
            "is_remote": (workplace.lower() == "remote") or is_remote(location, title, ""),
            "apply_url": f"https://jobs.ashbyhq.com/{company_slug}/{raw.get('id')}",
            "description": f"Team: {team_name}. Compensation: {compensation}" if compensation else f"Team: {team_name}",
            "source_board": "ashby",
            "external_id": raw.get("id", ""),
            "posted_at": None,
            "team": team_name,
            "employment_type": raw.get("employmentType", ""),
            "compensation": compensation,
        }
