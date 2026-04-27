# worker/discovery/yc_scraper.py — backward-compat stub
# All logic now lives in job_scout/discovery/yc.py
from job_scout.discovery.yc import (  # noqa: F401
    YCScraper,
    YCScraperV2,       # alias
    fetch_yc_companies,
    fetch_yc_companies_v2,  # alias
)
