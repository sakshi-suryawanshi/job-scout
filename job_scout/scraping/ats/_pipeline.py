# job_scout/scraping/ats/_pipeline.py
"""ATS scraping pipeline: slug resolution + unified scrape_ats_jobs entrypoint."""

import re
import time
from typing import List, Dict

from job_scout.scraping.ats.greenhouse import GreenhouseScraper, GREENHOUSE_SLUGS
from job_scout.scraping.ats.lever import LeverScraper, LEVER_SLUGS
from job_scout.scraping.ats.ashby import AshbyScraper, ASHBY_SLUGS
from job_scout.scraping.base import to_db_job
from job_scout.enrichment.filters import matches_criteria


def get_slugs_from_db(db, ats_type: str) -> List[str]:
    """Extract company slugs from DB career URLs for a given ATS type."""
    url_patterns = {
        "greenhouse": r"boards\.greenhouse\.io/([^/]+)",
        "lever": r"jobs\.lever\.co/([^/]+)",
        "ashby": r"jobs\.ashbyhq\.com/([^/]+)",
    }
    pattern = url_patterns.get(ats_type)
    if not pattern:
        return []

    companies = db.get_companies(active_only=True, limit=5000)
    slugs = []
    for c in companies:
        if c.get("ats_type") != ats_type:
            continue
        career_url = c.get("career_url", "") or ""
        match = re.search(pattern, career_url)
        if match:
            slugs.append(match.group(1))
    return list(set(slugs))


def get_all_slugs(db, ats_type: str) -> List[str]:
    """Merge DB slugs with hardcoded slug lists, deduplicated."""
    hardcoded = {
        "greenhouse": GREENHOUSE_SLUGS,
        "lever": LEVER_SLUGS,
        "ashby": ASHBY_SLUGS,
    }
    db_slugs = get_slugs_from_db(db, ats_type)
    return list(set(db_slugs + hardcoded.get(ats_type, [])))


_DEFAULT_CRITERIA = {
    "title_keywords": ["backend", "developer", "engineer", "software", "python", "golang", "full stack", "fullstack"],
    "required_skills": [],
    "exclude_keywords": ["staff", "principal", "director", "vp", "head of", "lead architect"],
    "remote_only": True,
    "max_yoe": 5,
}


def scrape_ats_jobs(
    db,
    ats_types: List[str] = None,
    criteria: Dict = None,
    max_slugs_per_ats: int = None,
    progress_callback=None,
) -> Dict:
    """
    Main entry: scrape ATS boards, filter, save to DB.
    Returns {"total_scraped", "matched", "saved", "errors", "by_ats"}.
    """
    if ats_types is None:
        ats_types = ["greenhouse", "lever", "ashby"]
    if criteria is None:
        criteria = _DEFAULT_CRITERIA

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

                matching = [j for j in jobs if matches_criteria(j, criteria)]
                ats_stats["matched"] += len(matching)

                for job in matching:
                    company_defaults = {
                        "career_url": job.get("apply_url", "").rsplit("/", 1)[0] if "/" in job.get("apply_url", "") else None,
                        "ats_type": ats_type,
                    }
                    company_id = db.find_or_create_company(job["company_name"], defaults=company_defaults)
                    db_job = to_db_job(job, company_id)
                    if db.upsert_job(db_job):
                        ats_stats["saved"] += 1

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
