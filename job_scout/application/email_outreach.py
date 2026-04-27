# job_scout/application/email_outreach.py
"""
Tier 3 — Email outreach for jobs found via HN / IndieHackers / Twitter
where there's no ATS form — just a "DM me" or email address in the post.
"""

import os
import re
from typing import Dict, Optional

from job_scout.application.base import ApplyResult, load_applicant_profile


_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)


def extract_email_from_text(text: str) -> Optional[str]:
    """Extract the first email address from a job description or post text."""
    matches = _EMAIL_PATTERN.findall(text or "")
    # Skip common no-reply / generic addresses
    skip = {"noreply@", "no-reply@", "support@", "info@", "admin@", "contact@", "help@"}
    for match in matches:
        if not any(match.lower().startswith(s) for s in skip):
            return match
    return None


def send_outreach_email(
    job: Dict,
    resume_text: str,
    profile: Optional[Dict] = None,
) -> ApplyResult:
    """
    Generate and send a cold outreach email for an HN / community job post.

    Looks for an email address in job.description or job.apply_url.
    Falls back to needs_attention if no email found.
    """
    if profile is None:
        profile = load_applicant_profile()

    if not profile.get("email"):
        return ApplyResult(status="failed", tier=3, apply_url=job.get("apply_url", ""),
                           error="APPLY_EMAIL not set")

    company_info = job.get("companies", {}) or {}
    company_name = company_info.get("name", "") or job.get("company_name", "Unknown")

    # Find recipient email
    description = job.get("description", "") or ""
    apply_url = job.get("apply_url", "")
    recipient = extract_email_from_text(description) or extract_email_from_text(apply_url)

    if not recipient:
        return ApplyResult(
            status="needs_attention", tier=3, apply_url=apply_url,
            notes=f"No email found in post — manual outreach needed for {company_name}",
        )

    # Generate email body with Gemini
    body = _generate_outreach_body(job, resume_text, profile)
    if not body:
        return ApplyResult(status="failed", tier=3, apply_url=apply_url,
                           error="Failed to generate outreach email body")

    subject = f"Re: {job.get('title', 'Engineering role')} at {company_name}"

    # Send via Gmail SMTP
    try:
        from job_scout.notifications.email import send_email
        html_body = f"<pre style='font-family:Georgia,serif;white-space:pre-wrap'>{body}</pre>"
        sent = send_email(to=recipient, subject=subject, html_body=html_body)
        if sent:
            return ApplyResult(
                status="applied", tier=3, apply_url=apply_url,
                cover_letter=body,
                notes=f"Outreach email sent to {recipient}",
            )
        else:
            return ApplyResult(status="failed", tier=3, apply_url=apply_url,
                               error="Gmail send failed — check GMAIL_USER and GMAIL_APP_PASS")
    except Exception as e:
        return ApplyResult(status="failed", tier=3, apply_url=apply_url, error=str(e))


def _generate_outreach_body(job: Dict, resume_text: str, profile: Dict) -> str:
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        return _fallback_body(job, resume_text, profile)

    company_info = job.get("companies", {}) or {}
    company_name = company_info.get("name", "") or job.get("company_name", "Unknown")

    prompt = f"""Write a short, personal cold outreach email for this job opportunity.

Role: {job.get('title', 'Unknown')}
Company: {company_name}
Job description snippet: {(job.get('description') or '')[:500]}

Candidate info (from resume):
{resume_text[:800]}

Requirements:
- Very short: 3-4 sentences max
- Personal, direct tone — NOT corporate
- First sentence must hook with specific value (not "I am interested")
- End with a specific CTA (quick call / reply)
- No subject line, no greeting — just the body
- Plain text

Email body:"""

    try:
        from job_scout.ai.gemini import GeminiClient
        gemini = GeminiClient(gemini_key)
        return gemini.generate(prompt, max_tokens=300) or _fallback_body(job, resume_text, profile)
    except Exception:
        return _fallback_body(job, resume_text, profile)


def _fallback_body(job: Dict, resume_text: str, profile: Dict) -> str:
    company_info = job.get("companies", {}) or {}
    company_name = company_info.get("name", "") or job.get("company_name", "Unknown")
    name = profile.get("full_name", "")
    title = job.get("title", "engineering role")
    return (
        f"Hi,\n\n"
        f"I saw your post about the {title} role and wanted to reach out directly. "
        f"I'm a backend engineer with experience in Python, Go, and distributed systems "
        f"— I'd love to chat about whether I'd be a fit.\n\n"
        f"Happy to send my full resume or jump on a quick call.\n\n"
        f"Best,\n{name}"
    )
