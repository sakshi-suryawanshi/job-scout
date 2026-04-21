import streamlit as st
import os
import sys

st.set_page_config(page_title="Apply", page_icon="🚀", layout="wide")

st.title("🚀 Bulk Apply")
st.markdown("Apply to jobs fast — open in browser, track applications, follow up")

# Import db
try:
    from db import get_db
    db = get_db()
except Exception as e:
    st.error(f"Database error: {e}")

# Import Gemini + resume helpers
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "worker", "ai"))
try:
    from gemini_client import GeminiClient, tailor_resume, fetch_job_description, generate_resume_html
    _gemini_key = os.getenv("GEMINI_API_KEY", "")
    try:
        _gemini_key = _gemini_key or st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        pass
    HAS_GEMINI = bool(_gemini_key and _gemini_key != "your_gemini_api_key_here")
except Exception:
    HAS_GEMINI = False


def _get_user_resume() -> str:
    """Load the user's base resume from Supabase."""
    try:
        result = db._request("GET", "user_profile", params={"limit": 1})
        if result:
            return result[0].get("resume_text", "") or ""
    except Exception:
        pass
    return ""
    st.stop()

# ========== TABS ==========
tab1, tab2, tab3 = st.tabs(["📋 Apply Queue", "🔔 Follow-Ups", "📊 Progress"])

