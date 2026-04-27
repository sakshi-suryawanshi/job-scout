# job_scout/scraping/ats/greenhouse.py
"""Greenhouse ATS scraper — free public API."""

import httpx
import re
from typing import List, Dict
from job_scout.scraping.base import is_remote

GREENHOUSE_SLUGS = [
    "axiom", "buildkite", "chainguard", "clickhouse", "cockroachlabs",
    "cribl", "encore", "fastly", "figma", "vercel",
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


class GreenhouseScraper:
    """Scrape jobs from Greenhouse boards. FREE public API."""

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self):
        self.client = httpx.Client(timeout=15.0, headers={"User-Agent": "JobScout/1.0"})

    def get_jobs(self, company_slug: str) -> List[Dict]:
        url = f"{self.BASE_URL}/{company_slug}/jobs"
        try:
            response = self.client.get(url, params={"content": "true"})
            if response.status_code == 404:
                return []
            response.raise_for_status()
            jobs = response.json().get("jobs", [])
            return [self._parse_job(j, company_slug) for j in jobs]
        except Exception:
            return []

    def _parse_job(self, raw: Dict, company_slug: str) -> Dict:
        location = raw.get("location", {}).get("name", "")
        title = raw.get("title", "")
        content = raw.get("content", "")
        description = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", content)).strip()

        return {
            "title": title,
            "company_name": company_slug.replace("-", " ").replace("_", " ").title(),
            "company_slug": company_slug,
            "location": location,
            "is_remote": is_remote(location, title, description),
            "apply_url": raw.get("absolute_url", f"https://boards.greenhouse.io/{company_slug}/jobs/{raw.get('id')}"),
            "description": description[:5000],
            "source_board": "greenhouse",
            "external_id": str(raw.get("id", "")),
            "posted_at": raw.get("updated_at"),
        }
