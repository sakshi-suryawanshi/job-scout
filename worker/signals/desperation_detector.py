# worker/signals/desperation_detector.py — backward-compat stub
# All logic now lives in job_scout/enrichment/desperation.py
from job_scout.enrichment.desperation import (  # noqa: F401
    compute_desperation_score,
    compute_desperation_for_jobs,
)
