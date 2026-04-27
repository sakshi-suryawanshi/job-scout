# worker/ai/gemini_client.py — backward-compat stub
# All logic now lives in job_scout/ai/gemini.py
from job_scout.ai.gemini import (  # noqa: F401
    GeminiClient,
    get_gemini_usage_today,
    parse_career_page_with_ai,
    score_job_with_ai,
    score_jobs_batch,
    score_job_rule_based,
    score_all_jobs,
    tailor_resume,
    fetch_job_description,
    generate_resume_html,
    SCORING_PROMPT,
    TAILOR_PROMPT,
)
