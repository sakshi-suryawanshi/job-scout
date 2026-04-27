import streamlit as st
import os
from datetime import datetime

st.set_page_config(page_title="Jobs — Job Scout", page_icon="💼", layout="wide")

try:
    from db import get_db
    db = get_db()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

def _gemini_key():
    key = os.getenv("GEMINI_API_KEY", "")
    try:
        key = key or st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        pass
    return key if key and key != "your_gemini_api_key_here" else ""

def _resume_text():
    try:
        result = db._request("GET", "user_profile", params={"limit": 1})
        return (result[0].get("resume_text", "") or "") if result else ""
    except Exception:
        return ""

def _score_badge(score):
    if score >= 80:  return f"🟢 {score}"
    if score >= 60:  return f"🟡 {score}"
    if score >= 40:  return f"🟠 {score}"
    if score >  0:   return f"🔴 {score}"
    return ""

def _action_buttons(job_id, job, db):
    if st.button("💾 Save",    key=f"sv_{job_id}", use_container_width=True):
        db.mark_job_action(job_id, "saved");    st.rerun()
    if st.button("✅ Applied", key=f"ap_{job_id}", use_container_width=True):
        db.mark_job_applied(job_id);            st.rerun()
    if st.button("❌ Skip",    key=f"sk_{job_id}", use_container_width=True):
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
                _action_buttons(job_id, job, db)

                # Tailored resume
                key = _gemini_key()
                if st.button("📄 Tailor Resume", key=f"tr_{job_id}", use_container_width=True,
                             disabled=not key, help="Set GEMINI_API_KEY to enable"):
                    base = _resume_text()
                    if not base.strip():
                        st.warning("No resume found. Go to Profile → Resume first.")
                    else:
                        from job_scout.ai.gemini import GeminiClient, tailor_resume, fetch_job_description, generate_resume_html
                        os.environ["GEMINI_API_KEY"] = key
                        with st.spinner("Fetching job description..."):
                            jd = fetch_job_description(job.get("apply_url", ""))
                        with st.spinner("Tailoring resume..."):
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

        # Show tailored resume if generated
        if f"tailored_{job_id}" in st.session_state:
            from job_scout.ai.gemini import generate_resume_html
            t = st.session_state[f"tailored_{job_id}"]
            title = st.session_state.get(f"job_title_{job_id}", "Role")
            cname = st.session_state.get(f"company_{job_id}", company_name)
            st.divider()
            st.markdown("**Tailored Resume**")
            st.text_area("Edit or copy:", value=t, height=350, key=f"ta_{job_id}")
            dc1, dc2 = st.columns(2)
            with dc1:
                st.download_button("📥 .txt", t, f"resume_{cname}.txt", key=f"dl_t_{job_id}")
            with dc2:
                st.download_button("📥 .html (→ PDF)", generate_resume_html(t, title, cname),
                                   f"resume_{cname}.html", mime="text/html", key=f"dl_h_{job_id}")


# ── Page ─────────────────────────────────────────────────────────────────────
st.title("💼 Jobs")

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

    selected_ids, selected_urls = [], []
    sel_all = st.checkbox("Select first 20 for bulk open", key="q_sel_all")

    for idx, job in enumerate(queue):
        _job_card(job, key_prefix="qq")
        job_id = job.get("id")
        if sel_all and idx < 20 and job.get("apply_url"):
            selected_ids.append(job_id)
            selected_urls.append(job["apply_url"])

    if queue:
        st.divider()
        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button(f"🌐 Open {len(selected_urls)} in browser", type="primary",
                         use_container_width=True, disabled=not selected_urls):
                js = "\n".join(f'window.open("{u}", "_blank");' for u in selected_urls[:20])
                st.components.v1.html(f"<script>{js}</script>", height=0)
                st.success(f"Opened {min(len(selected_urls), 20)} tabs!")
        with bc2:
            if st.button(f"✅ Mark {len(selected_ids)} as Applied",
                         use_container_width=True, disabled=not selected_ids):
                for jid in selected_ids:
                    db.mark_job_applied(jid)
                st.success(f"Marked {len(selected_ids)} as applied!")
                st.rerun()


# ── Tab: All Jobs ─────────────────────────────────────────────────────────────
with tab_all:
    st.subheader("All Jobs in Database")

    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    with fc1:
        f_status = st.selectbox("Status", ["All", "New Only", "Saved", "Applied", "Rejected"], key="all_status")
    with fc2:
        # Build source list dynamically from DB
        try:
            all_j = db.get_jobs(limit=5000, days=0)
            srcs = sorted({j.get("source_board", "") for j in all_j if j.get("source_board")})
        except Exception:
            srcs = []
            all_j = []
        f_source = st.selectbox("Source", ["All"] + srcs, key="all_source")
    with fc3:
        f_remote = st.selectbox("Location", ["All", "Remote Only"], key="all_remote")
    with fc4:
        search = st.text_input("Search title", key="all_search")
    with fc5:
        sort_all = st.selectbox("Sort by", ["Score ↓", "Score ↑", "Newest", "Desperation ↓"], key="all_sort")

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
        applied.sort(key=lambda j: j.get("applied_date") or "", reverse=True)
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
                    st.caption("Pre-filled values to copy-paste into the form:")

                    # Show pre-filled values from applications table if available
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
                        if st.button("✅ Mark Applied", key=f"ma_{jid}", use_container_width=True, type="primary"):
                            db.mark_job_applied(jid); st.rerun()
                        if st.button("❌ Skip", key=f"sa_{jid}", use_container_width=True):
                            db.mark_job_action(jid, "rejected"); st.rerun()
