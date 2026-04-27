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

_USAGE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".streamlit", "usage.json",
)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


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
    data = _load_usage()
    calls = data.get("gemini_calls", 0)
    return {"calls": calls, "remaining": 1500 - calls, "limit": 1500}


class GeminiClient:
    """Lightweight Gemini 2.0 Flash client using REST API."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY must be set")
        self.client = httpx.Client(timeout=60.0)
        self.requests_made = 0

    def generate(self, prompt: str, max_tokens: int = 2048) -> Optional[str]:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2},
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
            if e.response.status_code == 429:
                print("Gemini rate limit hit")
            elif e.response.status_code == 403:
                print("Gemini API key invalid")
            else:
                print(f"Gemini HTTP error: {e.response.status_code}")
            return None
        except Exception as e:
            print(f"Gemini error: {e}")
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
    prompt = f"""Score these {len(jobs)} jobs against the candidate criteria. Return a JSON array.

**Candidate criteria:**
- Title keywords: {", ".join(criteria.get("title_keywords", []))}
- Required skills: {", ".join(criteria.get("required_skills", [])) or "any"}
- Remote preferred: {criteria.get("remote_only", True)}
- Max YOE: {criteria.get("max_yoe", 5)}
- Extra: {criteria.get("extra_conditions", "none")}

**Jobs:**
{jobs_text}

Return a JSON array with {len(jobs)} objects in order:
[{{"score": <0-100>, "match_reason": "<1 sentence>"}}, ...]