# ========== TAB 1: APPLY QUEUE ==========
with tab1:
    st.subheader("Top Jobs to Apply")
    st.markdown("Jobs sorted by match score. Select jobs, open in browser, mark as applied.")

    qcol1, qcol2, qcol3 = st.columns(3)
    with qcol1:
        min_score = st.slider("Min match score", 0, 100, 30, key="q_score")
    with qcol2:
        queue_limit = st.slider("Max jobs to show", 20, 500, 100, key="q_limit")
    with qcol3:
        sort_queue = st.selectbox("Sort by", [
            "Match Score",
            "Desperation Score",
            "Combined (Match + Desperation)",
            "ASAP Hire (Best Chance First)",
        ], key="q_sort")

    # Fetch jobs
    try:
        from datetime import datetime, timedelta
        queue_jobs = db.get_apply_queue(limit=queue_limit)
        # Filter by min score
        queue_jobs = [j for j in queue_jobs if (j.get("match_score", 0) or 0) >= min_score]

        # Sort
        if sort_queue == "Desperation Score":
            queue_jobs.sort(key=lambda j: (j.get("desperation_score", 0) or 0), reverse=True)
        elif sort_queue == "Combined (Match + Desperation)":
            queue_jobs.sort(
                key=lambda j: (j.get("match_score", 0) or 0) + (j.get("desperation_score", 0) or 0),
                reverse=True,
            )
        elif sort_queue == "ASAP Hire (Best Chance First)":
            # Composite: desperation*2 + match + recency bonus (jobs posted <7 days ago get +20)
            now = datetime.now()
            def _asap_score(j):
                match = j.get("match_score", 0) or 0
                desp = j.get("desperation_score", 0) or 0
                # Recency: jobs discovered in last 7 days get bonus
                disc = j.get("discovered_at") or j.get("discovered_date") or ""
                recency_bonus = 0
                try:
                    disc_dt = datetime.fromisoformat(str(disc)[:19])
                    if (now - disc_dt).days <= 7:
                        recency_bonus = 20
                except Exception:
                    pass
                # Small-board bonus: fewer competitors
                low_comp = {"jobicy", "workingnomads", "arbeitnow", "hackernews", "hackernews_jobs"}
                board_bonus = 10 if j.get("source_board") in low_comp else 0
                return desp * 2 + match + recency_bonus + board_bonus
            queue_jobs.sort(key=_asap_score, reverse=True)
        # else: already sorted by match_score from DB
    except Exception as e:
        st.error(f"Error loading queue: {e}")
        queue_jobs = []

    st.write(f"**{len(queue_jobs)} jobs** ready to apply")

    if queue_jobs:
        # Select all / none
        select_col1, select_col2, select_col3 = st.columns([1, 1, 4])
        with select_col1:
            select_all = st.checkbox("Select first 20", key="sel_all")

        selected_ids = []
        selected_urls = []

        for idx, job in enumerate(queue_jobs):
            company_info = job.get("companies", {}) or {}
            company_name = company_info.get("name", "Unknown")
            score = job.get("match_score", 0) or 0
            desp = job.get("desperation_score", 0) or 0

            score_badge = f"Match: {score}" if score > 0 else ""
            desp_badge = f" | Desp: {desp}" if desp > 0 else ""
            sal_min = job.get("salary_min")
            sal_max = job.get("salary_max")
            if sal_min and sal_max:
                sal_badge = f" | ${sal_min//1000}k-${sal_max//1000}k"
            elif sal_min:
                sal_badge = f" | ${sal_min//1000}k+"
            else:
                sal_badge = ""

            checked = select_all and idx < 20

            with st.expander(
                f"**{job.get('title', 'Untitled')}** — {company_name} | {score_badge}{desp_badge}{sal_badge}",
                expanded=False,
            ):
                job_id = job.get("id", idx)

                ecol1, ecol2 = st.columns([3, 1])
                with ecol1:
                    is_selected = st.checkbox(
                        "Select for bulk apply",
                        value=checked,
                        key=f"q_{job_id}",
                    )
                    if job.get("apply_url"):
                        st.markdown(f"[Open job page]({job['apply_url']})")
                    if job.get("match_reason"):
                        st.caption(f"Why: {job['match_reason']}")

                with ecol2:
                    resume_btn_disabled = not HAS_GEMINI
                    resume_btn_help = "Set GEMINI_API_KEY in .env to enable" if not HAS_GEMINI else "Generate a tailored resume for this job"
                    if st.button(
                        "Generate Tailored Resume",
                        key=f"resume_{job_id}",
                        use_container_width=True,
                        disabled=resume_btn_disabled,
                        help=resume_btn_help,
                    ):
                        base_resume = _get_user_resume()
                        if not base_resume.strip():
                            st.warning("No resume found. Go to Profile page and paste your resume first.")
                        else:
                            with st.spinner("Fetching job page..."):
                                jd_text = fetch_job_description(job.get("apply_url", ""))
                            with st.spinner("Tailoring resume with Gemini..."):
                                try:
                                    gemini = GeminiClient(_gemini_key)
                                    tailored = tailor_resume(gemini, base_resume, job, jd_text)
                                except Exception as e:
                                    tailored = None
                                    st.error(f"Gemini error: {e}")

                            if tailored:
                                st.session_state[f"tailored_{job_id}"] = tailored
                                st.session_state[f"company_{job_id}"] = company_name
                                st.session_state[f"title_{job_id}"] = job.get("title", "Role")
                            else:
                                st.error("Failed to generate tailored resume. Try again.")

                # Show tailored resume if generated
                tailored_key = f"tailored_{job_id}"
                if tailored_key in st.session_state:
                    tailored_text = st.session_state[tailored_key]
                    saved_title = st.session_state.get(f"title_{job_id}", job.get("title", "Role"))
                    saved_company = st.session_state.get(f"company_{job_id}", company_name)

                    st.divider()
                    st.markdown("**Tailored Resume**")
                    st.text_area(
                        "Copy or edit below",
                        value=tailored_text,
                        height=400,
                        key=f"ta_{job_id}",
                    )
                    dl_col1, dl_col2 = st.columns(2)
                    with dl_col1:
                        st.download_button(
                            "Download .txt",
                            data=tailored_text,
                            file_name=f"resume_{saved_company.replace(' ', '_')}_{saved_title.replace(' ', '_')}.txt",
                            mime="text/plain",
                            key=f"dl_txt_{job_id}",
                            use_container_width=True,
                        )
                    with dl_col2:
                        html_content = generate_resume_html(tailored_text, saved_title, saved_company)
                        st.download_button(
                            "Download .html (open & print to PDF)",
                            data=html_content,
                            file_name=f"resume_{saved_company.replace(' ', '_')}_{saved_title.replace(' ', '_')}.html",
                            mime="text/html",
                            key=f"dl_html_{job_id}",
                            use_container_width=True,
                        )

                if is_selected and job.get("apply_url"):
                    selected_ids.append(job["id"])
                    selected_urls.append(job["apply_url"])

        st.divider()

        bcol1, bcol2 = st.columns(2)

        with bcol1:
            if st.button(
                f"🌐 Open {len(selected_urls)} Jobs in Browser",
                use_container_width=True,
                type="primary",
                disabled=len(selected_urls) == 0,
            ):
                # Open URLs in browser tabs via JavaScript
                # Cap at 20 per batch to avoid popup blocking
                batch = selected_urls[:20]
                js_lines = [f'window.open("{url}", "_blank");' for url in batch]
                js_code = "\n".join(js_lines)
                st.components.v1.html(
                    f"<script>{js_code}</script>",
                    height=0,
                )
                if len(selected_urls) > 20:
                    st.info(f"Opened first 20 of {len(selected_urls)}. Click again for the next batch.")
                else:
                    st.success(f"Opened {len(batch)} job pages in browser tabs!")

        with bcol2:
            if st.button(
                f"✅ Mark {len(selected_ids)} as Applied",
                use_container_width=True,
                disabled=len(selected_ids) == 0,
            ):
                applied_count = 0
                for job_id in selected_ids:
                    if db.mark_job_applied(job_id):
                        applied_count += 1
                st.success(f"Marked {applied_count} jobs as applied! Follow-up reminders set for 5 days.")
                st.rerun()
    else:
        st.info("No jobs in queue. Run scraping and scoring first!")


