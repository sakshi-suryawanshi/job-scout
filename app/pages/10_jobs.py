import streamlit as st
import os
from datetime import datetime
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="Jobs — Job Scout", page_icon="💼", layout="wide")

try:
    from db import get_db
    db = get_db()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

_PREFILLABLE_HOSTS = {
    "boards.greenhouse.io", "job-boards.greenhouse.io",
    "boards.eu.greenhouse.io", "job-boards.eu.greenhouse.io",
    "jobs.ashbyhq.com",
    "jobs.lever.co",
}

def _is_prefillable_url(url: str) -> bool:
    """Return True if this apply_url points at a real application form that
    Playwright can fill. Board listings (HN, LinkedIn, RemoteOK, WWR) and
    discussion pages don't have forms — show just the link for those."""
    if not url:
        return False
    host = urlparse(url).netloc.lower()
    if host in _PREFILLABLE_HOSTS:
        return True
    # Company careers pages with ?gh_jid= embed Greenhouse — rewritable
    if parse_qs(urlparse(url).query).get("gh_jid"):
        return True
    return False


def _gemini_key():
    key = os.getenv("GEMINI_API_KEY", "")
    try:
        key = key or st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        pass
    return key if key and key != "your_gemini_api_key_here" else ""

def _load_browse_prefs():
    """Load saved Browse Jobs filter state from user_profile.preferences."""
    try:
        result = db._request("GET", "user_profile", params={"limit": 1})
        prefs = (result[0].get("preferences") or {}) if result else {}
        return prefs.get("browse_filters", {}) if isinstance(prefs, dict) else {}
    except Exception:
        return {}

def _save_browse_prefs(status: str, source: str, remote: str, sort: str):
    """Persist Browse Jobs filter state to user_profile.preferences."""
    try:
        result = db._request("GET", "user_profile", params={"limit": 1})
        if not result:
            return
        prefs = result[0].get("preferences") or {}
        if not isinstance(prefs, dict):
            prefs = {}
        prefs["browse_filters"] = {"status": status, "source": source, "remote": remote, "sort": sort}
        db._request("PATCH", f"user_profile?id=eq.{result[0]['id']}", json={"preferences": prefs})
    except Exception:
        pass

def _resume_text():
    """Read the raw .tex resume from disk. Gemini receives it as-is.
    Returns "" if the file has not been uploaded yet.
    """
    from pathlib import Path
    tex_path = Path(__file__).parent.parent.parent / "data" / "resume.tex"
    try:
        return tex_path.read_text(encoding="utf-8", errors="replace") if tex_path.exists() else ""
    except Exception:
        return ""

def _score_badge(score):
    # Aligned with RECOMMEND_THRESHOLD=85 in job_scout/ai/gemini.py
    if score >= 85:  return f"🟢 {score}"
    if score >= 70:  return f"🟡 {score}"
    if score >= 50:  return f"🟠 {score}"
    if score >  0:   return f"🔴 {score}"
    return ""

def _action_buttons(job_id, job, db, key_prefix="jc"):
    if st.button("💾 Save",    key=f"{key_prefix}_sv_{job_id}", use_container_width=True):
        db.mark_job_action(job_id, "saved");    st.rerun()
    if st.button("✅ Applied", key=f"{key_prefix}_ap_{job_id}", use_container_width=True):
        db.mark_job_applied(job_id);            st.rerun()
    if st.button("❌ Skip",    key=f"{key_prefix}_sk_{job_id}", use_container_width=True):
        db.mark_job_action(job_id, "rejected"); st.rerun()
    action = job.get("user_action", "")
    if action:
        st.caption(f"Status: **{action}**")

