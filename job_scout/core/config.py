# job_scout/core/config.py
"""
Central environment-variable and settings loader.

All code should import from here rather than calling os.getenv() directly,
so there is a single place to audit what the app requires.
"""

import os
from typing import Optional


def get(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read an env var, falling back to default."""
    return os.environ.get(key, default)


def require(key: str) -> str:
    """Read an env var; raise if absent."""
    val = os.environ.get(key)
    if not val:
        raise EnvironmentError(f"Required environment variable {key!r} is not set.")
    return val


# ── Supabase ──────────────────────────────────────────────────────────────────

def supabase_url() -> str:
    return require("SUPABASE_URL")


def supabase_key() -> str:
    return require("SUPABASE_KEY")


# ── AI / external APIs ────────────────────────────────────────────────────────

def gemini_api_key() -> Optional[str]:
    return get("GEMINI_API_KEY")


def serper_api_key() -> Optional[str]:
    return get("SERPER_API_KEY")


# ── Email ─────────────────────────────────────────────────────────────────────

def smtp_host() -> str:
    return get("SMTP_HOST", "smtp.gmail.com")


def smtp_port() -> int:
    return int(get("SMTP_PORT", "587"))


def smtp_user() -> Optional[str]:
    return get("GMAIL_USER") or get("SMTP_USER") or get("APPLY_EMAIL")


def smtp_password() -> Optional[str]:
    return get("GMAIL_APP_PASS") or get("SMTP_PASSWORD")


def digest_email() -> Optional[str]:
    return get("DIGEST_EMAIL")


# ── Application ───────────────────────────────────────────────────────────────

def apply_email() -> Optional[str]:
    return get("APPLY_EMAIL")


def apply_phone() -> Optional[str]:
    return get("APPLY_PHONE")


def apply_linkedin() -> Optional[str]:
    return get("APPLY_LINKEDIN")


def apply_github() -> Optional[str]:
    return get("APPLY_GITHUB")


# ── Pipeline ──────────────────────────────────────────────────────────────────

def pipeline_max_jobs() -> int:
    return int(get("PIPELINE_MAX_JOBS", "500"))


def pipeline_ats_slugs() -> int:
    return int(get("PIPELINE_ATS_SLUGS", "100"))


def serper_max_queries() -> int:
    return int(get("SERPER_MAX_Q", "3"))


# ── Feature flags ─────────────────────────────────────────────────────────────

def is_demo_mode() -> bool:
    return get("DEMO_MODE", "").lower() in ("1", "true", "yes")
