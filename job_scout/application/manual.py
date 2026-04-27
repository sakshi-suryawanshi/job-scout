# job_scout/application/manual.py
"""
Tier 2 — Semi-automation for ATS platforms we don't have full form-fillers for
(Workday, Workable, SmartRecruiters, custom forms).

Behavior:
- Pre-tailors resume + generates cover letter
- Returns all pre-filled values in a structured dict
- The UI (Jobs page) presents these as a side panel so the user copy-pastes
- User clicks Submit themselves (~20 seconds instead of 3 minutes)
"""

import os
from typing import Dict, Optional

from job_scout.application.base import ApplyResult, load_applicant_profile


def prepare_manual_apply(
    job: Dict,
    resume_text: str,
    profile: Optional[Dict] = None,
) -> ApplyResult:
    """
    Prepare everything needed for a semi-manual application.
    No browser launched. Returns pre-filled values for the UI to display.
    """
    if profile is None:
        profile = load_applicant_profile()

    company_info = job.get("companies", {}) or {}
    company_name = company_info.get("name", "") or job.get("company_name", "Unknown")

    # Generate cover letter with Gemini if available
    cover_letter = ""
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key and resume_text:
        try:
            from job_scout.ai.gemini import GeminiClient, tailor_resume
            gemini = GeminiClient(gemini_key)
            cover_letter = _generate_cover_letter(gemini, job, resume_text)
        except Exception as e:
            print(f"cover letter generation error: {e}")

    return ApplyResult(
        status="needs_attention",
        tier=2,
        apply_url=job.get("apply_url", ""),
        cover_letter=cover_letter,
        notes=f"Semi-auto: pre-filled values ready for {company_name}. Open URL and paste.",
    )


def _generate_cover_letter(gemini, job: Dict, resume_text: str) -> str:
    company_info = job.get("companies", {}) or {}
    company_name = company_info.get("name", "") or job.get("company_name", "Unknown")
    title = job.get("title", "Unknown")

    prompt = f"""Write a concise, professional cover letter for this job application.

Job: {title}
Company: {company_name}
Location: {job.get('location', 'Remote')}

Resume summary (first 1500 chars):
{resume_text[:1500]}

Rules:
- 3 short paragraphs (opening, fit, close)
- No fluff, no generic phrases
- Mention specific role title and company name
- Under 200 words
- Plain text only, no markdown

Cover letter:"""

    try:
        result = gemini.generate(prompt, max_tokens=400)
        return result or ""
    except Exception:
        return ""