def _job_card(job, *, show_actions=True, key_prefix="jc"):
    company_info = job.get("companies", {}) or {}
    company_name = company_info.get("name", "Unknown")
    score = job.get("match_score", 0) or 0
    desp = job.get("desperation_score", 0) or 0
    source = job.get("source_board", "")
    action = job.get("user_action", "")
    remote_badge = " 🌍" if job.get("is_remote") else ""
    rec_badge = " ⭐" if job.get("is_recommended") else ""
    action_badge = f" [{action}]" if action else ""
    score_str = f" {_score_badge(score)}" if score else ""
    job_id = job.get("id")

    with st.expander(
        f"**{job.get('title', 'Untitled')}** — {company_name}{remote_badge}{score_str}{rec_badge}{action_badge} | {source}"
    ):
        left, right = st.columns([3, 1])
        with left:
            st.write(f"**Company:** {company_name}")
            st.write(f"**Location:** {job.get('location', 'N/A')}")
            source_boards = job.get("source_boards", "") or ""
            if "," in source_boards:
                st.write(f"**Found on:** {source_boards}")
            else:
                st.write(f"**Source:** {source or 'unknown'}")
            st.write(f"**Discovered:** {str(job.get('discovered_at', ''))[:10]}")

            sal_min = job.get("salary_min")
            sal_max = job.get("salary_max")
            if sal_min or sal_max:
                sal_str = f"${sal_min//1000}k" if sal_min else "?"
                sal_str += f" – ${sal_max//1000}k" if sal_max else "+"
                st.write(f"**Salary:** {sal_str}")

            if desp >= 60:
                st.warning(f"Desperation signal: **{desp}/100** — eager to hire!")
            elif desp >= 30:
                st.info(f"Desperation: **{desp}/100**")

            if score > 0:
                st.divider()
                label = {range(80, 101): "Strong match!", range(60, 80): "Decent match",
                         range(40, 60): "Partial match"}.get(next((r for r in [range(80,101),range(60,80),range(40,60)] if score in r), None), "Weak match")
                fn = st.success if score >= 80 else (st.info if score >= 60 else (st.warning if score >= 40 else st.error))
                fn(f"Match Score: **{score}/100** — {label}")
                reason = job.get("match_reason", "")
                if reason:
                    st.write(f"**Why:** {reason}")

            if job.get("apply_url"):
                st.markdown(f"[🔗 Apply Here]({job['apply_url']})")

        with right:
            if show_actions and job_id:
                _action_buttons(job_id, job, db, key_prefix=key_prefix)

                # Tailored resume
                key = _gemini_key()
                if st.button("📄 Tailor Resume", key=f"{key_prefix}_tr_{job_id}", use_container_width=True,
                             disabled=not key, help="Rewrites your .tex resume for this specific job using Gemini"):
                    base = _resume_text()
                    if not base.strip():
                        st.warning("No .tex file found. Go to **Profile → Resume** and upload your `resume.tex` file.")
                    else:
                        from job_scout.ai.gemini import GeminiClient, tailor_resume, fetch_job_description, generate_resume_html
                        os.environ["GEMINI_API_KEY"] = key
                        with st.spinner("Fetching job description from apply URL…"):
                            jd = fetch_job_description(job.get("apply_url", ""))
                        with st.spinner("Gemini tailoring your resume for this role…"):
                            try:
                                gemini = GeminiClient(key)
                                tailored = tailor_resume(gemini, base, job, jd)
                            except Exception as exc:
                                tailored = None
                                st.error(f"Gemini error: {exc}")
                        if tailored:
                            st.session_state[f"tailored_{job_id}"] = tailored
                            st.session_state[f"job_title_{job_id}"] = job.get("title", "Role")
                            st.session_state[f"company_{job_id}"] = company_name
                        else:
                            st.warning(
                                "⚠️ Gemini returned empty — most likely the **rate limit** was hit "
                                "(15 requests/minute on the free tier). "
                                "Wait 60 seconds and click **Tailor Resume** again."
                            )

        # ── Show tailored resume + downloads ──────────────────────────────
        if f"tailored_{job_id}" in st.session_state:
            from job_scout.ai.gemini import generate_resume_html
            t     = st.session_state[f"tailored_{job_id}"]
            title = st.session_state.get(f"job_title_{job_id}", "Role")
            cname = st.session_state.get(f"company_{job_id}", company_name)
            st.divider()
            st.success("✅ Resume tailored for this job. Download and use it when applying manually.")
            st.caption("Gemini rewrote your resume using only your real experience, prioritised to match this role.")
            dc1, dc2, dc3 = st.columns(3)
            with dc1:
                st.download_button(
                    "📥 Download .txt",
                    t,
                    file_name=f"resume_{cname}.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key=f"{key_prefix}_dl_t_{job_id}",
                    help="Plain text — paste into online forms",
                )
            with dc2:
                html = generate_resume_html(t, title, cname)
                st.download_button(
                    "📥 Download .html → PDF",
                    html,
                    file_name=f"resume_{cname}.html",
                    mime="text/html",
                    use_container_width=True,
                    key=f"{key_prefix}_dl_h_{job_id}",
                    help="Open in browser → Cmd+P → Save as PDF",
                )
            with dc3:
                if st.button("✏️ Preview / Edit", use_container_width=True, key=f"{key_prefix}_pr_{job_id}"):
                    st.session_state[f"show_preview_{job_id}"] = not st.session_state.get(f"show_preview_{job_id}", False)
            if st.session_state.get(f"show_preview_{job_id}"):
                st.text_area("Edit before downloading:", value=t, height=350, key=f"{key_prefix}_ta_{job_id}")


