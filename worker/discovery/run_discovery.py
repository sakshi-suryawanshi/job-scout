# worker/discovery/run_discovery.py — backward-compat stub
# All logic now lives in job_scout/discovery/orchestrator.py
from job_scout.discovery.orchestrator import (  # noqa: F401
    run_yc_discovery,
    run_alternative_discovery,
    run_serper_discovery,
    run_full_discovery,
    _dedup_and_insert,
)