# ========== TAB 2: FOLLOW-UPS ==========
with tab2:
    st.subheader("Follow-Up Reminders")
    st.markdown("Jobs you applied to where follow-up is due")

    try:
        follow_ups = db.get_follow_ups_due()
    except Exception as e:
        st.error(f"Error: {e}")
        follow_ups = []

    if follow_ups:
        st.write(f"**{len(follow_ups)} follow-ups due**")

        for job in follow_ups:
            company_info = job.get("companies", {}) or {}
            company_name = company_info.get("name", "Unknown")
            applied = str(job.get("applied_date", ""))[:10]
            follow_date = str(job.get("follow_up_date", ""))[:10]

            with st.expander(f"**{job.get('title', 'Untitled')}** — {company_name} | Applied: {applied} | Follow-up: {follow_date}"):
                fcol1, fcol2 = st.columns([3, 1])
                with fcol1:
                    if job.get("apply_url"):
                        st.markdown(f"[Open Job Page]({job['apply_url']})")
                    st.write(f"**Applied:** {applied}")
                    st.write(f"**Follow-up due:** {follow_date}")

                    snippet = job.get("cover_letter_snippet", "")
                    if snippet:
                        st.write(f"**Cover letter snippet:** {snippet}")

                with fcol2:
                    job_id = job.get("id")
                    if job_id:
                        if st.button("⏰ Snooze 3 days", key=f"snz_{job_id}", use_container_width=True):
                            db.snooze_follow_up(job_id, days=3)
                            st.rerun()
                        if st.button("💬 Got Response", key=f"resp_{job_id}", use_container_width=True):
                            db.mark_job_action(job_id, "responded")
                            st.rerun()
                        if st.button("🎉 Interview", key=f"int_{job_id}", use_container_width=True):
                            db.mark_job_action(job_id, "interview")
                            st.rerun()
                        if st.button("❌ Rejected", key=f"rej_{job_id}", use_container_width=True):
                            db.mark_job_action(job_id, "rejected")
                            st.rerun()
    else:
        st.info("No follow-ups due. Apply to some jobs first!")

    # Also show all applied jobs
    st.divider()
    st.subheader("All Applied Jobs")
    try:
        all_applied = db.get_jobs(limit=1000)
        applied_jobs = [j for j in all_applied if j.get("user_action") == "applied"]
        if applied_jobs:
            st.write(f"**{len(applied_jobs)} total applied**")
            for job in applied_jobs[:50]:
                company_info = job.get("companies", {}) or {}
                company_name = company_info.get("name", "Unknown")
                applied_d = str(job.get("applied_date", ""))[:10]
                st.write(f"- **{job.get('title', 'Untitled')}** — {company_name} | {applied_d}")
        else:
            st.write("No applications yet.")
    except Exception:
        pass


