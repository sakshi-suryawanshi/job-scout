# job_scout/enrichment/desperation.py
# Moved from worker/signals/desperation_detector.py
"""Detect companies desperate to hire — these respond more often."""

import re
from datetime import datetime, date
from typing import Dict, List, Optional


_URGENT_PATTERNS = re.compile(
    r"\b(urgent(ly)?|asap|immediate(ly)?|desperate(ly)?"
    r"|critical\s+hire|start\s+immediately|hiring\s+now"
    r"|need\s+immediately|fill\s+asap|right\s+away)\b",
    re.IGNORECASE,
)

_SMALL_PATTERNS = re.compile(
    r"\b(small\s+team|early[- ]stage|seed[- ]stage|pre[- ]seed"
    r"|startup|founding\s+team|\d{1,2}[- ]person\s+team"
    r"|series\s+a|bootstrapped|self[- ]funded)\b",
    re.IGNORECASE,
)


def compute_desperation_score(job: Dict, company: Optional[Dict] = None) -> Dict:
    """Return {score: 0-100, signals: [...]}."""
    signals = []
    text = f"{job.get('title', '')} {job.get('description', '') or ''}"

    # Multi-board posting (up to 25 pts)
    boards = [b.strip() for b in (job.get("source_boards", "") or "").split(",") if b.strip()]
    if len(boards) >= 3:
        signals.append({"type": "multi_board", "weight": 25, "detail": f"Found on {len(boards)} boards"})
    elif len(boards) >= 2:
        signals.append({"type": "multi_board", "weight": 15, "detail": f"Found on {len(boards)} boards"})

    # Urgent language (up to 20 pts)
    if _URGENT_PATTERNS.search(text):
        signals.append({"type": "urgent_language", "weight": 20, "detail": "Urgent language in posting"})

    # Small company (up to 20 pts)
    headcount = (company or {}).get("headcount")
    funding = ((company or {}).get("funding_stage") or "").lower()
    if headcount and headcount < 50:
        signals.append({"type": "small_company", "weight": 20, "detail": f"{headcount} employees"})
    elif headcount and headcount < 100:
        signals.append({"type": "small_company", "weight": 10, "detail": f"{headcount} employees"})
    elif _SMALL_PATTERNS.search(text):
        signals.append({"type": "small_company", "weight": 15, "detail": "Small team / early stage"})
    elif funding in ("seed", "pre-seed", "pre_seed", "series_a"):
        signals.append({"type": "small_company", "weight": 15, "detail": f"Early funding: {funding}"})

    # Long open (up to 15 pts)
    discovered = job.get("discovered_date") or job.get("discovered_at", "")
    if discovered:
        try:
            days_open = (date.today() - datetime.fromisoformat(str(discovered)[:10]).date()).days
            if days_open > 35:
                signals.append({"type": "long_open", "weight": 15, "detail": f"Open {days_open}d"})
            elif days_open > 21:
                signals.append({"type": "long_open", "weight": 10, "detail": f"Open {days_open}d"})
        except (ValueError, TypeError):
            pass

    # Company distress / funding signal (up to 5 pts)
    if company:
        notes = (company.get("notes") or "").lower()
        source = (company.get("source") or "").lower()
        if any(kw in notes for kw in ["distress", "urgent", "desperately"]):
            signals.append({"type": "distress_signal", "weight": 5, "detail": "Distress signal"})
        elif "serper" in source and any(kw in notes for kw in ["funding", "raised"]):
            signals.append({"type": "funding_signal", "weight": 5, "detail": "Recently funded"})

    return {"score": min(sum(s["weight"] for s in signals), 100), "signals": signals}


def compute_desperation_for_jobs(db, jobs: List[Dict], progress_callback=None) -> int:
    """Score desperation for a list of jobs and persist to DB. Returns count updated."""
    scored = 0
    for i, job in enumerate(jobs):
        company = None
        if job.get("company_id"):
            try:
                company = db.get_company_by_id(job["company_id"])
            except Exception:
                pass

        result = compute_desperation_score(job, company)
        if result["score"] > 0:
            try:
                db._request("PATCH", f"jobs?id=eq.{job['id']}", json={
                    "desperation_score": result["score"],
                    "desperation_signals": "; ".join(s["detail"] for s in result["signals"]),
                })
                scored += 1
            except Exception as e:
                print(f"desperation update error {job.get('id')}: {e}")

        if progress_callback:
            progress_callback(f"Desperation {i+1}/{len(jobs)}", (i + 1) / len(jobs))

    return scored
