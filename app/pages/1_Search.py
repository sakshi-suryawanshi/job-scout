import streamlit as st
import os
import sys

st.set_page_config(page_title="Search Jobs", page_icon="🔍", layout="wide")

st.title("🔍 Job Search")
st.markdown("Scrape ATS boards + job boards, filter jobs, find hidden gems")

# Import db
try:
    from db import get_db
    db = get_db()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# Import scrapers
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "worker", "scraping"))
from ats_scrapers import scrape_ats_jobs
from board_scrapers import scrape_board_jobs, _get_enabled_boards
from career_scraper import scrape_career_pages

# Load board manager config to pre-check only enabled boards
_ALL_BOARD_KEYS = [
    "remoteok","remotive","remotive_devops","remotive_data","weworkremotely","wwr_devops",
    "wwr_frontend","himalayas","arbeitnow","themuse","justjoin","hackernews","hackernews_jobs",
    "reddit","reddit_remotejs","jobicy","jobicy_all","workingnomads","workingnomads_devops",
    "jobspresso","wfhio","remoteco","authenticjobs","nodesk","4dayweek","dynamitejobs",
    "freshremote","remotefirstjobs","devitjobs","djangojobs","larajobs","vuejobs","golangjobs",
    "smashingmag","cryptojobslist","web3career","climatebase","powertofly",
]
_enabled_boards = set(_get_enabled_boards(_ALL_BOARD_KEYS))
def _on(key): return key in _enabled_boards

# Import AI scoring
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "worker", "ai"))
from gemini_client import score_all_jobs, GeminiClient

# ========== TABS ==========
tab1, tab2, tab3, tab4 = st.tabs(["🚀 Scrape Jobs", "📋 Browse Jobs", "🤖 Score Jobs", "📊 Stats"])

