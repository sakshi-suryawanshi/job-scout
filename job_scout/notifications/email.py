# job_scout/notifications/email.py
"""Gmail SMTP email sender. Free tier: 500 emails/day (hard-capped at 50 here)."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional


_DAILY_HARD_CAP = 50  # Never send more than 50/day — protects Gmail account reputation


def send_email(
    to: str,
    subject: str,
    html_body: str,
    from_addr: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> bool:
    """
    Send an HTML email via Gmail SMTP.

    Required env vars:
      GMAIL_USER      — your Gmail address (e.g. you@gmail.com)
      GMAIL_APP_PASS  — 16-char app password from Google Account → Security → App passwords

    Returns True on success, False on failure.
    """
    # Support both Gmail-specific and generic SMTP env var names
    gmail_user = from_addr or os.getenv("GMAIL_USER") or os.getenv("SMTP_USER", "")
    gmail_pass = smtp_password or os.getenv("GMAIL_APP_PASS") or os.getenv("SMTP_PASSWORD", "")

    if not gmail_user or not gmail_pass:
        print("email: GMAIL_USER or GMAIL_APP_PASS not set — skipping send")
        return False

    # Enforce daily cap before sending
    try:
        from job_scout.db.repositories.usage import get_usage_today
        usage = get_usage_today("gmail")
        if usage["calls"] >= _DAILY_HARD_CAP:
            print(f"email: daily cap of {_DAILY_HARD_CAP} reached ({usage['calls']} sent today) — skipping")
            return False
    except Exception:
        pass  # Never block a send because quota check failed

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, [to], msg.as_string())
        print(f"email: sent '{subject}' to {to}")
        try:
            from job_scout.db.repositories.usage import record_usage
            record_usage("gmail", 1)
        except Exception:
            pass
        return True
    except smtplib.SMTPAuthenticationError:
        print("email: authentication failed — check GMAIL_USER and GMAIL_APP_PASS")
        return False
    except Exception as e:
        print(f"email: send error — {e}")
        return False
