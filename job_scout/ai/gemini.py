# job_scout/ai/gemini.py
# Moved from worker/ai/gemini_client.py — no logic change, import paths updated.
"""Gemini 2.0 Flash integration: scoring, resume tailoring, career page parsing."""

import os
import json
import httpx
from datetime import date
from typing import List, Dict, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def _is_demo_mode() -> bool:
    """Read DEMO_MODE at call time so toggling the env var takes effect without restart."""
    return os.getenv("DEMO_MODE", "false").lower() == "true"

_USAGE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".streamlit", "usage.json",
)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


def _load_usage() -> dict:
    try:
        with open(_USAGE_FILE) as f:
            data = json.load(f)
        if data.get("date") != date.today().isoformat():
            return {"date": date.today().isoformat(), "gemini_calls": 0}
        return data
    except Exception:
        return {"date": date.today().isoformat(), "gemini_calls": 0}


def _save_usage(data: dict):
    try:
        os.makedirs(os.path.dirname(_USAGE_FILE), exist_ok=True)
        with open(_USAGE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def get_gemini_usage_today() -> dict:
    if _is_demo_mode():
        return {"calls": 42, "remaining": 1458, "limit": 1500}
    data = _load_usage()
    calls = data.get("gemini_calls", 0)
    return {"calls": calls, "remaining": 1500 - calls, "limit": 1500}


class GeminiClient:
    """Lightweight Gemini 2.0 Flash client using REST API."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY must be set")
        self.client = httpx.Client(timeout=120.0)   # 2 min — Gemini 2.5 Flash thinks before responding
        self.requests_made = 0

    def generate(self, prompt: str, max_tokens: int = 4096,
                 _retry: int = 0) -> Optional[str]:
        """Send a prompt to Gemini and return the text response.

        Retries automatically on 429 rate-limit with exponential backoff:
          attempt 1 → wait 30s → retry
          attempt 2 → wait 60s → retry
          attempt 3 → wait 90s → give up and return None

        This is better than sleeping between every call:
        - Zero wait when there is no rate limit
        - Self-healing when the pipeline sends a burst
        """
        import time

        if _is_demo_mode():
            return "Demo mode — Gemini response mocked. Set DEMO_MODE=false and add GEMINI_API_KEY to enable."
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.2,
            },
        }
        try:
            response = self.client.post(f"{GEMINI_API_URL}?key={self.api_key}", json=payload)
            response.raise_for_status()
            self.requests_made += 1
            usage = _load_usage()
            usage["gemini_calls"] = usage.get("gemini_calls", 0) + 1
            _save_usage(usage)
            candidates = response.json().get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return None

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            max_retries = 3
            if status in (429, 503):
                # 429 = rate limit   503 = model overloaded (high demand)
                # Both are temporary — exponential backoff: 30s → 60s → 90s
                if _retry < max_retries:
                    wait = 30 * (_retry + 1)
                    reason = "rate limit" if status == 429 else "server overloaded"
                    print(f"  Gemini {reason} (HTTP {status}) — waiting {wait}s, retry {_retry + 1}/{max_retries}")
                    time.sleep(wait)
                    return self.generate(prompt, max_tokens, _retry=_retry + 1)
                print(f"  Gemini HTTP {status} — max retries reached, skipping")
            elif status == 403:
                print("  Gemini API key invalid or quota exhausted for today")
            else:
                print(f"  Gemini HTTP {status}: {e.response.text[:200]}")
            return None

        except Exception as e:
            print(f"  Gemini error: {e}")
            return None

    def generate_json(self, prompt: str, max_tokens: int = 2048) -> Optional[Dict]:
        text = self.generate(prompt, max_tokens)
        if not text:
            return None
        text = text.strip()
        for strip in ["```json", "```"]:
            if text.startswith(strip):
                text = text[len(strip):]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{[\s\S]*\}|\[[\s\S]*\]', text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            print(f"Failed to parse Gemini JSON: {text[:200]}")
            return None


SCORING_PROMPT = """Score this job against the candidate's criteria. Return JSON.

**Candidate criteria:**
- Title keywords: {title_keywords}
- Required skills: {required_skills}
- Preferred remote: {remote_only}
- Max years of experience: {max_yoe}
- Extra conditions: {extra_conditions}

**Job details:**
- Title: {job_title}
- Company: {company_name}
- Location: {location}
- Remote: {is_remote}
- Source: {source_board}
- Description: {description}

Return this exact JSON format:
{{
    "score": <0-100 integer>,
    "match_reason": "<1-2 sentence explanation>",
    "signals": {{"title_match": <0-25>, "skills_match": <0-25>, "remote_match": <0-25>, "experience_match": <0-25>}}
}}

Scoring: 80-100=strong, 60-79=decent, 40-59=partial, 20-39=weak, 0-19=poor.
JSON response:"""

TAILOR_PROMPT = """You are an expert resume writer. Tailor the candidate's resume for a specific job.

**Job details:**
- Title: {job_title}
- Company: {company_name}
- Location: {location}
- Remote: {is_remote}
- Source board: {source_board}
{description_section}

**Candidate's base resume:**
{resume_text}

Rewrite the resume tailored to this job. Rules:
1. Keep ALL facts true — do not invent experience or skills.
2. Reorder bullet points to surface the most relevant experience first.
3. Adjust the summary/objective to mention the role title and company.
4. Emphasize skills and tools that match the job.
5. Keep the same overall structure and length.
6. Output plain text only — no markdown, no JSON, no explanation.

Tailored resume:"""


def parse_career_page_with_ai(gemini: GeminiClient, raw_text: str, company_name: str, max_jobs: int = 20) -> List[Dict]:
    prompt = f"""Extract job listings from this career page text for "{company_name}".
Return a JSON array of job objects with: title, location, is_remote, department, employment_type, seniority, skills, yoe_min, yoe_max, salary_min, salary_max.
Only actual job openings. Return at most {max_jobs} jobs. If none, return [].
Career page text:\n{raw_text[:8000]}\nJSON response:"""
    result = gemini.generate_json(prompt, max_tokens=3000)
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and "jobs" in result:
        return result["jobs"]
    return []


def score_job_with_ai(gemini: GeminiClient, job: Dict, criteria: Dict) -> Optional[Dict]:
    prompt = SCORING_PROMPT.format(
        title_keywords=", ".join(criteria.get("title_keywords", [])),
        required_skills=", ".join(criteria.get("required_skills", [])) or "any",
        remote_only=criteria.get("remote_only", True),
        max_yoe=criteria.get("max_yoe", 5),
        extra_conditions=criteria.get("extra_conditions", "none"),
        job_title=job.get("title", "Unknown"),
        company_name=job.get("company_name", "Unknown"),
        location=job.get("location", "Unknown"),
        is_remote=job.get("is_remote", False),
        source_board=job.get("source_board", "unknown"),
        description=(job.get("description") or "")[:3000],
    )
    return gemini.generate_json(prompt, max_tokens=500)


def _score_batch(gemini: GeminiClient, jobs: List[Dict], criteria: Dict) -> Optional[List[Dict]]:
    jobs_text = ""
    for i, j in enumerate(jobs):
        jobs_text += f"\nJob {i+1}:\n  Title: {j.get('title', 'Unknown')}\n  Company: {j.get('company_name', 'Unknown')}\n  Location: {j.get('location', 'Unknown')}\n  Remote: {j.get('is_remote', False)}\n"
        desc = (j.get("description") or "")[:500]
        if desc:
            jobs_text += f"  Description: {desc}\n"
    must_have = ", ".join(criteria.get("must_have_skills", [])) or "(none)"
    nice_to_have = ", ".join(
        criteria.get("nice_to_have_skills") or criteria.get("required_skills", [])
    ) or "(none)"
    prompt = f"""Score these {len(jobs)} jobs against the candidate criteria. Return a JSON array.

**Candidate criteria:**
- Title keywords: {", ".join(criteria.get("title_keywords", []))}
- MUST-have skills (all required): {must_have}
- Nice-to-have skills: {nice_to_have}
- Remote preferred: {criteria.get("remote_only", True)}
- Globally remote required: {criteria.get("global_remote_only", True)}
- Max YOE: {criteria.get("max_yoe", 5)}
- Exclude in title: {", ".join(criteria.get("exclude_keywords", [])) or "(none)"}

**Jobs:**
{jobs_text}

Return a JSON array with {len(jobs)} objects in order:
[{{"score": <0-100>, "match_reason": "<1 sentence>"}}, ...]

CALIBRATION — be strict, user wants ~20 of 1000 at 85+, not 200:
- 85+ ONLY: globally-remote (not US-only / India), junior/IC software role,
  YOE ≤ max+1, ALL must-have skills present, ≥2 nice-to-have matched.
- Senior/Staff/Lead/Principal/Manager in title → cap at 40.
- US-only / work-auth required → cap at 60.
- India-located → cap at 20.
- Missing a must-have skill → cap at 50.

JSON array:"""
    result = gemini.generate_json(prompt, max_tokens=1500)
    if isinstance(result, list) and len(result) == len(jobs):
        return result
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Scoring (Gate → Component score → Penalty) — see .planning/zany-enchanting-acorn.md
#
# Goal: surface ~20 must-apply jobs out of ~1000 by being strict, not lenient.
# A score of 85+ means the job genuinely matches the candidate's bare minimum.
# ─────────────────────────────────────────────────────────────────────────────

RECOMMEND_THRESHOLD = 85   # is_recommended = (final_score >= RECOMMEND_THRESHOLD)

# Role-family phrases — title must contain one of these as a whole phrase.
_ROLE_FAMILY = [
    "software engineer", "software developer",
    "backend engineer", "backend developer",
    "back end engineer", "back end developer",
    "full stack developer", "full stack engineer",
    "fullstack developer", "fullstack engineer",
    "full-stack developer", "full-stack engineer",
    "python developer", "python engineer",
]

# Defensive India-location list (mirrors GLOBAL_EXCLUSIONS in serper_dorking).
_INDIA_LOCATION_WORDS = {
    "india", "bangalore", "bengaluru", "mumbai", "delhi", "pune",
    "hyderabad", "chennai", "kolkata", "noida", "gurugram", "gurgaon", "ahmedabad",
}


def _word_boundary_match(needle: str, haystack: str) -> bool:
    """Case-insensitive whole-word/phrase match. Handles multi-word phrases."""
    import re
    pattern = r"(?<![A-Za-z0-9])" + re.escape(needle) + r"(?![A-Za-z0-9])"
    return bool(re.search(pattern, haystack, re.IGNORECASE))


def _extract_max_yoe(description: str) -> Optional[int]:
    """Return the MAX (strictest) YOE mentioned in JD body, or None if absent.
    Old impl used min(), which let '3-8 years' pass max_yoe=4."""
    import re
    matches = re.findall(r"(\d+)\+?\s*(?:years?|yrs?)\b", description, re.IGNORECASE)
    if not matches:
        return None
    try:
        return max(int(m) for m in matches)
    except ValueError:
        return None


def _check_gates(job: Dict, criteria: Dict):
    """Return (passed: bool, reason: str). Reason describes the FIRST failing gate."""
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    location = (job.get("location") or "").lower()

    # Gate: remote
    if criteria.get("remote_only", True) and not job.get("is_remote"):
        return False, "gated: not remote"

    # Gate: globally remote (not US-only, not India)
    if criteria.get("global_remote_only", True):
        try:
            from job_scout.enrichment.dedup import is_globally_remote
            if not is_globally_remote(job):
                return False, "gated: not globally remote (US-only / region-locked / India)"
        except Exception:
            pass

    # Gate: India-location leak (defensive)
    if any(w in location for w in _INDIA_LOCATION_WORDS):
        return False, "gated: India location"

    # Gate: role family present (whole-phrase, not substring)
    if not any(_word_boundary_match(phrase, title) for phrase in _ROLE_FAMILY):
        # Fall-back: at least one user title_keyword whole-word
        kws = criteria.get("title_keywords", [])
        if kws and not any(_word_boundary_match(kw, title) for kw in kws):
            return False, "gated: title doesn't match role family or any title_keyword"

    # Gate: excluded title keywords (whole-word, not substring)
    for ex in criteria.get("exclude_keywords", []):
        if _word_boundary_match(ex, title):
            return False, f"gated: excluded keyword in title ('{ex}')"

    # Gate: YOE ceiling (using MAX, not min)
    max_yoe = criteria.get("max_yoe")
    if max_yoe is not None:
        mentioned = _extract_max_yoe(description)
        if mentioned is not None and mentioned > max_yoe + 1:
            return False, f"gated: requires {mentioned}+ years (max allowed {max_yoe})"

    # Gate: ALL must-have skills present
    must_have = criteria.get("must_have_skills") or []
    if must_have:
        text = f"{title} {description}"
        missing = [s for s in must_have if not _word_boundary_match(s, text)]
        if missing:
            return False, f"gated: missing must-have skill(s) {missing}"

    return True, ""


def _score_components(job: Dict, criteria: Dict):
    """Compute the 7 weighted components (sum max = 100). Returns (score, breakdown)."""
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    text = f"{title} {description}"
    breakdown = {}

    # 1. Role-family title match — max 30
    role_pts = 0
    if any(_word_boundary_match(p, title) for p in _ROLE_FAMILY):
        role_pts = 30
    else:
        kw_hits = sum(1 for kw in criteria.get("title_keywords", []) if _word_boundary_match(kw, title))
        role_pts = min(10, kw_hits * 5)
    breakdown["role"] = role_pts

    # 2. Nice-to-have skills overlap — max 20
    nice = criteria.get("nice_to_have_skills") or criteria.get("required_skills") or []
    if nice:
        matched = sum(1 for s in nice if _word_boundary_match(s, text))
        skill_pts = round(matched / len(nice) * 20)
    else:
        skill_pts = 0
    breakdown["skills"] = skill_pts

    # 3. Global remote strength — max 15
    try:
        from job_scout.enrichment.dedup import is_globally_remote
        global_remote = is_globally_remote(job)
    except Exception:
        global_remote = False
    if global_remote and any(w in text for w in ("worldwide", "anywhere", "global")):
        global_pts = 15
    elif global_remote:
        global_pts = 10
    elif job.get("is_remote"):
        global_pts = 5
    else:
        global_pts = 0
    breakdown["global"] = global_pts

    # 4. YOE fit — max 15
    max_yoe = criteria.get("max_yoe")
    mentioned = _extract_max_yoe(description)
    if max_yoe is None:
        yoe_pts = 10
    elif mentioned is None:
        yoe_pts = 5
    elif mentioned <= max_yoe:
        yoe_pts = 15
    elif mentioned <= max_yoe + 1:
        yoe_pts = 8
    else:
        yoe_pts = 0  # gated above; defensive
    breakdown["yoe"] = yoe_pts

    # 5. Desperation — max 10
    desp = job.get("desperation_score") or 0
    try:
        desp_pts = round(min(100, int(desp)) / 100 * 10)
    except (TypeError, ValueError):
        desp_pts = 0
    breakdown["desperation"] = desp_pts

    # 6. Freshness — max 5
    fresh_pts = 0
    discovered = job.get("discovered_at") or job.get("discovered_date") or ""
    if discovered:
        try:
            from datetime import datetime, date
            d = datetime.fromisoformat(str(discovered)[:10]).date()
            age_days = (date.today() - d).days
            if age_days < 3:
                fresh_pts = 5
            elif age_days < 7:
                fresh_pts = 3
            elif age_days < 14:
                fresh_pts = 1
        except Exception:
            pass
    breakdown["fresh"] = fresh_pts

    # 7. Salary — max 5
    min_sal = criteria.get("min_salary")
    s_max = job.get("salary_max")
    s_min = job.get("salary_min")
    if min_sal is None:
        # No floor specified — give credit if salary disclosed at all
        sal_pts = 5 if (s_max or s_min) else 2
    elif s_max and s_max >= min_sal:
        sal_pts = 5
    elif not (s_max or s_min):
        sal_pts = 2
    else:
        sal_pts = 0
    breakdown["salary"] = sal_pts

    total = sum(breakdown.values())
    return total, breakdown


def _apply_penalties(job: Dict, criteria: Dict, score: int):
    """Apply Stage 3 negative-signal penalties. Returns (new_score, penalty_notes)."""
    import re
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    head = description[:200]
    notes = []

    # 5+ years (etc.) leak past the gate
    max_yoe = criteria.get("max_yoe")
    if max_yoe is not None:
        for m in re.finditer(r"(\d+)\+\s*(?:years?|yrs?)\b", description, re.IGNORECASE):
            y = int(m.group(1))
            if y > max_yoe + 1:
                score -= 15
                notes.append(f"-15 yoe-leak({y}+)")
                break

    # US-only / work-auth
    if re.search(r"must be authorized to work in (the )?(us|united states|uk)", description, re.IGNORECASE):
        score -= 15
        notes.append("-15 us-auth")

    # On-site / hybrid in title or first 200 chars
    if re.search(r"\bon[-\s]?site\b|\bhybrid\b", title + " " + head, re.IGNORECASE):
        score -= 10
        notes.append("-10 on-site/hybrid")

    # India HQ leak
    if re.search(r"\b(india hq|based in india|headquartered in india)\b", description, re.IGNORECASE):
        score -= 20
        notes.append("-20 india-hq")

    return max(0, score), notes


def _compute_score(job: Dict, criteria: Dict):
    """Top-level rule-based scoring.

    Returns dict {score, match_reason, gated} where:
      - score: 0..100
      - match_reason: human-readable signal trace, e.g.
          "gated: not globally remote (US-only)"
          "+30 role +20 skills +15 global +15 yoe +6 desp +5 fresh +5 salary = 96"
      - gated: bool — True when a gate failed (score forced to 0)
    """
    passed, reason = _check_gates(job, criteria)
    if not passed:
        return {"score": 0, "match_reason": reason, "gated": True}

    base, breakdown = _score_components(job, criteria)
    final, penalty_notes = _apply_penalties(job, criteria, base)

    parts = [f"+{v} {k}" for k, v in breakdown.items() if v > 0]
    trace = " ".join(parts) + (" " + " ".join(penalty_notes) if penalty_notes else "")
    trace += f" = {final}"
    return {"score": min(100, final), "match_reason": trace.strip(), "gated": False}


# Back-compat wrappers — keep existing callers working.

def _rule_based_score(job: Dict, criteria: Dict) -> int:
    """Old API: returns int score only."""
    return _compute_score(job, criteria)["score"]


def score_job_rule_based(job: Dict, criteria: Dict) -> Dict:
    """Old API: returns {score, match_reason}. Now includes a gate trace when applicable."""
    r = _compute_score(job, criteria)
    return {"score": r["score"], "match_reason": r["match_reason"]}


def score_jobs_batch(gemini: GeminiClient, jobs: List[Dict], criteria: Dict, progress_callback=None) -> List[Dict]:
    scored = []
    batch_size = 10
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        if progress_callback:
            progress_callback(f"Scoring jobs {i+1}-{min(i+batch_size, len(jobs))}...", i / len(jobs))
        batch_result = _score_batch(gemini, batch, criteria)
        if batch_result:
            for j, score_data in zip(batch, batch_result):
                j["match_score"] = score_data.get("score", 0)
                j["match_reason"] = score_data.get("match_reason", "")
                scored.append(j)
        else:
            for j in batch:
                j["match_score"] = _rule_based_score(j, criteria)
                j["match_reason"] = "Scored by rules (AI unavailable)"
                scored.append(j)
    return scored


def _update_job_score(db, job_id: str, score: int, reason: str):
    try:
        db._request("PATCH", f"jobs?id=eq.{job_id}", json={
            "match_score": score, "match_reason": reason,
            "is_recommended": score >= RECOMMEND_THRESHOLD,
        })
    except Exception as e:
        print(f"Error updating score for {job_id}: {e}")


# Top-N candidates sent to Gemini for refinement. Keeps API usage well under
# the free-tier 15 RPM cap even on 1000-job corpuses.
_AI_TOP_N = 50


def score_all_jobs(
    db,
    criteria: Dict,
    use_ai: bool = False,
    max_jobs: int = 200,
    progress_callback=None,
    force_rescore: bool = False,
) -> Dict:
    """Rule-based score for ALL candidates, then optionally refine the top-N
    with Gemini (blended via max(rule, gemini-5)).

    force_rescore=True re-scores every job (not only `match_score=0`). Use this
    after criteria changes.
    """
    all_jobs = db.get_jobs(limit=max_jobs)
    if force_rescore:
        candidates = list(all_jobs)
    else:
        candidates = [j for j in all_jobs if (j.get("match_score") or 0) == 0]
    if not candidates:
        return {"scored": 0, "ai_used": False, "avg_score": 0, "gated": 0, "recommended": 0}

    # ── Phase 1: rule-based scoring for every candidate ────────────────────
    if progress_callback:
        progress_callback(f"Rule-based scoring of {len(candidates)} jobs…", 0.0)

    rule_scores: Dict[str, Dict] = {}   # job_id -> {score, match_reason, gated}
    gated_count = 0
    for i, j in enumerate(candidates):
        r = _compute_score(j, criteria)
        rule_scores[j["id"]] = r
        if r["gated"]:
            gated_count += 1
        if progress_callback and i % 25 == 0:
            progress_callback(f"Rule-scoring {i+1}/{len(candidates)}…", 0.05 + 0.35 * (i / len(candidates)))

    # ── Phase 2: optional AI refinement on TOP-N rule-scorers ──────────────
    ai_available = False
    gemini = None
    if use_ai:
        try:
            gemini = GeminiClient()
            ai_available = True
        except ValueError:
            print("Gemini API key not set — using rule-based scoring only")

    ai_scores: Dict[str, int] = {}      # job_id -> gemini score
    if ai_available and gemini:
        # Only refine non-gated, top-N by rule score. Gated jobs stay at 0.
        eligible = [j for j in candidates
                    if not rule_scores[j["id"]]["gated"]
                    and rule_scores[j["id"]]["score"] >= 50]  # below 50 not worth API call
        eligible.sort(key=lambda j: rule_scores[j["id"]]["score"], reverse=True)
        top_n = eligible[:_AI_TOP_N]

        if top_n:
            if progress_callback:
                progress_callback(f"AI refining top {len(top_n)} candidates…", 0.4)
            batch_size = 10
            for i in range(0, len(top_n), batch_size):
                batch = top_n[i:i + batch_size]
                if progress_callback:
                    progress_callback(
                        f"AI batch {i // batch_size + 1}/{(len(top_n) + batch_size - 1) // batch_size}…",
                        0.4 + 0.5 * (i / max(len(top_n), 1)),
                    )
                job_dicts = [{
                    "title": j.get("title", ""),
                    "company_name": (j.get("companies", {}) or {}).get("name", "Unknown"),
                    "location": j.get("location", ""),
                    "is_remote": j.get("is_remote", False),
                    "source_board": j.get("source_board", ""),
                    "description": (j.get("description") or "")[:1000],
                } for j in batch]
                try:
                    batch_result = _score_batch(gemini, job_dicts, criteria)
                except Exception as e:
                    print(f"AI batch error (non-fatal): {e}")
                    batch_result = None
                if batch_result:
                    for j, sd in zip(batch, batch_result):
                        ai_scores[j["id"]] = int(sd.get("score", 0) or 0)

    # ── Phase 3: write final blended scores to DB ──────────────────────────
    scored_count, total_score, recommended = 0, 0, 0
    for i, j in enumerate(candidates):
        r = rule_scores[j["id"]]
        rule_score = r["score"]
        reason = r["match_reason"]
        ai_score = ai_scores.get(j["id"])

        if r["gated"] or ai_score is None:
            final = rule_score
        else:
            # AI is a FLOOR not a ceiling: max(rule, ai - 5).
            # Rule never gets pulled down, but AI can lift a borderline rule-70 to 85.
            final = max(rule_score, ai_score - 5)
            if final != rule_score:
                reason = f"{reason} | ai={ai_score}"

        _update_job_score(db, j["id"], final, reason)
        scored_count += 1
        total_score += final
        if final >= RECOMMEND_THRESHOLD:
            recommended += 1

        if progress_callback and i % 25 == 0:
            progress_callback(f"Saving scores {i+1}/{len(candidates)}…", 0.9 + 0.05 * (i / len(candidates)))

    try:
        from job_scout.enrichment.desperation import compute_desperation_for_jobs
        all_for_desp = db.get_jobs(limit=max_jobs)
        no_desp = [j for j in all_for_desp if not j.get("desperation_score")]
        if no_desp:
            if progress_callback:
                progress_callback("Computing desperation signals...", 0.95)
            compute_desperation_for_jobs(db, no_desp)
    except Exception as e:
        print(f"Desperation scoring error (non-fatal): {e}")

    if progress_callback:
        progress_callback("Scoring complete!", 1.0)

    avg = total_score / scored_count if scored_count > 0 else 0
    return {
        "scored": scored_count,
        "ai_used": ai_available,
        "avg_score": round(avg, 1),
        "gated": gated_count,
        "recommended": recommended,
        "ai_refined": len(ai_scores),
    }


def tailor_resume(gemini: "GeminiClient", resume_text: str, job: Dict, job_description: str = "") -> Optional[str]:
    company_info = job.get("companies", {}) or {}
    company_name = company_info.get("name", "") or job.get("company_name", "Unknown")
    description_section = f"- Description excerpt:\n{job_description[:2000]}" if (job_description or "").strip() else ""
    prompt = TAILOR_PROMPT.format(
        job_title=job.get("title", "Unknown"),
        company_name=company_name,
        location=job.get("location", "Remote"),
        is_remote=job.get("is_remote", True),
        source_board=job.get("source_board", ""),
        description_section=description_section,
        resume_text=resume_text[:4000],
    )
    return gemini.generate(prompt, max_tokens=6000)


def fetch_job_description(apply_url: str, timeout: int = 10) -> str:
    if not apply_url:
        return ""
    try:
        from bs4 import BeautifulSoup
        resp = httpx.get(apply_url, timeout=timeout, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; JobScout/1.0)"})
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["nav", "footer", "header", "script", "style"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:3000]
    except Exception:
        return ""


def generate_resume_html(tailored_text: str, job_title: str, company_name: str) -> str:
    import html as html_lib
    safe_text = html_lib.escape(tailored_text).replace("\n\n", "</p><p>").replace("\n", "<br>")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Resume — {html_lib.escape(job_title)} at {html_lib.escape(company_name)}</title>
<style>
  body {{ font-family: 'Georgia', serif; font-size: 11pt; line-height: 1.5; max-width: 750px; margin: 40px auto; color: #111; }}
  .meta {{ font-size: 9pt; color: #555; margin-bottom: 20px; }}
  p {{ margin: 6px 0; }}
  @media print {{ body {{ margin: 20px; }} }}
</style>
</head>
<body>
<div class="meta">Tailored for: <strong>{html_lib.escape(job_title)}</strong> at <strong>{html_lib.escape(company_name)}</strong></div>
<p>{safe_text}</p>
</body>
</html>"""