Scoring: 80-100=strong, 60-79=decent, 40-59=partial, 20-39=weak, 0-19=poor.
JSON array:"""
    result = gemini.generate_json(prompt, max_tokens=1500)
    if isinstance(result, list) and len(result) == len(jobs):
        return result
    return None


def _rule_based_score(job: Dict, criteria: Dict) -> int:
    score = 0
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    text = f"{title} {description}"

    title_keywords = criteria.get("title_keywords", [])
    if title_keywords:
        score += min(30, sum(1 for kw in title_keywords if kw.lower() in title) * 10)

    skills = criteria.get("required_skills", [])
    if skills:
        score += min(30, sum(1 for s in skills if s.lower() in text) * 10)
    else:
        score += 15

    if criteria.get("remote_only"):
        score += 20 if job.get("is_remote") else 0
    else:
        score += 20

    max_yoe = criteria.get("max_yoe")
    if max_yoe is not None:
        import re
        yoe_patterns = re.findall(r"(\d+)\+?\s*(?:years|yrs)", description)
        if yoe_patterns:
            min_mentioned = min(int(y) for y in yoe_patterns)
            score += 20 if min_mentioned <= max_yoe else (10 if min_mentioned <= max_yoe + 2 else 0)
        else:
            score += 15
    else:
        score += 20

    low_competition = {
        "jobicy", "workingnomads", "arbeitnow", "hackernews", "hackernews_jobs",
        "jobspresso", "wfhio", "remoteco", "authenticjobs", "djangojobs", "larajobs",
        "nodesk", "4dayweek", "vuejobs", "golangjobs", "dynamitejobs", "smashingmag",
        "devitjobs", "cryptojobslist", "web3career", "climatebase", "freshremote",
        "powertofly", "remotefirstjobs", "jobicy_all", "cord", "wellfound", "hired",
        "talentio", "pallet",
    }
    if job.get("source_board") in low_competition:
        score += 5

    s_min, s_max = job.get("salary_min"), job.get("salary_max")
    if s_min and s_max:
        if 40000 <= s_min <= 100000 or 40000 <= s_max <= 100000:
            score += 5

    return min(100, score)


def score_job_rule_based(job: Dict, criteria: Dict) -> Dict:
    score = _rule_based_score(job, criteria)
    reasons = []
    title = (job.get("title") or "").lower()
    matched_kws = [kw for kw in criteria.get("title_keywords", []) if kw.lower() in title]
    if matched_kws:
        reasons.append(f"Title matches: {', '.join(matched_kws)}")
    if job.get("is_remote") and criteria.get("remote_only"):
        reasons.append("Remote")
    text = f"{title} {(job.get('description') or '').lower()}"
    matched_skills = [s for s in criteria.get("required_skills", []) if s.lower() in text]
    if matched_skills:
        reasons.append(f"Skills: {', '.join(matched_skills)}")
    return {"score": score, "match_reason": " | ".join(reasons) if reasons else "Basic match"}


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
            "match_score": score, "match_reason": reason, "is_recommended": score >= 70,
        })
    except Exception as e:
        print(f"Error updating score for {job_id}: {e}")


def score_all_jobs(db, criteria: Dict, use_ai: bool = False, max_jobs: int = 200, progress_callback=None) -> Dict:
    all_jobs = db.get_jobs(limit=max_jobs)
    unscored = [j for j in all_jobs if j.get("match_score", 0) == 0]
    if not unscored:
        return {"scored": 0, "ai_used": False, "avg_score": 0}

    gemini = None
    ai_available = False
    if use_ai:
        try:
            gemini = GeminiClient()
            ai_available = True
        except ValueError:
            print("Gemini API key not set — using rule-based scoring")

    scored_count, total_score = 0, 0

    if ai_available and gemini:
        ai_candidates = []
        for j in unscored:
            rule_result = score_job_rule_based(j, criteria)
            if rule_result["score"] >= 15:
                ai_candidates.append(j)
            else:
                _update_job_score(db, j["id"], rule_result["score"], rule_result["match_reason"] + " (pre-filtered)")
                scored_count += 1
                total_score += rule_result["score"]

        if progress_callback and ai_candidates:
            progress_callback(f"Pre-filter: {len(unscored) - len(ai_candidates)} skipped, {len(ai_candidates)} sent to Gemini", 0.1)

        batch_size = 10
        for i in range(0, len(ai_candidates), batch_size):
            batch = ai_candidates[i:i + batch_size]
            if progress_callback:
                progress_callback(f"AI scoring {i+1}-{min(i+batch_size, len(ai_candidates))} of {len(ai_candidates)}...",
                                   0.1 + 0.85 * (i / max(len(ai_candidates), 1)))
            job_dicts = [{
                "title": j.get("title", ""),
                "company_name": (j.get("companies", {}) or {}).get("name", "Unknown"),
                "location": j.get("location", ""),
                "is_remote": j.get("is_remote", False),
                "source_board": j.get("source_board", ""),
                "description": "",
            } for j in batch]
            batch_scores = _score_batch(gemini, job_dicts, criteria)
            if batch_scores:
                for j, score_data in zip(batch, batch_scores):
                    _update_job_score(db, j["id"], score_data.get("score", 0), score_data.get("match_reason", ""))
                    scored_count += 1
                    total_score += score_data.get("score", 0)
            else:
                for j in batch:
                    result = score_job_rule_based(j, criteria)
                    _update_job_score(db, j["id"], result["score"], result["match_reason"])
                    scored_count += 1
                    total_score += result["score"]
    else:
        for i, j in enumerate(unscored):
            if progress_callback:
                progress_callback(f"Scoring job {i+1}/{len(unscored)}...", i / len(unscored))
            result = score_job_rule_based(j, criteria)
            _update_job_score(db, j["id"], result["score"], result["match_reason"])
            scored_count += 1
            total_score += result["score"]

    try:
        from worker.signals.desperation_detector import compute_desperation_for_jobs
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
    return {"scored": scored_count, "ai_used": ai_available, "avg_score": round(avg, 1)}


def tailor_resume(gemini: "GeminiClient", resume_text: str, job: Dict, job_description: str = "") -> Optional[str]:
    company_info = job.get("companies", {}) or {}
    company_name = company_info.get("name", "") or job.get("company_name", "Unknown")
    description_section = f"- Description excerpt:\n{job_description[:2000]}" if job_description.strip() else ""
    prompt = TAILOR_PROMPT.format(
        job_title=job.get("title", "Unknown"),
        company_name=company_name,
        location=job.get("location", "Remote"),
        is_remote=job.get("is_remote", True),
        source_board=job.get("source_board", ""),
        description_section=description_section,
        resume_text=resume_text[:4000],
    )
    return gemini.generate(prompt, max_tokens=3000)


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
