# worker/scraping/dedup.py — backward-compat stub
# All logic now lives in job_scout/enrichment/dedup.py
from job_scout.enrichment.dedup import (  # noqa: F401
    normalize_text,
    generate_job_fingerprint,
    is_globally_remote,
)
