# worker/discovery/serper_dorking.py — backward-compat stub
# All logic now lives in job_scout/discovery/serper_dorking.py
from job_scout.discovery.serper_dorking import (  # noqa: F401
    SerperDorker, DORK_QUERIES,
    fetch_serper_companies,
    parse_serper_result_as_job,
    create_signal_from_result,
    get_serper_usage,
    is_category_on_cooldown,
    CATEGORY_COOLDOWNS,
)