# ========== TAB 1: SCRAPE ==========
with tab1:
    # --- Shared criteria ---
    st.subheader("Search Criteria")

    col1, col2 = st.columns(2)
    with col1:
        title_keywords = st.text_input(
            "Title keywords (comma-separated)",
            value="backend, developer, engineer, software, python, golang, full stack",
            help="Job title must contain at least one of these",
        )
        required_skills = st.text_input(
            "Required skills (comma-separated, optional)",
            value="",
            placeholder="python, go, postgresql, django, fastapi",
            help="Job description must mention at least one. Leave empty to skip.",
        )
        exclude_keywords = st.text_input(
            "Exclude from title (comma-separated)",
            value="staff, principal, director, vp, head of, lead architect, manager",
            help="Skip jobs with these in the title",
        )
    with col2:
        remote_only = st.checkbox("Remote only", value=True)
        global_remote = st.checkbox("Global remote only (exclude US-only, India-based)", value=True)
        max_yoe = st.slider("Max years of experience", 0, 15, 5)

    criteria = {
        "title_keywords": [k.strip() for k in title_keywords.split(",") if k.strip()],
        "required_skills": [k.strip() for k in required_skills.split(",") if k.strip()],
        "exclude_keywords": [k.strip() for k in exclude_keywords.split(",") if k.strip()],
        "remote_only": remote_only,
        "global_remote_only": global_remote,
        "max_yoe": max_yoe,
    }

    st.divider()

    # --- Source selection ---
    st.subheader("Select Sources")
    source_col1, source_col2 = st.columns(2)

    with source_col1:
        st.write("**ATS Boards** (scrape company career pages)")
        ats_greenhouse = st.checkbox("Greenhouse (~80 companies)", value=True, key="ats_gh")
        ats_lever = st.checkbox("Lever (~15 companies)", value=True, key="ats_lv")
        ats_ashby = st.checkbox("Ashby (~60 companies)", value=True, key="ats_ash")
        max_slugs = st.slider("Max companies per ATS", 10, 200, 50)

    with source_col2:
        st.write("**Job Boards** (direct job listings)")

        st.caption("Defaults come from 🗂️ Board Manager. Override here for this run only.")

        # ── Popular / High Volume ──
        board_remoteok = st.checkbox("RemoteOK (~100 jobs)", value=_on("remoteok"), key="b_rok")
        board_remotive = st.checkbox("Remotive software-dev (~200 jobs)", value=_on("remotive"), key="b_rmt")
        board_remotive_devops = st.checkbox("Remotive DevOps category", value=_on("remotive_devops"), key="b_rmt_dv")
        board_remotive_data = st.checkbox("Remotive Data category", value=_on("remotive_data"), key="b_rmt_dt")
        board_wwr = st.checkbox("WeWorkRemotely backend (~100 jobs)", value=_on("weworkremotely"), key="b_wwr")
        board_wwr_devops = st.checkbox("WeWorkRemotely DevOps", value=_on("wwr_devops"), key="b_wwr_dv")
        board_wwr_frontend = st.checkbox("WeWorkRemotely Frontend", value=_on("wwr_frontend"), key="b_wwr_fe")
        board_hn = st.checkbox("HN Who's Hiring (~500 posts)", value=_on("hackernews"), key="b_hn")
        board_hn_jobs = st.checkbox("HN Job Stories (YC companies)", value=_on("hackernews_jobs"), key="b_hnj")
        board_himalayas = st.checkbox("Himalayas (~100 jobs)", value=_on("himalayas"), key="b_him")
        board_arbeitnow = st.checkbox("Arbeitnow (~100 jobs, EU+worldwide)", value=_on("arbeitnow"), key="b_arb")
        board_themuse = st.checkbox("The Muse (~100 jobs, startups)", value=_on("themuse"), key="b_muse")
        board_justjoin = st.checkbox("JustJoin.it (EU tech, many remote)", value=_on("justjoin"), key="b_jj")

        st.caption("── Low competition (fewer applicants = better odds) ──")
        board_jobicy = st.checkbox("Jobicy (~50 jobs, small board)", value=_on("jobicy"), key="b_jcy")
        board_jobicy_all = st.checkbox("Jobicy all engineering (no filter)", value=_on("jobicy_all"), key="b_jcy_all")
        board_workingnomads = st.checkbox("WorkingNomads dev (~100 jobs)", value=_on("workingnomads"), key="b_wn")
        board_workingnomads_devops = st.checkbox("WorkingNomads DevOps", value=_on("workingnomads_devops"), key="b_wn_dv")
        board_jobspresso = st.checkbox("Jobspresso (curated, ~50 jobs)", value=_on("jobspresso"), key="b_jsp")
        board_wfhio = st.checkbox("WFH.io (niche remote, ~60 jobs)", value=_on("wfhio"), key="b_wfh")
        board_remoteco = st.checkbox("Remote.co (curated remote)", value=_on("remoteco"), key="b_rco")
        board_authenticjobs = st.checkbox("Authentic Jobs (web/dev/design)", value=_on("authenticjobs"), key="b_auth")
        board_nodesk = st.checkbox("NodeDesk (very small, curated)", value=_on("nodesk"), key="b_ndk")
        board_4dayweek = st.checkbox("4DayWeek (ultra-niche, tiny pool)", value=_on("4dayweek"), key="b_4dw")
        board_dynamitejobs = st.checkbox("Dynamite Jobs (remote entrepreneurs)", value=_on("dynamitejobs"), key="b_dyn")
        board_freshremote = st.checkbox("Fresh Remote (aggregator)", value=_on("freshremote"), key="b_fr")
        board_remotefirstjobs = st.checkbox("Remote First Jobs (remote-only companies)", value=_on("remotefirstjobs"), key="b_rfj")
        board_devitjobs = st.checkbox("DevITjobs EU (EU developer jobs API)", value=_on("devitjobs"), key="b_dit")

        st.caption("── Tech-specific (niche = less competition) ──")
        board_djangojobs = st.checkbox("DjangoJobs (Python/Django only)", value=_on("djangojobs"), key="b_dj")
        board_larajobs = st.checkbox("LaraJobs (PHP/Laravel)", value=_on("larajobs"), key="b_lara")
        board_vuejobs = st.checkbox("VueJobs (Vue.js)", value=_on("vuejobs"), key="b_vue")
        board_golangjobs = st.checkbox("GolangJobs (Go)", value=_on("golangjobs"), key="b_go")
        board_smashingmag = st.checkbox("Smashing Magazine Jobs (frontend/dev)", value=_on("smashingmag"), key="b_smsh")

        st.caption("── Startup / Niche / Web3 ──")
        board_cryptojobslist = st.checkbox("CryptoJobsList (web3 startups, remote-first)", value=_on("cryptojobslist"), key="b_crypto")
        board_web3career = st.checkbox("Web3.career (blockchain startups)", value=_on("web3career"), key="b_w3c")
        board_climatebase = st.checkbox("ClimateBase (climate tech startups)", value=_on("climatebase"), key="b_clm")
        board_powertofly = st.checkbox("PowerToFly (inclusive remote hiring)", value=_on("powertofly"), key="b_ptf")

        st.caption("── Communities ──")
        board_reddit = st.checkbox("Reddit r/forhire", value=_on("reddit"), key="b_rdt")
        board_reddit_remotejs = st.checkbox("Reddit r/remotejs", value=_on("reddit_remotejs"), key="b_rjs")

    st.write("**Career Pages** (scrape company websites directly)")
    scrape_careers = st.checkbox("Scrape career pages of DB companies (custom/unknown ATS)", value=False, key="cp_on")
    max_career_pages = 30
    if scrape_careers:
        max_career_pages = st.slider("Max career pages to scrape", 10, 100, 30, key="cp_max")

    # Build source lists
    ats_types = []
    if ats_greenhouse:
        ats_types.append("greenhouse")
    if ats_lever:
        ats_types.append("lever")
    if ats_ashby:
        ats_types.append("ashby")

    _board_map = [
        (board_remoteok, "remoteok"),
        (board_remotive, "remotive"),
        (board_remotive_devops, "remotive_devops"),
        (board_remotive_data, "remotive_data"),
        (board_wwr, "weworkremotely"),
        (board_wwr_devops, "wwr_devops"),
        (board_wwr_frontend, "wwr_frontend"),
        (board_hn, "hackernews"),
        (board_hn_jobs, "hackernews_jobs"),
        (board_reddit, "reddit"),
        (board_reddit_remotejs, "reddit_remotejs"),
        (board_himalayas, "himalayas"),
        (board_arbeitnow, "arbeitnow"),
        (board_jobicy, "jobicy"),
        (board_jobicy_all, "jobicy_all"),
        (board_themuse, "themuse"),
        (board_workingnomads, "workingnomads"),
        (board_workingnomads_devops, "workingnomads_devops"),
        (board_jobspresso, "jobspresso"),
        (board_wfhio, "wfhio"),
        (board_remoteco, "remoteco"),
        (board_authenticjobs, "authenticjobs"),
        (board_nodesk, "nodesk"),
        (board_4dayweek, "4dayweek"),
        (board_dynamitejobs, "dynamitejobs"),
        (board_freshremote, "freshremote"),
        (board_remotefirstjobs, "remotefirstjobs"),
        (board_devitjobs, "devitjobs"),
        (board_djangojobs, "djangojobs"),
        (board_larajobs, "larajobs"),
        (board_vuejobs, "vuejobs"),
        (board_golangjobs, "golangjobs"),
        (board_smashingmag, "smashingmag"),
        (board_cryptojobslist, "cryptojobslist"),
        (board_web3career, "web3career"),
        (board_climatebase, "climatebase"),
        (board_powertofly, "powertofly"),
        (board_justjoin, "justjoin"),
    ]
    boards = [key for flag, key in _board_map if flag]

    total_sources = len(ats_types) + len(boards) + (1 if scrape_careers else 0)
    phases = sum([bool(ats_types), bool(boards), scrape_careers])

    st.divider()
    st.write(f"**{total_sources} sources selected** ({len(ats_types)} ATS + {len(boards)} boards{' + career pages' if scrape_careers else ''})")

    if st.button("🚀 Start Scraping All Sources", use_container_width=True, type="primary", disabled=total_sources == 0):
        progress_bar = st.progress(0)
        status_text = st.empty()
        results_container = st.container()

        grand_stats = {"total_scraped": 0, "matched": 0, "saved": 0, "errors": 0, "details": {}}
        phase_idx = 0

        # Phase 1: ATS Boards
        if ats_types:
            status_text.write(f"**Phase {phase_idx+1}/{phases}: Scraping ATS boards...**")
            for i, ats in enumerate(ats_types):
                def ats_progress(msg, prog, _i=i):
                    overall = (phase_idx + (_i + prog) / len(ats_types)) / phases
                    progress_bar.progress(min(overall, 0.99))
                    status_text.write(f"ATS: {msg}")

                stats = scrape_ats_jobs(
                    db=db,
                    ats_types=[ats],
                    criteria=criteria,
                    max_slugs_per_ats=max_slugs,
                    progress_callback=ats_progress,
                )
                grand_stats["total_scraped"] += stats["total_scraped"]
                grand_stats["matched"] += stats["matched"]
                grand_stats["saved"] += stats["saved"]
                grand_stats["errors"] += stats["errors"]
                for k, v in stats.get("by_ats", {}).items():
                    grand_stats["details"][k] = v
            phase_idx += 1

        # Phase 2: Job Boards
        if boards:
            status_text.write(f"**Phase {phase_idx+1}/{phases}: Scraping job boards...**")

            def board_progress(msg, prog):
                overall = (phase_idx + prog) / phases
                progress_bar.progress(min(overall, 0.99))
                status_text.write(f"Boards: {msg}")

            stats = scrape_board_jobs(
                db=db,
                boards=boards,
                criteria=criteria,
                progress_callback=board_progress,
            )
            grand_stats["total_scraped"] += stats["total_scraped"]
            grand_stats["matched"] += stats["matched"]
            grand_stats["saved"] += stats["saved"]
            grand_stats["errors"] += stats["errors"]
            for k, v in stats.get("by_board", {}).items():
                grand_stats["details"][k] = v
            phase_idx += 1

        # Phase 3: Career Pages
        if scrape_careers:
            status_text.write(f"**Phase {phase_idx+1}/{phases}: Scraping career pages...**")

            def career_progress(msg, prog):
                overall = (phase_idx + prog) / phases
                progress_bar.progress(min(overall, 0.99))
                status_text.write(f"Career pages: {msg}")

            stats = scrape_career_pages(
                db=db,
                criteria=criteria,
                max_companies=max_career_pages,
                progress_callback=career_progress,
            )
            grand_stats["total_scraped"] += stats["total_scraped"]
            grand_stats["matched"] += stats["matched"]
            grand_stats["saved"] += stats["saved"]
            grand_stats["errors"] += stats["errors"]
            grand_stats["details"]["career_pages"] = {
                "scraped": stats["total_scraped"],
                "matched": stats["matched"],
                "saved": stats["saved"],
            }

        progress_bar.progress(1.0)
        status_text.write("**Done!**")

        with results_container:
            st.divider()
            st.subheader("Results")

            mcols = st.columns(4)
            with mcols[0]:
                st.metric("Total Jobs Found", grand_stats["total_scraped"])
            with mcols[1]:
                st.metric("Matched Criteria", grand_stats["matched"])
            with mcols[2]:
                st.metric("Saved to DB", grand_stats["saved"])
            with mcols[3]:
                st.metric("Errors", grand_stats["errors"])

            # Per-source breakdown
            st.write("**Breakdown by source:**")
            for src, src_stats in grand_stats["details"].items():
                scraped = src_stats.get("scraped", 0)
                matched = src_stats.get("matched", 0)
                saved = src_stats.get("saved", 0)
                st.write(f"- **{src}**: {scraped} found → {matched} matched → {saved} saved")

            if grand_stats["saved"] > 0:
                st.success(f"Found {grand_stats['saved']} new jobs! Switch to Browse Jobs tab.")
                st.balloons()
            elif grand_stats["matched"] > 0:
                st.info(f"{grand_stats['matched']} matching jobs found, but all already in DB.")
            else:
                st.warning("No matching jobs. Try broadening criteria or adding more sources.")


