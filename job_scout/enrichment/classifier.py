# job_scout/enrichment/classifier.py
"""
Multi-label job classifier — assigns categories to the job_categories table.
Categories: desperation, startup, funding, hidden_gem, regional, yc, asap,
            salary_transparent, recommended
All rule-based (no AI cost).
"""

import re
from datetime import datetime, date
from typing import Dict, List


_SALARY_PATTERN = re.compile(r"\$\s*\d{2,3}[,k]", re.IGNORECASE)

_FUNDING_KEYWORDS = re.compile(
    r"\b(raised|series\s+[abc]|seed\s+round|pre-seed|just\s+funded|recently\s+funded"
    r"|backed\s+by|investors|venture|vc[- ]backed)\b",
    re.IGNORECASE,
)

_YC_PATTERN = re.compile(r"\bYC\s*[WS]\d{2}\b|\bY\s*Combinator\b", re.IGNORECASE)

_ASAP_PATTERN = re.compile(
    r"\b(asap|urgent|immediately|start\s+now|hire\s+fast|right\s+away)\b",
    re.IGNORECASE,
)

_HIDDEN_GEM_REGIONS = re.compile(
    r"\b(africa|kenya|nigeria|ghana|ethiopia|egypt|rwanda"
    r"|southeast\s+asia|indonesia|philippines|vietnam|thailand"
    r"|latin\s+america|brazil|colombia|argentina|mexico"
    r"|eastern\s+europe|poland|estonia|latvia|ukraine"
    r"|south\s+asia(?!\s+remote)|bangladesh|sri\s+lanka)\b",
    re.IGNORECASE,
)

_REGIONAL_KEYWORDS = re.compile(
    r"\b(japan|south\s+korea|singapore|taiwan"
    r"|portugal|spain|netherlands|scandinavia"
    r"|dubai|uae|middle\s+east|israel)\b",
    re.IGNORECASE,
)


def classify_job(job: Dict, company: Dict = None) -> List[Dict]:
    """
    Return list of {category, confidence} dicts for a job.
    Caller is responsible for writing to job_categories table.
    """
    company = company or {}
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    location = (job.get("location") or "").lower()
    source = (job.get("source_board") or "").lower()
    notes = (company.get("notes") or "").lower()
    funding = (company.get("funding_stage") or "").lower()
    text = f"{title} {description} {location} {notes}"

    categories = []

    # desperation
    desp = job.get("desperation_score", 0) or 0
    if desp >= 50:
        categories.append({"category": "desperation", "confidence": round(desp / 100, 2)})
    elif desp >= 30:
        categories.append({"category": "desperation", "confidence": 0.4})

    # startup
    is_startup = (
        "startup" in text
        or _FUNDING_KEYWORDS.search(text)
        or funding in ("seed", "pre-seed", "pre_seed", "series_a")
        or (company.get("headcount") or 999) < 50
    )
    if is_startup:
        categories.append({"category": "startup", "confidence": 0.85})

    # funding
    if _FUNDING_KEYWORDS.search(text) or funding in ("seed", "pre-seed", "pre_seed", "series_a", "series_b"):
        categories.append({"category": "funding", "confidence": 0.9})

    # yc
    if _YC_PATTERN.search(text) or (company.get("source") or "") == "yc_directory":
        categories.append({"category": "yc", "confidence": 1.0})

    # asap
    if _ASAP_PATTERN.search(text):
        categories.append({"category": "asap", "confidence": 0.9})

    # salary_transparent
    sal_min = job.get("salary_min") or 0
    sal_max = job.get("salary_max") or 0
    if sal_min > 0 or sal_max > 0 or _SALARY_PATTERN.search(text):
        categories.append({"category": "salary_transparent", "confidence": 1.0})
    # Also flag salary-transparent boards
    if source in ("cord", "wellfound", "hired", "talentio", "pallet"):
        categories.append({"category": "salary_transparent", "confidence": 0.8})

    # hidden_gem (underserved regions)
    if _HIDDEN_GEM_REGIONS.search(text):
        categories.append({"category": "hidden_gem", "confidence": 0.8})

    # regional (niche markets)
    if _REGIONAL_KEYWORDS.search(text):
        categories.append({"category": "regional", "confidence": 0.75})

    # recommended (derived from match_score)
    score = job.get("match_score", 0) or 0
    if score >= 70:
        categories.append({"category": "recommended", "confidence": round(score / 100, 2)})

    # Deduplicate by category
    seen: set = set()
    unique = []
    for cat in categories:
        if cat["category"] not in seen:
            seen.add(cat["category"])
            unique.append(cat)

    return unique


def classify_jobs_bulk(db, jobs: List[Dict], progress_callback=None) -> Dict:
    """Classify a list of jobs and write results to job_categories. Returns stats."""
    stats = {"classified": 0, "categories_added": 0, "by_category": {}}

    for i, job in enumerate(jobs):
        company = None
        if job.get("company_id"):
            try:
                company = db.get_company_by_id(job["company_id"])
            except Exception:
                pass

        cats = classify_job(job, company)
        for cat_entry in cats:
            try:
                db._request("POST", "job_categories", json={
                    "job_id": job["id"],
                    "category": cat_entry["category"],
                    "confidence": cat_entry["confidence"],
                }, headers={**db.headers, "Prefer": "resolution=ignore-duplicates,return=minimal"})
                stats["categories_added"] += 1
                stats["by_category"][cat_entry["category"]] = stats["by_category"].get(cat_entry["category"], 0) + 1
            except Exception:
                pass

        if cats:
            stats["classified"] += 1

        if progress_callback:
            progress_callback(f"Classifying {i+1}/{len(jobs)}", (i + 1) / len(jobs))

    return stats
