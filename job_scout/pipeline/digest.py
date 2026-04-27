# job_scout/pipeline/digest.py
"""Build the daily email digest HTML from pipeline run stats."""

import html as html_lib
from datetime import date, datetime
from typing import Dict, List


def build_digest_html(db, run_stats: Dict, config: Dict = None) -> str:
    """Compose a full HTML digest email from pipeline stats + live DB data."""
    config = config or {}
    today = date.today().strftime("%B %-d, %Y")

    scrape_stats  = run_stats.get("scrape", {})
    score_stats   = run_stats.get("score", {})
    auto_stats    = run_stats.get("auto_apply", {})
    follow_stats  = run_stats.get("follow_ups", {})
    discover_stats = run_stats.get("discover", {})

    # Pull live data for digest sections
    try:
        all_jobs = db.get_jobs(limit=5000, days=0)
        applied = [j for j in all_jobs if j.get("user_action") in ("applied", "responded", "interview", "interviewing")]
        responded = [j for j in all_jobs if j.get("user_action") == "responded"]
        interviews = [j for j in all_jobs if j.get("user_action") in ("interview", "interviewing")]
        top_new = sorted(
            [j for j in all_jobs if j.get("is_new") and (j.get("match_score", 0) or 0) >= 70],
            key=lambda j: j.get("match_score", 0) or 0,
            reverse=True,
        )[:5]
        follow_ups = db.get_follow_ups_due()[:5]
    except Exception:
        applied = responded = interviews = top_new = follow_ups = []

    total_applied = len(applied)
    resp_rate = f"{len(responded)/total_applied*100:.1f}%" if total_applied else "—"
    int_rate  = f"{len(interviews)/total_applied*100:.1f}%" if total_applied else "—"

    def _e(text: str) -> str:
        return html_lib.escape(str(text))

    def _job_row(job) -> str:
        company_info = job.get("companies", {}) or {}
        company = company_info.get("name", "Unknown")
        title = job.get("title", "Unknown")
        score = job.get("match_score", 0) or 0
        url = job.get("apply_url", "")
        link = f'<a href="{_e(url)}" style="color:#0066cc">{_e(title)}</a>' if url else _e(title)
        return f"<li>{link} @ {_e(company)} — score {score}</li>"

    sections = []

    # ── 📊 Pipeline summary ─────────────────────────────────────────────────
    pipeline_rows = []
    if discover_stats.get("new_companies"):
        pipeline_rows.append(f"<tr><td>New companies discovered</td><td><b>{discover_stats['new_companies']}</b></td></tr>")
    if scrape_stats.get("jobs_new"):
        pipeline_rows.append(f"<tr><td>New jobs scraped</td><td><b>{scrape_stats['jobs_new']}</b></td></tr>")
    if score_stats.get("total_scored"):
        avg = score_stats.get("avg_score", 0)
        pipeline_rows.append(f"<tr><td>Jobs scored</td><td><b>{score_stats['total_scored']}</b> (avg {avg})</td></tr>")
    if auto_stats.get("would_apply"):
        pipeline_rows.append(f"<tr><td>Queued for auto-apply</td><td><b>{auto_stats['would_apply']}</b></td></tr>")
    if auto_stats.get("needs_attention"):
        pipeline_rows.append(f"<tr><td>Need your attention</td><td><b>{auto_stats['needs_attention']}</b></td></tr>")
    if follow_stats.get("follow_ups_due"):
        pipeline_rows.append(f"<tr><td>Follow-ups due today</td><td><b>{follow_stats['follow_ups_due']}</b></td></tr>")

    if pipeline_rows:
        sections.append(f"""
<h2 style="color:#333;border-bottom:2px solid #eee;padding-bottom:4px">📊 Pipeline</h2>
<table style="border-collapse:collapse;width:100%">
  {"".join(pipeline_rows)}
</table>""")

    # ── ⭐ Top new recommended ───────────────────────────────────────────────
    if top_new:
        jobs_html = "\n".join(_job_row(j) for j in top_new)
        sections.append(f"""
<h2 style="color:#333;border-bottom:2px solid #eee;padding-bottom:4px">⭐ Top New Recommended</h2>
<ul style="padding-left:20px">{jobs_html}</ul>""")

    # ── ⚠️ Needs attention ──────────────────────────────────────────────────
    if auto_stats.get("needs_attention", 0) > 0:
        sections.append(f"""
<h2 style="color:#e65c00;border-bottom:2px solid #eee;padding-bottom:4px">⚠️ Needs Your Attention ({auto_stats['needs_attention']})</h2>
<p style="color:#666">These jobs matched your rules but need manual apply (non-Greenhouse/Lever/Ashby ATS). Check Jobs → Apply Queue.</p>""")

    # ── 🔔 Follow-ups due ───────────────────────────────────────────────────
    if follow_ups:
        fu_html = "\n".join(
            f"<li>{_e(j.get('title','?'))} — applied {str(j.get('applied_date',''))[:10]}</li>"
            for j in follow_ups
        )
        sections.append(f"""
<h2 style="color:#333;border-bottom:2px solid #eee;padding-bottom:4px">🔔 Follow-Ups Due ({len(follow_ups)})</h2>
<ul style="padding-left:20px">{fu_html}</ul>""")

    # ── 📈 Progress ─────────────────────────────────────────────────────────
    sections.append(f"""
<h2 style="color:#333;border-bottom:2px solid #eee;padding-bottom:4px">📈 Progress</h2>
<table style="border-collapse:collapse;width:100%">
  <tr><td>Total applied</td><td><b>{total_applied}</b> / 1000 ({total_applied/10:.1f}%)</td></tr>
  <tr><td>Response rate</td><td><b>{resp_rate}</b></td></tr>
  <tr><td>Interview rate</td><td><b>{int_rate}</b></td></tr>
</table>""")

    body = "\n".join(sections) or "<p>No significant activity today.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Scout Daily — {_e(today)}</title>
</head>
<body style="font-family:Georgia,serif;font-size:13pt;line-height:1.6;max-width:640px;margin:32px auto;color:#222;padding:0 16px">
<p style="font-size:11pt;color:#888;margin-bottom:4px">Job Scout Daily Digest</p>
<h1 style="margin-top:0;color:#111">{_e(today)}</h1>
{body}
<hr style="border:none;border-top:1px solid #eee;margin-top:32px">
<p style="font-size:9pt;color:#aaa">Sent by Job Scout V2 · <a href="https://github.com" style="color:#aaa">GitHub</a></p>
</body>
</html>"""