# ========== TAB 2: BROWSE JOBS ==========
with tab2:
    st.subheader("Jobs in Database")

    fcol1, fcol2, fcol3, fcol4, fcol5 = st.columns(5)
    with fcol1:
        filter_new = st.selectbox("Status", ["All", "New Only", "Saved", "Applied", "Rejected"])
    with fcol2:
        all_sources = [
            "All",
            # ATS
            "greenhouse", "lever", "ashby",
            # Large boards
            "remoteok", "remotive", "weworkremotely", "hackernews", "hackernews_jobs",
            "himalayas", "arbeitnow", "themuse", "justjoin",
            # Low-competition
            "jobicy", "workingnomads", "jobspresso", "wfhio", "remoteco",
            "authenticjobs", "nodesk", "4dayweek", "dynamitejobs", "freshremote",
            "remotefirstjobs", "devitjobs",
            # Tech-specific
            "djangojobs", "larajobs", "vuejobs", "golangjobs", "smashingmag",
            # Startup/niche
            "cryptojobslist", "web3career", "climatebase", "powertofly",
            # Communities
            "reddit_forhire", "reddit_remotejs",
            # Career pages
            "career_page",
        ]
        filter_source = st.selectbox("Source", all_sources)
    with fcol3:
        filter_remote = st.selectbox("Location", ["All", "Remote Only"])
    with fcol4:
        search_text = st.text_input("Search title", "")
    with fcol5:
        sort_by = st.selectbox("Sort by", ["Score (high first)", "Score (low first)", "Newest", "Recommended", "Desperation (high first)"])

    job_filters = {"limit": 500}
    if filter_new == "New Only":
        job_filters["is_new"] = True

    try:
        jobs = db.get_jobs(**job_filters)
    except Exception as e:
        st.error(f"Error loading jobs: {e}")
        jobs = []

    # Client-side filters
    if filter_source != "All":
        jobs = [j for j in jobs if j.get("source_board") == filter_source]
    if filter_remote == "Remote Only":
        jobs = [j for j in jobs if j.get("is_remote")]
    if filter_new == "Saved":
        jobs = [j for j in jobs if j.get("user_action") == "saved"]
    elif filter_new == "Applied":
        jobs = [j for j in jobs if j.get("user_action") == "applied"]
    elif filter_new == "Rejected":
        jobs = [j for j in jobs if j.get("user_action") == "rejected"]
    if search_text:
        jobs = [j for j in jobs if search_text.lower() in (j.get("title") or "").lower()]

    # Sorting
    if sort_by == "Score (high first)":
        jobs.sort(key=lambda j: j.get("match_score", 0), reverse=True)
    elif sort_by == "Score (low first)":
        jobs.sort(key=lambda j: j.get("match_score", 0))
    elif sort_by == "Recommended":
        jobs.sort(key=lambda j: (j.get("is_recommended", False), j.get("match_score", 0)), reverse=True)
    elif sort_by == "Desperation (high first)":
        jobs.sort(key=lambda j: (j.get("desperation_score", 0) or 0), reverse=True)
    # Newest = default DB order

    st.write(f"Showing **{len(jobs)}** jobs")

    if jobs:
        for job in jobs:
            company_info = job.get("companies", {}) or {}
            company_name = company_info.get("name", "Unknown Company")
            remote_badge = " 🌍" if job.get("is_remote") else ""
            action = job.get("user_action", "")
            action_badge = f" [{action}]" if action else ""

            # Score badge
            score = job.get("match_score", 0)
            if score >= 80:
                score_badge = f" 🟢 {score}"
            elif score >= 60:
                score_badge = f" 🟡 {score}"
            elif score >= 40:
                score_badge = f" 🟠 {score}"
            elif score > 0:
                score_badge = f" 🔴 {score}"
            else:
                score_badge = ""

            recommended = " ⭐" if job.get("is_recommended") else ""

            with st.expander(
                f"**{job.get('title', 'Untitled')}** — {company_name}{remote_badge}{score_badge}{recommended}{action_badge} | {job.get('source_board', '')}"
            ):
                jcol1, jcol2 = st.columns([3, 1])

                with jcol1:
                    st.write(f"**Company:** {company_name}")
                    st.write(f"**Location:** {job.get('location', 'N/A')}")
                    st.write(f"**Remote:** {'Yes' if job.get('is_remote') else 'No'}")
                    # Show all sources this job was found on
                    source_boards = job.get("source_boards", "") or ""
                    if "," in source_boards:
                        st.write(f"**Found on:** {source_boards}")
                    else:
                        st.write(f"**Source:** {job.get('source_board', 'unknown')}")
                    st.write(f"**Found:** {str(job.get('discovered_at', ''))[:10]}")

                    # Desperation signal
                    desp_score = job.get("desperation_score", 0) or 0
                    if desp_score >= 60:
                        st.warning(f"Desperation: **{desp_score}/100** — Likely eager to hire!")
                    elif desp_score >= 30:
                        st.info(f"Desperation: **{desp_score}/100**")

                    # Show score and match reason
                    if score > 0:
                        st.divider()
                        if score >= 80:
                            st.success(f"Match Score: **{score}/100** — Strong match!")
                        elif score >= 60:
                            st.info(f"Match Score: **{score}/100** — Decent match")
                        elif score >= 40:
                            st.warning(f"Match Score: **{score}/100** — Partial match")
                        else:
                            st.error(f"Match Score: **{score}/100** — Weak match")

                        match_reason = job.get("match_reason", "")
                        if match_reason:
                            st.write(f"**Why this fits:** {match_reason}")

                    if job.get("apply_url"):
                        st.markdown(f"[Apply Here]({job['apply_url']})")

                with jcol2:
                    job_id = job.get("id")
                    if job_id:
                        if st.button("💾 Save", key=f"save_{job_id}", use_container_width=True):
                            db.mark_job_action(job_id, "saved")
                            st.rerun()
                        if st.button("✅ Applied", key=f"apply_{job_id}", use_container_width=True):
                            db.mark_job_action(job_id, "applied")
                            st.rerun()
                        if st.button("❌ Skip", key=f"skip_{job_id}", use_container_width=True):
                            db.mark_job_action(job_id, "rejected")
                            st.rerun()
                        if action:
                            st.write(f"Status: **{action}**")
    else:
        st.info("No jobs yet. Go to 'Scrape Jobs' tab to find some!")


