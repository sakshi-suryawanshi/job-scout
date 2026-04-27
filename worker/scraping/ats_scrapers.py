# worker/scraping/ats_scrapers.py — backward-compat stub
# All logic now lives in job_scout/scraping/ats/
from job_scout.scraping.ats import (  # noqa: F401
    GreenhouseScraper, GREENHOUSE_SLUGS,
    LeverScraper, LEVER_SLUGS,
    AshbyScraper, ASHBY_SLUGS,
    get_slugs_from_db, get_all_slugs, scrape_ats_jobs,
)
from job_scout.scraping.base import to_db_job  # noqa: F401
from job_scout.enrichment.filters import matches_criteria  # noqa: F401
