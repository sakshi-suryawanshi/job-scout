# job_scout/ai/prompts.py
"""
All Gemini prompt templates in one place.

Import constants from here rather than embedding prompt strings inline.
Format with .format(**kwargs) before sending to the API.
"""

# ── Scoring ───────────────────────────────────────────────────────────────────

SCORING_PROMPT = """\
Score this job against the candidate's criteria. Return JSON.

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

CALIBRATION — be strict:
- 85-100 = "apply today". Globally remote (not US-only, not India). Title is a
  junior/IC role in the software-engineering family (no senior/staff/lead/principal/manager).
  YOE requirement within {max_yoe}+1 years. At least 2 required skills are in the JD.
- 70-84 = decent match with one weakness (unclear remote, one missing skill, edge YOE).
- 50-69 = partial — wrong seniority OR weak skills overlap OR US-only.
- 0-49 = clearly off (wrong role family, India-located, 5+ years required, etc).

If in doubt, score lower. The user wants ~20 jobs out of 1000 at 85+, not 200.
JSON response:"""

BATCH_SCORING_PROMPT = """\
Score these {count} jobs against the candidate criteria. Return a JSON array.

Candidate:
- Keywords: {title_keywords}
- Skills: {required_skills}
- Remote: {remote_only}
- Max YoE: {max_yoe}

Jobs:
{jobs_json}

CALIBRATION — be strict:
- 85+ ONLY for globally-remote, junior/IC software-engineering roles, YOE within max+1,
  with clear skill overlap. Anything ambiguous → ≤79.
- US-only / "must be authorized to work in US" → cap at 60.
- Senior/Staff/Lead/Principal/Manager in title → cap at 40.
- India-located → cap at 20.

Return JSON array — one object per job in the same order:
[{{"id": "<job_id>", "score": <0-100>, "match_reason": "<1 sentence>"}}, ...]
JSON:"""

# ── Resume tailoring ──────────────────────────────────────────────────────────

TAILOR_PROMPT = """\
You are helping tailor a resume for a specific job application.

The resume below is provided as **raw LaTeX source** (.tex file). \
Read it as a structured document — sections, bullet points, dates, and skills \
are all encoded in LaTeX markup. You understand LaTeX natively.

**Job details:**
- Title: {job_title}
- Company: {company_name}
- Location: {location}
- Remote: {is_remote}
- Source board: {source_board}
{description_section}

**Candidate's base resume (raw LaTeX source):**
{resume_text}

---

HARD RULES — NEVER BREAK THESE:
1. Do NOT add any skill, tool, technology, or achievement that is not explicitly \
in the original resume. Not even implied.
2. Do NOT increase seniority, years of experience, or scope beyond what is written. \
"Led a team of 3" cannot become "Led cross-functional teams."
3. If the job requires a skill the candidate does NOT have, leave it out entirely. \
Do not hint at it, approximate it, or frame adjacent experience as equivalent.
4. If you are uncertain whether the candidate has something, assume they do not.
5. NEVER change any proper noun — university names, city names, company names, \
college names, degree names, dates, GPA, or any factual identifier. \
If the resume says "Pune", write "Pune". If it says "University of XYZ", write \
"University of XYZ" exactly. Changing a real place or institution name is \
a serious factual error that will fail a background check.

WHAT YOU SHOULD DO:
1. Read the job description carefully. Identify the 3-5 most important requirements.
2. For each requirement, check if the resume has a direct match.
   If YES → bring it forward, make it prominent, add context linking it to this role.
   If NO  → do not mention it at all.
3. Reorder bullet points within each role so the most relevant experience appears \
first and the least relevant is at the bottom or removed.
4. Rewrite the summary (2-3 sentences) using ONLY what is in the resume — connect \
the candidate's real background to this specific role and company.
5. Keep the same overall structure and approximate length.
6. Output plain text only. No markdown, no JSON, no commentary.

The goal is a resume that creates a strong, HONEST interview conversation — \
not one that creates awkward questions about experience that does not exist.

Tailored resume:"""

# ── Career page extraction ────────────────────────────────────────────────────

CAREER_PAGE_PROMPT = """\
Extract job listings from this career page text for "{company_name}".
Return a JSON array of job objects with: title, location, is_remote, department, \
employment_type, seniority, skills, yoe_min, yoe_max, salary_min, salary_max.
Only actual job openings. Return at most {max_jobs} jobs. If none, return [].
Career page text:
{raw_text}
JSON response:"""

# ── Profile analysis ──────────────────────────────────────────────────────────

PROFILE_ANALYSIS_PROMPT = """\
Analyze this resume and extract structured information. Return JSON.

Resume:
{resume_text}

Return ONLY valid JSON:
{{
  "summary": "<2-3 sentence professional summary>",
  "skills": ["skill1", "skill2", ...],
  "experience_years": <integer>,
  "preferred_roles": ["role1", "role2", ...]
}}"""

# ── Cover letter / ATS answers ────────────────────────────────────────────────

COVER_LETTER_PROMPT = """\
Write a concise, compelling cover letter for this job application.

Job: {job_title} at {company_name}
Description excerpt: {description}

Candidate background: {resume_summary}
Key skills: {skills}

Rules:
1. 3 short paragraphs maximum.
2. Open with why this specific company/role.
3. Second paragraph: 2-3 concrete accomplishments directly relevant to the role.
4. Close with a confident call to action.
5. No fluff. No generic phrases like "I am a fast learner".
6. Plain text only.

Cover letter:"""

ATS_ANSWER_PROMPT = """\
Answer this ATS application question for a job at {company_name} ({job_title}).

Question: {question}

Candidate info:
- Resume summary: {resume_summary}
- Skills: {skills}
- Years of experience: {experience_years}

Keep the answer concise (1-3 sentences unless a longer answer is clearly needed).
Answer only what was asked. No preamble.

Answer:"""