# ========== TAB 3: SCORE JOBS ==========
with tab3:
    st.subheader("AI Job Scoring")
    st.markdown("Score all jobs against your criteria using **Gemini 2.0 Flash** (free tier) or rule-based fallback.")

    st.write("**Scoring Criteria**")
    scol1, scol2 = st.columns(2)
    with scol1:
        score_title_kw = st.text_input(
            "Title keywords",
            value="backend, developer, engineer, software, python, golang, full stack",
            key="score_title",
            help="Job title should contain at least one of these",
        )
        score_skills = st.text_input(
            "Required skills",
            value="python, go, postgresql, django, fastapi, docker, kubernetes",
            key="score_skills",
            help="Skills you're looking for",
        )
    with scol2:
        score_remote = st.checkbox("Remote preferred", value=True, key="score_remote")
        score_max_yoe = st.slider("Max years of experience", 0, 15, 5, key="score_yoe")
        score_extra = st.text_input(
            "Extra conditions (optional)",
            value="",
            key="score_extra",
            placeholder="e.g., startup, small team, no enterprise",
        )

    score_criteria = {
        "title_keywords": [k.strip() for k in score_title_kw.split(",") if k.strip()],
        "required_skills": [k.strip() for k in score_skills.split(",") if k.strip()],
        "remote_only": score_remote,
        "max_yoe": score_max_yoe,
        "extra_conditions": score_extra or "none",
    }

    # Check for Gemini API key
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    try:
        gemini_key = gemini_key or st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        pass
    has_gemini = gemini_key and gemini_key != "your_gemini_api_key_here"

    # Show Gemini usage
    if has_gemini:
        try:
            from gemini_client import get_gemini_usage_today
            g_usage = get_gemini_usage_today()
            pct = g_usage["calls"] / g_usage["limit"]
            if pct >= 0.9:
                st.error(f"Gemini quota: {g_usage['calls']}/{g_usage['limit']} today — almost full! Rule-based scoring will be used.")
            elif pct >= 0.7:
                st.warning(f"Gemini quota: {g_usage['calls']}/{g_usage['limit']} today ({g_usage['remaining']} left)")
            else:
                st.caption(f"Gemini quota today: {g_usage['calls']}/{g_usage['limit']} used — {g_usage['remaining']} remaining")
        except Exception:
            pass

    scol_a, scol_b = st.columns(2)
    with scol_a:
        use_ai = st.checkbox(
            "Use Gemini AI scoring (recommended)",
            value=has_gemini,
            disabled=not has_gemini,
            key="use_ai",
            help="Requires GEMINI_API_KEY. Falls back to rule-based scoring if unavailable.",
        )
        if not has_gemini:
            st.caption("Set GEMINI_API_KEY in .env to enable AI scoring. Using rule-based scoring.")

    with scol_b:
        max_to_score = st.slider("Max jobs to score", 50, 1000, 200, key="max_score")

    st.divider()

    if st.button("🤖 Score All Unscored Jobs", use_container_width=True, type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()

        # Set env var from secrets if needed
        if has_gemini and use_ai:
            os.environ["GEMINI_API_KEY"] = gemini_key

        def score_progress(msg, prog):
            progress_bar.progress(min(prog, 0.99))
            status_text.write(f"**{msg}**")

        result = score_all_jobs(
            db=db,
            criteria=score_criteria,
            use_ai=use_ai,
            max_jobs=max_to_score,
            progress_callback=score_progress,
        )

        progress_bar.progress(1.0)
        status_text.write("**Scoring complete!**")

        rcols = st.columns(3)
        with rcols[0]:
            st.metric("Jobs Scored", result["scored"])
        with rcols[1]:
            st.metric("AI Used", "Yes" if result["ai_used"] else "No (rules)")
        with rcols[2]:
            st.metric("Avg Score", result["avg_score"])

        if result["scored"] > 0:
            st.success(f"Scored {result['scored']} jobs! Go to **Browse Jobs** tab to see results sorted by score.")
        else:
            st.info("All jobs already scored. No new jobs to score.")

    # Quick stats on scored vs unscored
    st.divider()
    st.write("**Scoring Status**")
    try:
        all_for_stats = db.get_jobs(limit=5000)
        scored_jobs = [j for j in all_for_stats if j.get("match_score", 0) > 0]
        unscored_jobs = [j for j in all_for_stats if j.get("match_score", 0) == 0]
        recommended_jobs = [j for j in all_for_stats if j.get("is_recommended")]

        stat_cols = st.columns(4)
        with stat_cols[0]:
            st.metric("Total Jobs", len(all_for_stats))
        with stat_cols[1]:
            st.metric("Scored", len(scored_jobs))
        with stat_cols[2]:
            st.metric("Unscored", len(unscored_jobs))
        with stat_cols[3]:
            st.metric("Recommended (70+)", len(recommended_jobs))

        if scored_jobs:
            scores = [j.get("match_score", 0) for j in scored_jobs]
            avg = sum(scores) / len(scores)
            st.write(f"**Average score:** {avg:.1f} | **Highest:** {max(scores)} | **Lowest:** {min(scores)}")

            # Score distribution
            st.write("**Score distribution:**")
            buckets = {"80-100 (Strong)": 0, "60-79 (Decent)": 0, "40-59 (Partial)": 0, "20-39 (Weak)": 0, "0-19 (Poor)": 0}
            for s in scores:
                if s >= 80:
                    buckets["80-100 (Strong)"] += 1
                elif s >= 60:
                    buckets["60-79 (Decent)"] += 1
                elif s >= 40:
                    buckets["40-59 (Partial)"] += 1
                elif s >= 20:
                    buckets["20-39 (Weak)"] += 1
                else:
                    buckets["0-19 (Poor)"] += 1
            for bucket, count in buckets.items():
                if count > 0:
                    st.write(f"- **{bucket}**: {count} jobs")
    except Exception:
        st.info("No jobs in database yet.")


# ========== TAB 4: STATS ==========
with tab4:
    st.subheader("Scraping Statistics")

    try:
        all_jobs = db.get_jobs(limit=5000)
    except Exception:
        all_jobs = []

    if all_jobs:
        mcols = st.columns(5)
        new_jobs = [j for j in all_jobs if j.get("is_new")]
        saved = [j for j in all_jobs if j.get("user_action") == "saved"]
        applied = [j for j in all_jobs if j.get("user_action") == "applied"]
        remote_jobs = [j for j in all_jobs if j.get("is_remote")]

        with mcols[0]:
            st.metric("Total Jobs", len(all_jobs))
        with mcols[1]:
            st.metric("New", len(new_jobs))
        with mcols[2]:
            st.metric("Saved", len(saved))
        with mcols[3]:
            st.metric("Applied", len(applied))
        with mcols[4]:
            st.metric("Remote", len(remote_jobs))

        # Source breakdown
        st.divider()
        st.write("**Jobs by Source:**")
        sources = {}
        for j in all_jobs:
            src = j.get("source_board", "unknown")
            sources[src] = sources.get(src, 0) + 1

        for src, count in sorted(sources.items(), key=lambda x: -x[1]):
            pct = count / len(all_jobs) * 100
            st.write(f"- **{src}**: {count} jobs ({pct:.0f}%)")
    else:
        st.info("No jobs in database yet. Run a scrape first!")


# ========== SIDEBAR ==========
try:
    sidebar_jobs = db.get_jobs(limit=5000)
    new_count = len([j for j in sidebar_jobs if j.get("is_new")])
    saved_count = len([j for j in sidebar_jobs if j.get("user_action") == "saved"])

    st.sidebar.divider()
    st.sidebar.subheader("Job Stats")
    st.sidebar.metric("Total Jobs", len(sidebar_jobs))
    st.sidebar.metric("New", new_count)
    st.sidebar.metric("Saved", saved_count)
except Exception:
    pass
