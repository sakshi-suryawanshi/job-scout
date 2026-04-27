import streamlit as st
import os

st.set_page_config(page_title="Dashboard — Job Scout", page_icon="🏠", layout="wide")

try:
    from db import get_db
    db = get_db()
    db_ok = True
except Exception as e:
    st.error(f"Database error: {e}")
    db_ok = False
    st.stop()

# ── helpers ──────────────────────────────────────────────────────────────────

def _count(table: str, filters: dict = None) -> int:
    try:
        params = {"select": "id", "limit": 1, **(filters or {})}
        result = db._request("GET", table, params={
            **params, "select": "id",
        }, headers={**db.headers, "Prefer": "count=exact", "Range": "0-0"})
        resp = db.client.get(
            f"{db.rest_url}/{table}",
            params={**{k: v for k, v in (filters or {}).items()}, "select": "id", "limit": 0},
            headers={**db.headers, "Prefer": "count=exact"},
        )
        count_header = resp.headers.get("Content-Range", "0/0")
        total = count_header.split("/")[-1]
        return int(total) if total != "*" else 0
    except Exception:
        return 0


@st.cache_data(ttl=60, show_spinner=False)
def load_funnel():
    try:
        jobs = db.get_jobs(limit=5000, days=0)
        companies = db.get_companies(active_only=True)
        applied = [j for j in jobs if j.get("user_action") in ("applied", "responded", "interview", "interviewing")]
        responded = [j for j in jobs if j.get("user_action") in ("responded",)]
        interviews = [j for j in jobs if j.get("user_action") in ("interview", "interviewing")]
        recommended = [j for j in jobs if j.get("match_score", 0) >= 70]
        scored = [j for j in jobs if j.get("match_score", 0) > 0]
        saved = [j for j in jobs if j.get("user_action") == "saved"]
        return {
            "companies": len(companies),
            "jobs": len(jobs),
            "scored": len(scored),
            "recommended": len(recommended),
            "saved": len(saved),
            "applied": len(applied),
            "responded": len(responded),
            "interviews": len(interviews),
        }
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def load_quota():
    try:
        from job_scout.db.repositories.usage import get_usage_today, get_usage_monthly
        return {
            "gemini": get_usage_today("gemini"),
            "serper": get_usage_monthly("serper"),
            "gmail": get_usage_today("gmail"),
        }
    except Exception:
        return {}


@st.cache_data(ttl=60, show_spinner=False)
def load_last_pipeline_run():
    try:
        result = db._request("GET", "pipeline_runs", params={
            "order": "started_at.desc", "limit": 1
        })
        return result[0] if result else None
    except Exception:
        return None


# ── Page ─────────────────────────────────────────────────────────────────────

st.title("🏠 Dashboard")

funnel = load_funnel()
last_run = load_last_pipeline_run()
quota = load_quota()

# ── Funnel metrics ────────────────────────────────────────────────────────────
st.subheader("Job Hunt Funnel")

cols = st.columns(8)
labels = [
    ("🏢 Companies", funnel.get("companies", 0)),
    ("📥 Discovered", funnel.get("jobs", 0)),
    ("🤖 Scored", funnel.get("scored", 0)),
    ("⭐ Recommended", funnel.get("recommended", 0)),
    ("💾 Saved", funnel.get("saved", 0)),
    ("✅ Applied", funnel.get("applied", 0)),
    ("💬 Responses", funnel.get("responded", 0)),
    ("🎯 Interviews", funnel.get("interviews", 0)),
]
for col, (label, val) in zip(cols, labels):
    col.metric(label, val)

# ── Goal progress ─────────────────────────────────────────────────────────────
applied = funnel.get("applied", 0)
goal = 1000
progress = applied / goal
st.progress(min(progress, 1.0), text=f"**{applied} / {goal}** applications — {progress*100:.1f}% of goal")

resp_rate = (funnel.get("responded", 0) / applied * 100) if applied else 0
int_rate = (funnel.get("interviews", 0) / applied * 100) if applied else 0
rc1, rc2 = st.columns(2)
rc1.metric("Response rate", f"{resp_rate:.1f}%")
rc2.metric("Interview rate", f"{int_rate:.1f}%")

st.divider()

# ── Pipeline status + Quota ───────────────────────────────────────────────────
left, right = st.columns(2)

with left:
    st.subheader("Pipeline")
    if last_run:
        status = last_run.get("status", "unknown")
        started = str(last_run.get("started_at", ""))[:16]
        triggered = last_run.get("triggered_by", "manual")
        icon = {"success": "✅", "partial": "⚠️", "failed": "❌", "running": "🔄"}.get(status, "❓")
        st.write(f"{icon} Last run: **{started}** ({triggered}) — {status}")
        stats = last_run.get("stats") or {}
        if stats:
            s_cols = st.columns(3)
            s_cols[0].metric("Found", stats.get("jobs_found", 0))
            s_cols[1].metric("Applied", stats.get("auto_applied", 0))
            s_cols[2].metric("Need attention", stats.get("needs_attention", 0))
    else:
        st.info("No pipeline runs yet. Configure Auto-Pilot to get started.")

    if st.button("▶ Run Pipeline Now", use_container_width=True):
        st.switch_page("pages/40_pipeline.py")

with right:
    st.subheader("Quota")
    if quota:
        for provider, data in quota.items():
            label = {"gemini": "Gemini (daily)", "serper": "Serper (monthly)", "gmail": "Gmail (daily)"}.get(provider, provider)
            calls = data.get("calls", 0)
            lim = data.get("limit", 1)
            pct = calls / lim if lim else 0
            color = "🟢" if pct < 0.7 else ("🟡" if pct < 0.9 else "🔴")
            st.progress(min(pct, 1.0), text=f"{color} {label}: {calls}/{lim} ({pct*100:.0f}%)")
    else:
        st.caption("Quota tracking requires api_usage table (migration 009 ✅)")

st.divider()

# ── Quick actions ─────────────────────────────────────────────────────────────
st.subheader("Quick Actions")
qa1, qa2, qa3, qa4 = st.columns(4)

with qa1:
    if st.button("🔍 Find Jobs", use_container_width=True, type="primary"):
        st.switch_page("pages/30_discovery.py")
with qa2:
    if st.button("💼 Apply Queue", use_container_width=True):
        st.switch_page("pages/10_jobs.py")
with qa3:
    if st.button("🏢 Companies", use_container_width=True):
        st.switch_page("pages/20_companies.py")
with qa4:
    if st.button("🤖 Auto-Pilot", use_container_width=True):
        st.switch_page("pages/40_pipeline.py")
