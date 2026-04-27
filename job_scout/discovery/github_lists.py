# job_scout/discovery/github_lists.py
"""
Import companies from open-source remote-job lists on GitHub.
Primary: remoteintech/remote-jobs README.md — 700+ globally remote companies.
"""

import re
import httpx
from typing import List, Dict


_README_URL = "https://raw.githubusercontent.com/remoteintech/remote-jobs/main/README.md"

# Only keep entries with one of these region labels
_GLOBAL_REGIONS = re.compile(
    r"\b(worldwide|global|anywhere|remote|international)\b",
    re.IGNORECASE,
)

_TABLE_ROW = re.compile(
    r"^\|\s*\[(?P<name>[^\]]+)\]\((?P<url>https?://[^)]+)\)\s*\|"
    r"\s*(?P<region>[^|]*?)\s*\|",
    re.MULTILINE,
)


def fetch_remoteintech(filter_global: bool = True) -> List[Dict]:
    """
    Fetch remoteintech/remote-jobs list from GitHub.
    Returns list of company dicts ready for db.add_companies_bulk().

    Args:
        filter_global: If True, only return companies with a global/worldwide region tag.
                       Set False to import everything (includes US-only entries).
    """
    try:
        client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/2.0"})
        response = client.get(_README_URL)
        response.raise_for_status()
        text = response.text
    except Exception as e:
        print(f"remoteintech fetch error: {e}")
        return []

    companies = []
    for match in _TABLE_ROW.finditer(text):
        name = match.group("name").strip()
        url = match.group("url").strip()
        region = match.group("region").strip()

        if not name or not url:
            continue

        if filter_global and not _GLOBAL_REGIONS.search(region):
            continue

        domain = url.replace("https://", "").replace("http://", "").rstrip("/").split("/")[0]
        career_url = f"https://{domain}/careers"

        companies.append({
            "name": name,
            "website": url,
            "career_url": career_url,
            "ats_type": "unknown",
            "source": "remoteintech_github",
            "is_active": True,
            "priority_score": 7,
            "notes": f"Region: {region}" if region else None,
        })

    print(f"remoteintech/remote-jobs: {len(companies)} globally remote companies found")
    return companies


def import_remoteintech_to_db(db, filter_global: bool = True) -> Dict:
    """Fetch remoteintech list and insert new companies into DB. Returns stats."""
    companies = fetch_remoteintech(filter_global=filter_global)
    if not companies:
        return {"found": 0, "new": 0, "inserted": 0}

    existing = db.get_companies(active_only=False, limit=10000)
    existing_names = {c["name"].lower() for c in existing}

    new = [c for c in companies if c["name"].lower() not in existing_names]
    inserted = db.add_companies_bulk(new) if new else 0

    return {"found": len(companies), "new": len(new), "inserted": inserted}
