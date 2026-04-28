# job_scout/core/types.py
"""
TypedDicts for the core domain objects.

These are used for type-checking and documentation only — the actual data
travels as plain dicts from Supabase. TypedDicts ensure the expected shape
is stated explicitly rather than scattered in comments.
"""

from typing import List, Optional
from typing_extensions import TypedDict, NotRequired


class Company(TypedDict):
    id: str
    name: str
    career_url: str
    website: NotRequired[Optional[str]]
    ats_type: NotRequired[Optional[str]]        # greenhouse | lever | ashby | workable | custom
    ats_identifier: NotRequired[Optional[str]]  # slug / subdomain
    source: NotRequired[Optional[str]]
    is_active: NotRequired[bool]
    tags: NotRequired[Optional[List[str]]]


class Job(TypedDict):
    id: str
    company_id: NotRequired[Optional[str]]
    title: str
    location: NotRequired[Optional[str]]
    description: NotRequired[Optional[str]]
    apply_url: NotRequired[Optional[str]]
    is_remote: NotRequired[bool]
    source_board: NotRequired[Optional[str]]
    ats_type: NotRequired[Optional[str]]
    salary_min: NotRequired[Optional[int]]
    salary_max: NotRequired[Optional[int]]
    salary_currency: NotRequired[Optional[str]]
    match_score: NotRequired[Optional[int]]
    match_reason: NotRequired[Optional[str]]
    desperation_score: NotRequired[Optional[int]]
    user_action: NotRequired[Optional[str]]     # saved | applied | responded | interview | skip | needs_attention
    is_new: NotRequired[bool]
    fingerprint: NotRequired[Optional[str]]
    posted_at: NotRequired[Optional[str]]
    scraped_at: NotRequired[Optional[str]]


class Application(TypedDict):
    id: str
    job_id: str
    status: str                                 # applied | failed | needs_attention
    tier: NotRequired[Optional[int]]            # 1=playwright | 2=semi-auto | 3=email
    notes: NotRequired[Optional[str]]
    applied_at: NotRequired[Optional[str]]
    follow_up_at: NotRequired[Optional[str]]


class PipelineRun(TypedDict):
    id: str
    triggered_by: str                           # schedule | manual | api
    status: str                                 # running | success | partial | failed
    started_at: str
    finished_at: NotRequired[Optional[str]]
    stats: NotRequired[Optional[dict]]
    error_log: NotRequired[Optional[str]]


class ScoringCriteria(TypedDict):
    title_keywords: List[str]
    required_skills: List[str]
    exclude_keywords: List[str]
    remote_only: bool
    global_remote_only: bool
    max_yoe: int
    min_salary: NotRequired[Optional[int]]