# ========== TAB 3: PROGRESS ==========
with tab3:
    st.subheader("Application Progress")
    st.markdown("Track your progress toward applying to **1000 jobs in 10 days**")

    try:
        all_jobs = db.get_jobs(limit=5000)
    except Exception:
        all_jobs = []

    applied = [j for j in all_jobs if j.get("user_action") in ("applied", "responded", "interview")]
    saved = [j for j in all_jobs if j.get("user_action") == "saved"]
    responded = [j for j in all_jobs if j.get("user_action") == "responded"]
    interviews = [j for j in all_jobs if j.get("user_action") == "interview"]
    rejected = [j for j in all_jobs if j.get("user_action") == "rejected"]

    # Metrics
    mcols = st.columns(5)
    with mcols[0]:
        st.metric("Applied", len(applied))
    with mcols[1]:
        st.metric("Responded", len(responded))
    with mcols[2]:
        st.metric("Interviews", len(interviews))
    with mcols[3]:
        st.metric("Rejected", len(rejected))
    with mcols[4]:
        st.metric("Saved", len(saved))

    # Progress bar toward 1000
    goal = 1000
    progress = len(applied) / goal
    st.progress(min(progress, 1.0))
    st.write(f"**{len(applied)} / {goal}** applications ({progress * 100:.1f}%)")

    remaining = goal - len(applied)
    if remaining > 0:
        st.write(f"**{remaining}** more to go!")
        # Daily rate needed
        days_left = 10
        daily_needed = remaining / days_left
        st.write(f"Need **~{daily_needed:.0f} per day** to hit goal in {days_left} days")
    else:
        st.balloons()
        st.success("Goal reached! You applied to 1000+ jobs!")

    # Response rate
    st.divider()
    st.subheader("Funnel")
    if len(applied) > 0:
        response_rate = (len(responded) + len(interviews)) / len(applied) * 100
        interview_rate = len(interviews) / len(applied) * 100
        st.write(f"- **Response rate:** {response_rate:.1f}%")
        st.write(f"- **Interview rate:** {interview_rate:.1f}%")
    else:
        st.info("Apply to some jobs to see your funnel stats!")

    # Daily breakdown
    st.divider()
    st.subheader("Daily Applications")
    daily = {}
    for job in applied:
        d = str(job.get("applied_date", ""))[:10]
        if d:
            daily[d] = daily.get(d, 0) + 1

    if daily:
        for d in sorted(daily.keys(), reverse=True):
            st.write(f"- **{d}**: {daily[d]} applications")
    else:
        st.write("No applications tracked yet.")


# ========== SIDEBAR ==========
try:
    sidebar_jobs = db.get_jobs(limit=5000)
    applied_count = len([j for j in sidebar_jobs if j.get("user_action") in ("applied", "responded", "interview")])
    total_jobs = len(sidebar_jobs)

    st.sidebar.divider()
    st.sidebar.subheader("Apply Stats")
    st.sidebar.metric("Total Jobs", total_jobs)
    st.sidebar.metric("Applied", applied_count)
    st.sidebar.metric("Goal", f"{applied_count}/1000")
except Exception:
    pass
