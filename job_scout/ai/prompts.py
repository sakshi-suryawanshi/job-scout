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

Scoring: 80-100=strong, 60-79=decent, 40-59=partial, 20-39=weak, 0-19=poor.
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

Return JSON array — one object per job in the same order:
[{{"id": "<job_id>", "score": <0-100>, "match_reason": "<1 sentence>"}}, ...]
JSON:"""

# ── Resume tailoring ──────────────────────────────────────────────────────────

TAILOR_PROMPT = """\
You are an expert resume writer. Tailor the candidate's resume for a specific job.

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
