# worker/signals/desperation_detector.py
"""
Detect companies that are desperate to hire — these are more likely to respond.

Signals:
- Job posted on multiple boards
- Urgent language in title/description
- Small company / early stage
- Job open for a long time
- Reposted across scrape cycles
"""

import re
from datetime import datetime, date
from typing import Dict, List, Optional


_URGENT_PATTERNS = re.compile(
    r"\b("
    r"urgent(ly)?|asap|immediate(ly)?|desperate(ly)?"
    r"|critical\s+hire|start\s+immediately|hiring\s+now"
    r"|need\s+immediately|fill\s+asap|right\s+away"
    r")\b",
    re.IGNORECASE,
)

_SMALL_COMPANY_PATTERNS = re.compile(
    r"\b("
    r"small\s+team|early[- ]stage|seed[- ]stage|pre[- ]seed"
    r"|startup|founding\s+team"
    r"|\d{1,2}[- ]person\s+team"
    r"|series\s+a|bootstrapped|self[- ]funded"
    r")\b",
    re.IGNORECASE,
)



def compute_desperation_score(job: Dict, company: Optional[Dict] = None) -> Dict:
    """
    Compute a 0-100 desperation score for a job.

    Args:
        job: Job dict from DB (with source_boards, title, description, etc.)
        company: Optional company dict (with headcount, funding_stage, etc.)

    Returns:
        {"score": int, "signals": [{"type": str, "weight": int, "detail": str}, ...]}
    """
    signals = []

    title = job.get("title", "")
    description = job.get("description", "") or ""
    text = f"{title} {description}"

    # 1. Multi-board posting (0-25 pts)
    source_boards = job.get("source_boards", "") or ""
    boards_list = [b.strip() for b in source_boards.split(",") if b.strip()]
    if len(boards_list) >= 3:
        signals.append({
            "type": "multi_board",
            "weight": 25,
            "detail": f"Found on {len(boards_list)} boards: {', '.join(boards_list)}",
        })
    elif len(boards_list) >= 2:
        signals.append({
            "type": "multi_board",
            "weight": 15,
            "detail": f"Found on {len(boards_list)} boards: {', '.join(boards_list)}",
        })

    # 2. Urgent language (0-20 pts)
    urgent_matches = _URGENT_PATTERNS.findall(text)
    if urgent_matches:
        signals.append({
            "type": "urgent_language",
            "weight": 20,
            "detail": f"Contains urgent language in posting",
        })

    # 3. Small company (0-20 pts)
    headcount = None
    if company:
        headcount = company.get("headcount")
        funding = (company.get("funding_stage") or "").lower()
    else:
        funding = ""

    if headcount and headcount < 50:
        signals.append({
            "type": "small_company",
            "weight": 20,
            "detail": f"Small company ({headcount} employees)",
        })
    elif headcount and headcount < 100:
        signals.append({
            "type": "small_company",
            "weight": 10,
            "detail": f"Mid-size company ({headcount} employees)",
        })
    elif _SMALL_COMPANY_PATTERNS.search(text):
        signals.append({
            "type": "small_company",
            "weight": 15,
            "detail": "Description mentions small team / early stage",
        })
    elif funding in ("seed", "pre-seed", "pre_seed", "series_a"):
        signals.append({
            "type": "small_company",
            "weight": 15,
            "detail": f"Early-stage funding ({funding})",
        })

    # 4. Long open (0-15 pts)
    discovered = job.get("discovered_date") or job.get("discovered_at", "")
    if discovered:
        try:
            disc_date = datetime.fromisoformat(str(discovered)[:10]).date()
            days_open = (date.today() - disc_date).days
            if days_open > 35:
                signals.append({
                    "type": "long_open",
                    "weight": 15,
                    "detail": f"Open for {days_open} days",
                })
            elif days_open > 21:
                signals.append({
                    "type": "long_open",
                    "weight": 10,
                    "detail": f"Open for {days_open} days",
                })
        except (ValueError, TypeError):
            pass

    # 5. Funding/distress signal from discovery (0-5 pts)
    if company:
        notes = (company.get("notes") or "").lower()
        source = (company.get("source") or "").lower()
        if any(kw in notes for kw in ["distress", "urgent", "desperately"]):
            signals.append({
                "type": "funding_signal",
                "weight": 5,
                "detail": "Company flagged via distress signal discovery",
            })
        elif "serper" in source and any(kw in notes for kw in ["funding", "raised"]):
            signals.append({
                "type": "funding_signal",
                "weight": 5,
                "detail": "Recently funded company (eager to grow)",
            })

    total = min(sum(s["weight"] for s in signals), 100)

    return {
        "score": total,
        "signals": signals,
    }


def compute_desperation_for_jobs(db, jobs: List[Dict], progress_callback=None) -> int:
    """
    Compute desperation scores for a list of jobs and update DB.
    Returns count of jobs scored.
    """
    scored = 0
    for i, job in enumerate(jobs):
        # Fetch company info if available
        company = None
        company_id = job.get("company_id")
        if company_id:
            company = db.get_company_by_id(company_id)

        result = compute_desperation_score(job, company)

        if result["score"] > 0:
            signals_text = "; ".join(s["detail"] for s in result["signals"])
            try:
                db._request("PATCH", f"jobs?id=eq.{job['id']}", json={
                    "desperation_score": result["score"],
                    "desperation_signals": signals_text,
                })
                scored += 1
            except Exception as e:
                print(f"Error updating desperation for {job.get('id')}: {e}")

        if progress_callback and len(jobs) > 0:
            progress_callback(f"Scoring desperation... {i+1}/{len(jobs)}", (i + 1) / len(jobs))

    return scored
