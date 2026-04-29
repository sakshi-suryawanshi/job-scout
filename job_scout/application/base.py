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


_CTRL_CHARS = re.compile(r"[\x00-\x1f\x7f]")  # strips all ASCII control chars incl. \r \n \t


def _sanitize(value: str) -> str:
    """Strip control characters that Playwright could emit as keystrokes.
    Preserves normal whitespace (space, tab in URLs, newline in multi-line fields is
    handled by Playwright .fill() which replaces the field value atomically anyway).
    """
    return _CTRL_CHARS.sub("", (value or "")).strip()


def load_applicant_profile() -> Dict:
    """
    Load personal details used to fill application forms.
    Read from env vars — never stored in DB.
    All fields are sanitized to prevent control-character injection via Playwright.

    Required env vars:
      APPLY_FIRST_NAME, APPLY_LAST_NAME, APPLY_EMAIL
    Optional:
      APPLY_PHONE, APPLY_LINKEDIN, APPLY_GITHUB, APPLY_PORTFOLIO, APPLY_LOCATION
    """
    fn = _sanitize(os.getenv("APPLY_FIRST_NAME", ""))
    ln = _sanitize(os.getenv("APPLY_LAST_NAME", ""))
    return {
        "first_name":    fn,
        "last_name":     ln,
        "full_name":     f"{fn} {ln}".strip(),
        "email":         _sanitize(os.getenv("APPLY_EMAIL", "")),
        "phone":         _sanitize(os.getenv("APPLY_PHONE", "")),
        "linkedin_url":  _sanitize(os.getenv("APPLY_LINKEDIN", "")),
        "github_url":    _sanitize(os.getenv("APPLY_GITHUB", "")),
        "portfolio_url": _sanitize(os.getenv("APPLY_PORTFOLIO", "")),
        "location":      _sanitize(os.getenv("APPLY_LOCATION", "Remote")),
    }


_RESUME_PDF_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "resume.pdf",
)


def resume_pdf_path() -> str:
    """Return the path where the uploaded PDF resume is stored, or '' if not present."""
    return _RESUME_PDF_PATH if os.path.exists(_RESUME_PDF_PATH) else ""


def write_resume_tempfile(resume_text: str, suffix: str = ".txt") -> str:
    """Write resume to a named temp file for Playwright to attach.

    Priority:
      1. If data/resume.pdf exists → always attach the real PDF (no suffix override needed).
         ATS forms accept PDFs; this is the cleanest upload.
      2. Otherwise fall back to writing resume_text as a .txt file.

    Callers always pass resume_text as a safety net; if the PDF is on disk it takes precedence.
    """
    # Always prefer the stored PDF when it exists — attach the real file to ATS forms
    if os.path.exists(_RESUME_PDF_PATH):
        import shutil
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.close()
        shutil.copy2(_RESUME_PDF_PATH, tmp.name)
        return tmp.name

    # Fallback: write the text content (from .tex extraction or plain paste)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
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
