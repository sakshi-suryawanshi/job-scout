# job_scout/enrichment/filters.py
# Single canonical matches_criteria function — extracted from board_scrapers & ats_scrapers.
"""
Job filtering: keyword match, remote, YOE, salary.
"""

import re
from typing import Dict


def _wb(needle: str, haystack: str) -> bool:
    """Case-insensitive whole-word/phrase match. Avoids 'engineer' matching
    'engineering manager' or 'lead' matching 'leadership'."""
    return bool(re.search(
        r"(?<![A-Za-z0-9])" + re.escape(needle) + r"(?![A-Za-z0-9])",
        haystack, re.IGNORECASE,
    ))


def matches_criteria(job: Dict, criteria: Dict) -> bool:
    """
    Return True if job passes all criteria filters.

    criteria keys:
      title_keywords      list[str]  — at least one must appear in title (word-boundary)
      must_have_skills    list[str]  — ALL must appear in title+description (word-boundary)
      nice_to_have_skills list[str]  — scored later, not used to filter here
      required_skills     list[str]  — legacy alias for nice_to_have_skills
      exclude_keywords    list[str]  — none may appear in title (word-boundary)
      remote_only         bool
      global_remote_only  bool
      max_yoe             int|None   — uses MAX of mentioned ranges (stricter than before)
      min_salary / max_salary int|None
    """
    from job_scout.enrichment.dedup import is_globally_remote

    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    text = f"{title} {description}"

    if criteria.get("remote_only") and not job.get("is_remote"):
        return False

    if criteria.get("global_remote_only") and not is_globally_remote(job):
        return False

    title_keywords = criteria.get("title_keywords", [])
    if title_keywords and not any(_wb(kw, title) for kw in title_keywords):
        return False

    exclude = criteria.get("exclude_keywords", [])
    if exclude and any(_wb(kw, title) for kw in exclude):
        return False

    # must_have_skills — ALL must be present (whole-word).
    must_have = criteria.get("must_have_skills") or []
    if must_have and not all(_wb(s, text) for s in must_have):
        return False

    max_yoe = criteria.get("max_yoe")
    if max_yoe is not None:
        # Use MAX of mentioned years (old impl used min, letting "3-8 years" leak past max=4).
        mentioned = re.findall(r"(\d+)\+?\s*(?:years?|yrs?)\b", description, re.IGNORECASE)
        if mentioned:
            try:
                max_mentioned = max(int(y) for y in mentioned)
                if max_mentioned > max_yoe + 1:
                    return False
            except ValueError:
                pass

    min_salary = criteria.get("min_salary")
    max_salary = criteria.get("max_salary")
    if min_salary and job.get("salary_max") and job["salary_max"] < min_salary:
        return False
    if max_salary and job.get("salary_min") and job["salary_min"] > max_salary:
        return False

    return True
