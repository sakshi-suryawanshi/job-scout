# job_scout/enrichment/filters.py
# Single canonical matches_criteria function — extracted from board_scrapers & ats_scrapers.
"""
Job filtering: keyword match, remote, YOE, salary.
"""

import re
from typing import Dict


def matches_criteria(job: Dict, criteria: Dict) -> bool:
    """
    Return True if job passes all criteria filters.

    criteria keys:
      title_keywords   list[str]  — at least one must appear in title
      required_skills  list[str]  — at least one must appear in title+description
      exclude_keywords list[str]  — none may appear in title
      remote_only      bool
      global_remote_only bool
      max_yoe          int|None
      min_salary       int|None
      max_salary       int|None
    """
    from job_scout.enrichment.dedup import is_globally_remote

    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    location = (job.get("location") or "").lower()
    text = f"{title} {description} {location}"

    if criteria.get("remote_only") and not job.get("is_remote"):
        return False

    if criteria.get("global_remote_only") and not is_globally_remote(job):
        return False

    title_keywords = criteria.get("title_keywords", [])
    if title_keywords:
        if not any(kw.lower() in title for kw in title_keywords):
            return False

    exclude = criteria.get("exclude_keywords", [])
    if exclude:
        if any(kw.lower() in title for kw in exclude):
            return False

    skills = criteria.get("required_skills", [])
    if skills:
        if not any(skill.lower() in text for skill in skills):
            return False

    max_yoe = criteria.get("max_yoe")
    if max_yoe is not None:
        yoe_patterns = re.findall(r"(\d+)\+?\s*(?:years|yrs)", description)
        if yoe_patterns:
            min_mentioned = min(int(y) for y in yoe_patterns)
            if min_mentioned > max_yoe:
                return False

    min_salary = criteria.get("min_salary")
    max_salary = criteria.get("max_salary")
    if min_salary and job.get("salary_max") and job["salary_max"] < min_salary:
        return False
    if max_salary and job.get("salary_min") and job["salary_min"] > max_salary:
        return False

    return True