# ── Page ─────────────────────────────────────────────────────────────────────
st.title("💼 Jobs")

# ── Score audit — show that scoring is working, at a glance ─────────────────
@st.cache_data(ttl=30, show_spinner=False)
def _load_score_audit(limit: int = 50):
    """Recent jobs with their score + gate/reason. TTL=30s so a fresh scrape
    surfaces within half a minute. Click the 🔄 button to force-refresh."""
    try:
        return db._request("GET", "jobs", params={
            "select": "id,title,match_score,match_reason,is_recommended,source_board,discovered_at,companies(name)",
            "order": "discovered_at.desc",
            "limit": limit,
        }) or []
    except Exception as e:
        st.error(f"Score audit query failed: {e}")
        return []

with st.expander("📊 **Score audit** — verify scoring is happening", expanded=False):
    audit_left, audit_right = st.columns([1, 6])
    if audit_left.button("🔄 Refresh", key="audit_refresh"):
        _load_score_audit.clear()
        st.rerun()
    recent = _load_score_audit(limit=200)
    if not recent:
        st.info("No jobs in DB yet. Run a scrape from Discovery → 🚀 Scrape Jobs.")
    else:
        # Distribution
        b85 = sum(1 for j in recent if (j.get("match_score") or 0) >= 85)
        b70 = sum(1 for j in recent if 70 <= (j.get("match_score") or 0) < 85)
        b50 = sum(1 for j in recent if 50 <= (j.get("match_score") or 0) < 70)
        b1  = sum(1 for j in recent if 1 <= (j.get("match_score") or 0) < 50)
        b0  = sum(1 for j in recent if (j.get("match_score") or 0) == 0)

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("⭐ ≥85",   b85)
        m2.metric("🟡 70-84", b70)
        m3.metric("🟠 50-69", b50)
        m4.metric("🔴 1-49",  b1)
        m5.metric("⚫ Gated/0", b0)

        st.caption(
            f"Of the **{len(recent)}** most-recently-discovered jobs, **{b85}** are "
            f"must-apply (score ≥ 85). Gated jobs (score 0) are usually fine — the gate "
            f"reason in the table below tells you why each was rejected."
        )

        # Show top 20 by score, then 5 most-recent gated for debugging
        sorted_jobs = sorted(recent, key=lambda j: -(j.get("match_score") or 0))
        top = sorted_jobs[:20]
        gated = [j for j in recent if (j.get("match_score") or 0) == 0][:5]

        if top:
            st.write("**Top 20 by score (most recent 200 jobs)**")
            rows = [{
                "Score":   j.get("match_score") or 0,
                "⭐":      "⭐" if j.get("is_recommended") else "",
                "Title":   (j.get("title") or "")[:60],
                "Company": ((j.get("companies") or {}) or {}).get("name", "")[:30],
                "Source":  j.get("source_board") or "",
                "Why":     (j.get("match_reason") or "")[:120],
            } for j in top]
            st.dataframe(rows, use_container_width=True, hide_index=True)

        if gated:
            st.write("**Sample of gated jobs (score=0) — confirms gates are firing**")
            rows = [{
                "Title":   (j.get("title") or "")[:60],
                "Company": ((j.get("companies") or {}) or {}).get("name", "")[:30],
                "Source":  j.get("source_board") or "",
                "Gated because": (j.get("match_reason") or "")[:120],
            } for j in gated]
            st.dataframe(rows, use_container_width=True, hide_index=True)

