# job_scout/enrichment/dedup.py
# Moved from worker/scraping/dedup.py — single canonical dedup implementation.
"""
Job deduplication and global-remote filtering utilities.
"""

import hashlib
import re
from typing import Dict


_COMPANY_SUFFIXES = re.compile(
    r"\b(inc\.?|ltd\.?|llc|co\.?|corp\.?|gmbh|pvt\.?|pte\.?|pty\.?|limited|incorporated)\b",
    re.IGNORECASE,
)

_YC_BATCH = re.compile(r"\((?:YC\s*)?[WSF]\d{2}\)", re.IGNORECASE)


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, remove company suffixes."""
    text = (text or "").lower().strip()
    text = _COMPANY_SUFFIXES.sub("", text)
    text = _YC_BATCH.sub("", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def generate_job_fingerprint(title: str, company_name: str) -> str:
    """SHA256 fingerprint from normalized title + company name."""
    norm_title = normalize_text(title)
    norm_company = normalize_text(company_name)
    raw = f"{norm_company}::{norm_title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


_REJECT_PATTERNS = re.compile(
    r"("
    r"us\s+only|usa\s+only|united\s+states\s+only|u\.s\.\s+only"
    r"|us[- ]based\s+only|must\s+be\s+(in\s+the\s+us|authorized\s+to\s+work\s+in\s+the\s+u)"
    r"|us\s+citizens?\s+only|us\s+work\s+authorization\s+required"
    r"|uk\s+only|eu\s+only|canada\s+only|emea\s+only|apac\s+only"
    r")",
    re.IGNORECASE,
)

_INDIA_LOCATIONS = re.compile(
    r"\b("
    r"india|bangalore|bengaluru|hyderabad|mumbai|pune|chennai"
    r"|noida|gurgaon|gurugram|kolkata|delhi|ahmedabad|jaipur"
    r")\b",
    re.IGNORECASE,
)

_GLOBAL_ACCEPT = re.compile(
    r"("
    r"worldwide|anywhere|global(ly)?\s*remote|remote\s*[\-—]\s*worldwide"
    r"|remote\s*\(global\)|work\s+from\s+anywhere|fully\s+distributed"
    r"|remote\s*[\-—]\s*anywhere"
    r")",
    re.IGNORECASE,
)


def is_globally_remote(job: Dict) -> bool:
    """
    Returns True if the job is genuinely globally remote.
    Returns False for US-only, India-based, or region-locked roles.
    """
    location = (job.get("location") or "").strip()
    title = job.get("title") or ""
    description = job.get("description") or ""
    text = f"{location} {title} {description}"

    if _REJECT_PATTERNS.search(text):
        return False

    if _INDIA_LOCATIONS.search(location):
        return False

    if _GLOBAL_ACCEPT.search(text):
        return True

    loc_lower = location.lower().strip()
    if job.get("is_remote") and loc_lower in ("", "remote", "remote job", "unknown"):
        return True

    if job.get("is_remote"):
        return True

    return False
