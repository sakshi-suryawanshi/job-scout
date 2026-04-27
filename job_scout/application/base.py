# job_scout/application/base.py
"""Shared types, utilities, and the ApplyResult protocol."""

import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import Optional, Dict


@dataclass
class ApplyResult:
    status: str             # 'applied' | 'failed' | 'skipped' | 'needs_attention'
    tier: int               # 1=auto, 2=semi, 3=email
    apply_url: str = ""
    screenshot_path: str = ""
    error: str = ""
    notes: str = ""
    cover_letter: str = ""


def load_applicant_profile() -> Dict:
    """
    Load personal details used to fill application forms.
    Read from env vars — never stored in DB.

    Required env vars:
      APPLY_FIRST_NAME, APPLY_LAST_NAME, APPLY_EMAIL
    Optional:
      APPLY_PHONE, APPLY_LINKEDIN, APPLY_GITHUB, APPLY_PORTFOLIO, APPLY_LOCATION
    """
    return {
        "first_name":    os.getenv("APPLY_FIRST_NAME", ""),
        "last_name":     os.getenv("APPLY_LAST_NAME", ""),
        "full_name":     f"{os.getenv('APPLY_FIRST_NAME', '')} {os.getenv('APPLY_LAST_NAME', '')}".strip(),
        "email":         os.getenv("APPLY_EMAIL", ""),
        "phone":         os.getenv("APPLY_PHONE", ""),
        "linkedin_url":  os.getenv("APPLY_LINKEDIN", ""),
        "github_url":    os.getenv("APPLY_GITHUB", ""),
        "portfolio_url": os.getenv("APPLY_PORTFOLIO", ""),
        "location":      os.getenv("APPLY_LOCATION", "Remote"),
    }


def write_resume_tempfile(resume_text: str, suffix: str = ".txt") -> str:
    """Write resume text to a named temp file. Caller must delete it."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    )
    tmp.write(resume_text)
    tmp.close()
    return tmp.name


def screenshots_dir() -> str:
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "screenshots",
    )
    os.makedirs(base, exist_ok=True)
    return base


def _clean_url(url: str) -> str:
    return (url or "").split("?")[0].rstrip("/")