with st.expander("🧹 **Dedup audit** — find and collapse duplicate job rows", expanded=False):
    st.caption(
        "Duplicates accumulate because `normalize_text` rules have changed over time "
        "(e.g. seniority stripping was added later) — older rows store stale fingerprints "
        "that no longer match a fresh insert's fingerprint, so upsert_job misses them."
    )
    dd_col1, dd_col2 = st.columns([1, 1])
    if dd_col1.button("🔍 Dry-run audit (no changes)", use_container_width=True, key="dd_dry"):
        from job_scout.enrichment.dedup import rebuild_fingerprints
        with st.spinner("Scanning…"):
            stats = rebuild_fingerprints(db, dry_run=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Scanned",          stats["scanned"])
        m2.metric("Dupe groups",      stats["groups_with_dupes"])
        m3.metric("Would delete",     stats["rows_deleted"])
        m4.metric("FPs to fix",       stats["fingerprints_fixed"])
        st.info(
            "Dry-run only — nothing was changed. Click **Apply** to actually "
            "delete the duplicates and patch fingerprints."
        )
    if dd_col2.button("⚡ Apply (delete duplicates + fix fingerprints)", use_container_width=True, key="dd_apply", type="primary"):
        from job_scout.enrichment.dedup import rebuild_fingerprints
        progress = st.progress(0)
        status = st.empty()
        def _dd_cb(msg, p):
            status.write(msg)
            progress.progress(min(p, 1.0))
        with st.spinner("Rebuilding fingerprints + collapsing duplicates…"):
            stats = rebuild_fingerprints(db, dry_run=False, progress_callback=_dd_cb)
        progress.progress(1.0)
        status.write("**Done!**")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Scanned",      stats["scanned"])
        m2.metric("Dupe groups",  stats["groups_with_dupes"])
        m3.metric("Deleted",      stats["rows_deleted"])
        m4.metric("FPs fixed",    stats["fingerprints_fixed"])
        st.success(
            f"Removed **{stats['rows_deleted']}** duplicate rows and rebuilt "
            f"**{stats['fingerprints_fixed']}** stale fingerprints. "
            "Future upserts will dedup correctly."
        )
        _load_score_audit.clear()

st.divider()

tab_queue, tab_all, tab_saved, tab_applied, tab_followups, tab_attention = st.tabs([
    "🚀 Apply Queue", "📋 All Jobs", "💾 Saved", "✅ Applied", "🔔 Follow-Ups", "⚠️ Needs Attention"
])


# ── Tab: Apply Queue ──────────────────────────────────────────────────────────
with tab_queue:
    st.subheader("Top Jobs to Apply To")

    c1, c2, c3 = st.columns(3)
    with c1:
        min_score = st.slider("Min match score", 0, 100, 30, key="q_min")
    with c2:
        q_limit = st.slider("Max jobs", 20, 500, 100, key="q_lim")
    with c3:
        sort_q = st.selectbox("Sort by", [
            "Match Score", "Desperation Score", "Combined (Match + Desperation)", "ASAP (Best chance first)"
        ], key="q_sort")

    try:
        queue = db.get_apply_queue(limit=q_limit)
        queue = [j for j in queue if (j.get("match_score", 0) or 0) >= min_score]

        now = datetime.now()
        if sort_q == "Desperation Score":
            queue.sort(key=lambda j: j.get("desperation_score", 0) or 0, reverse=True)
        elif sort_q == "Combined (Match + Desperation)":
            queue.sort(key=lambda j: (j.get("match_score", 0) or 0) + (j.get("desperation_score", 0) or 0), reverse=True)
        elif sort_q == "ASAP (Best chance first)":
            low_comp = {"jobicy", "workingnomads", "arbeitnow", "hackernews", "hackernews_jobs"}
            def _asap(j):
                match = j.get("match_score", 0) or 0
                desp = j.get("desperation_score", 0) or 0
                disc = j.get("discovered_at") or ""
                recency = 0
                try:
                    if (now - datetime.fromisoformat(str(disc)[:19])).days <= 7:
                        recency = 20
                except Exception:
                    pass
                return desp * 2 + match + recency + (10 if j.get("source_board") in low_comp else 0)
            queue.sort(key=_asap, reverse=True)
    except Exception as e:
        st.error(f"Error loading queue: {e}")
        queue = []

    st.write(f"**{len(queue)} jobs** ready to apply")

    # ── Per-job checkboxes + individual cards ─────────────────────────────────
    selected_ids, selected_urls, selected_jobs = [], [], []

    for idx, job in enumerate(queue):
        job_id  = job.get("id", "")
        company = (job.get("companies") or {}).get("name", "?")
        title   = job.get("title", "?")
        score   = job.get("match_score", 0) or 0
        url     = job.get("apply_url", "")

        col_chk, col_card = st.columns([0.05, 0.95])
        with col_chk:
            checked = st.checkbox("", key=f"qq_chk_{job_id}",
                                  label_visibility="collapsed")
        with col_card:
            _job_card(job, key_prefix="qq")

        if checked and url:
            selected_ids.append(job_id)
            selected_urls.append(url)
            selected_jobs.append(job)

    # ── Sticky action bar ──────────────────────────────────────────────────────
    if queue:
        st.divider()
        n = len(selected_ids)

        if n == 0:
            st.caption("☝️ Tick the checkbox next to any job above to select it — then use the buttons below.")
        else:
            st.success(f"**{n} job{'s' if n > 1 else ''} selected**")
            bc1, bc2 = st.columns(2)

            with bc1:
                # Show links to apply manually — st.link_button works as real HTML anchor
                with st.expander(f"🌐 Open {n} apply page{'s' if n > 1 else ''}", expanded=True):
                    for job in selected_jobs:
                        url     = job.get("apply_url", "")
                        company = (job.get("companies") or {}).get("name", "Company")
                        title   = (job.get("title") or "Role")[:45]
                        score   = job.get("match_score", 0) or 0
                        if url:
                            st.link_button(
                                f"↗ {title} @ {company}  ({score})",
                                url,
                                use_container_width=True,
                            )

            with bc2:
                if st.button(f"✅ Mark {n} as Applied",
                             use_container_width=True, type="primary"):
                    for jid in selected_ids:
                        db.mark_job_applied(jid)
                    st.success(f"Marked {n} as applied!")
                    st.rerun()


# ── Tab: All Jobs ─────────────────────────────────────────────────────────────
with tab_all:
    st.subheader("All Jobs in Database")

    _bprefs = _load_browse_prefs()   # restore last session's filter state

    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    with fc1:
        _status_opts = ["All", "New Only", "Saved", "Applied", "Rejected"]
        f_status = st.selectbox("Status", _status_opts, key="all_status",
                                index=_status_opts.index(_bprefs.get("status", "All"))
                                      if _bprefs.get("status") in _status_opts else 0)
    with fc2:
        # Build source list dynamically from DB
        try:
            all_j = db.get_jobs(limit=5000, days=0)
            srcs = sorted({j.get("source_board", "") for j in all_j if j.get("source_board")})
        except Exception:
            srcs = []
            all_j = []
        _src_opts = ["All"] + srcs
        _saved_src = _bprefs.get("source", "All")
        f_source = st.selectbox("Source", _src_opts, key="all_source",
                                index=_src_opts.index(_saved_src) if _saved_src in _src_opts else 0)
    with fc3:
        _rem_opts = ["All", "Remote Only"]
        f_remote = st.selectbox("Location", _rem_opts, key="all_remote",
                                index=_rem_opts.index(_bprefs.get("remote", "All"))
                                      if _bprefs.get("remote") in _rem_opts else 0)
    with fc4:
        search = st.text_input("Search title", key="all_search")
    with fc5:
        _sort_opts = ["Score ↓", "Score ↑", "Newest", "Desperation ↓"]
        sort_all = st.selectbox("Sort by", _sort_opts, key="all_sort",
                                index=_sort_opts.index(_bprefs.get("sort", "Score ↓"))
                                      if _bprefs.get("sort") in _sort_opts else 0)

    # Auto-save filter state so it restores on next visit
    _save_browse_prefs(f_status, f_source, f_remote, sort_all)

    jobs = all_j if all_j else []
    if f_status == "New Only":  jobs = [j for j in jobs if j.get("is_new")]
    elif f_status == "Saved":   jobs = [j for j in jobs if j.get("user_action") == "saved"]
    elif f_status == "Applied": jobs = [j for j in jobs if j.get("user_action") == "applied"]
    elif f_status == "Rejected":jobs = [j for j in jobs if j.get("user_action") == "rejected"]
    if f_source != "All":       jobs = [j for j in jobs if j.get("source_board") == f_source]
    if f_remote == "Remote Only": jobs = [j for j in jobs if j.get("is_remote")]
    if search:                  jobs = [j for j in jobs if search.lower() in (j.get("title") or "").lower()]

    if sort_all == "Score ↓":   jobs.sort(key=lambda j: j.get("match_score", 0) or 0, reverse=True)
    elif sort_all == "Score ↑": jobs.sort(key=lambda j: j.get("match_score", 0) or 0)
    elif sort_all == "Desperation ↓": jobs.sort(key=lambda j: j.get("desperation_score", 0) or 0, reverse=True)

    st.write(f"Showing **{len(jobs)}** jobs")
    for job in jobs[:200]:
        _job_card(job, key_prefix="all")
    if len(jobs) > 200:
        st.caption(f"Showing first 200 of {len(jobs)}. Use filters to narrow down.")


# ── Tab: Saved ────────────────────────────────────────────────────────────────
with tab_saved:
    st.subheader("Saved Jobs")
    try:
        saved = [j for j in db.get_jobs(limit=5000, days=0) if j.get("user_action") == "saved"]
    except Exception:
        saved = []
    st.write(f"**{len(saved)}** saved")
    for job in saved:
        _job_card(job, key_prefix="sv")


# ── Tab: Applied ──────────────────────────────────────────────────────────────
with tab_applied:
    st.subheader("Applied Jobs")
    try:
        applied = [j for j in db.get_jobs(limit=5000, days=0)
                   if j.get("user_action") in ("applied", "responded", "interview", "interviewing")]
        applied.sort(key=lambda j: j.get("applied_date") or "0000-00-00", reverse=True)
    except Exception:
        applied = []

    # Funnel metrics
    responded = [j for j in applied if j.get("user_action") in ("responded",)]
    interviews = [j for j in applied if j.get("user_action") in ("interview", "interviewing")]
    m1, m2, m3 = st.columns(3)
    m1.metric("Total applied", len(applied))
    m2.metric("Responses", len(responded))
    m3.metric("Interviews", len(interviews))
    if applied:
        rr = len(responded) / len(applied) * 100
        ir = len(interviews) / len(applied) * 100
        st.caption(f"Response rate: {rr:.1f}%  |  Interview rate: {ir:.1f}%")
    st.divider()

    for job in applied[:200]:
        _job_card(job, key_prefix="ap")


# ── Tab: Follow-Ups ───────────────────────────────────────────────────────────
with tab_followups:
    st.subheader("Follow-Up Reminders")
    st.caption("Jobs you applied to where 5+ days have passed with no response.")
    try:
        followups = db.get_follow_ups_due()
    except Exception as e:
        st.error(f"Error: {e}")
        followups = []

    if followups:
        st.write(f"**{len(followups)} follow-ups due**")
        for job in followups:
            company_info = job.get("companies", {}) or {}
            company_name = company_info.get("name", "Unknown")
            applied_d = str(job.get("applied_date", ""))[:10]
            follow_d = str(job.get("follow_up_date", ""))[:10]

            with st.expander(f"**{job.get('title', 'Untitled')}** — {company_name} | Applied: {applied_d} | Due: {follow_d}"):
                left, right = st.columns([3, 1])
                with left:
                    if job.get("apply_url"):
                        st.markdown(f"[🔗 Open Job Page]({job['apply_url']})")
                    st.write(f"Applied: {applied_d}  |  Follow-up due: {follow_d}")
                with right:
                    jid = job.get("id")
                    if jid:
                        if st.button("⏰ Snooze 3d", key=f"snz_{jid}", use_container_width=True):
                            db.snooze_follow_up(jid, 3); st.rerun()
                        if st.button("💬 Got Response", key=f"rsp_{jid}", use_container_width=True):
                            db.mark_job_action(jid, "responded"); st.rerun()
                        if st.button("🎉 Interview", key=f"int_{jid}", use_container_width=True):
                            db.mark_job_action(jid, "interview"); st.rerun()
                        if st.button("❌ Rejected", key=f"rej_{jid}", use_container_width=True):
                            db.mark_job_action(jid, "rejected"); st.rerun()
    else:
        st.success("No follow-ups due right now!")


# ── Tab: Needs Attention ──────────────────────────────────────────────────────
with tab_attention:
    st.subheader("⚠️ Needs Attention")
    st.caption("Jobs the pipeline couldn't auto-apply to — Tier 2 semi-auto with pre-filled values.")

    try:
        attention_jobs = [j for j in db.get_jobs(limit=5000, days=0)
                         if j.get("user_action") == "needs_attention"]
    except Exception:
        attention_jobs = []

    if not attention_jobs:
        st.info("Nothing needs attention. The pipeline will populate this when it finds non-Greenhouse/Lever/Ashby jobs that match your rules.")
    else:
        st.write(f"**{len(attention_jobs)} jobs** need a quick manual apply (~20 seconds each)")

        for job in attention_jobs:
            company_info = job.get("companies", {}) or {}
            company_name = company_info.get("name", "Unknown")
            ats = (company_info.get("ats_type") or "unknown")

            with st.expander(f"**{job.get('title', 'Untitled')}** — {company_name} | ATS: {ats}"):
                left, right = st.columns([3, 1])

                with left:
                    if job.get("apply_url"):
                        st.markdown(f"[🔗 Open Application Page]({job['apply_url']})")

                    # Prefill & Open: only for URLs with real application forms.
                    # HN, LinkedIn, Reddit, board listings don't have forms.
                    _can_prefill = _is_prefillable_url(job.get("apply_url", ""))
                    if _can_prefill and st.button(
                        "🚀 Prefill & Open in Browser", key=f"pf_{job['id']}",
                        use_container_width=True, type="primary",
                    ):
                        resume = _resume_text()
                        if not resume:
                            st.warning("Upload your resume first (Profile → Resume).")
                        else:
                            with st.spinner("Opening browser and prefilling form…"):
                                try:
                                    from job_scout.application.orchestrator import prefill_and_open
                                    result = prefill_and_open(job, resume, db=db)
                                    if result.screenshot_path:
                                        st.image(result.screenshot_path, caption="Prefilled form")
                                    st.info(result.notes or "Form opened — switch to the browser window to review and submit.")
                                except Exception as e:
                                    st.error(f"Prefill error: {e}")

                    # Show cover letter from applications table if available
                    try:
                        app_record = db._request("GET", "applications", params={
                            "job_id": f"eq.{job['id']}", "limit": 1
                        })
                        if app_record:
                            cover_letter = app_record[0].get("cover_letter", "")
                            if cover_letter:
                                st.text_area("Cover Letter (copy ↓)", value=cover_letter,
                                             height=200, key=f"cl_attn_{job['id']}")
                    except Exception:
                        pass

                with right:
                    jid = job.get("id")
                    if jid:
                        if st.button("✅ Mark Applied", key=f"ma_{jid}", use_container_width=True):
                            db.mark_job_applied(jid); st.rerun()
                        if st.button("❌ Skip", key=f"sa_{jid}", use_container_width=True):
                            db.mark_job_action(jid, "rejected"); st.rerun()
