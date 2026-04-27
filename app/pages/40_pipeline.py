import streamlit as st
from datetime import datetime

st.set_page_config(page_title="Auto-Pilot — Job Scout", page_icon="🤖", layout="wide")

try:
    from db import get_db
    db = get_db()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()


@st.cache_data(ttl=30, show_spinner=False)
def load_runs(limit: int = 30):
    try:
        return db._request("GET", "pipeline_runs", params={
            "order": "started_at.desc", "limit": limit,
        }) or []
    except Exception:
        return []


@st.cache_data(ttl=60, show_spinner=False)
def load_rules():
    try:
        return db._request("GET", "auto_apply_rules", params={
            "order": "priority.desc", "limit": 100,
        }) or []
    except Exception:
        return []


st.title("🤖 Auto-Pilot")
st.caption("Configure and monitor the automated daily pipeline.")

tab_run, tab_rules, tab_history = st.tabs(["▶ Run Now", "📋 Auto-Apply Rules", "📜 History"])


# ── Tab: Run Now ──────────────────────────────────────────────────────────────
with tab_run:
    st.subheader("Manual Pipeline Run")
    st.markdown("""
The full pipeline:
1. **Discover** — YC + alternative sources
2. **Scrape** — all enabled ATS + boards
3. **Enrich** — remote filter + desperation scoring
4. **Score** — rule-based pre-filter → Gemini AI
5. **Digest** — summary of what was found
    """)

    c1, c2 = st.columns(2)
    with c1:
        run_discover = st.checkbox("Stage 1: Discovery (YC, alternatives)", value=True)
        run_scrape = st.checkbox("Stage 2: Scrape jobs (ATS + boards)", value=True)
        run_score = st.checkbox("Stage 4: Score new jobs", value=True)
    with c2:
        max_scrape = st.slider("Max companies per ATS scraper", 20, 200, 50)
        use_ai = st.checkbox("Use Gemini AI for scoring (uses quota)", value=True)

    st.info("⚙️ Auto-apply (Stage 6) is coming in a later V2 phase. For now, use Jobs → Apply Queue.")

    if st.button("▶ Run Pipeline Now", type="primary", use_container_width=True):
        from job_scout.db.repositories.pipeline_runs import create_run, complete_run, add_stage_result

        run = create_run(triggered_by="manual")
        run_id = run["id"] if run else None

        progress = st.progress(0)
        status_el = st.empty()
        all_stats = {}

        try:
            # Stage 1: Discover
            if run_discover:
                status_el.write("**Stage 1: Discovery...**")
                progress.progress(0.1)
                from job_scout.discovery.yc import fetch_yc_companies
                from job_scout.discovery.alternative import fetch_alternative_sources
                existing = {c["name"].lower() for c in db.get_companies(active_only=False, limit=10000)}
                new_cos = []
                try:
                    yc = fetch_yc_companies(batch="W24", limit=100)
                    new_cos += [c for c in yc if (c.get("name") or "").lower() not in existing]
                except Exception:
                    pass
                try:
                    alt = fetch_alternative_sources()
                    new_cos += [c for c in alt if (c.get("name") or "").lower() not in existing]
                except Exception:
                    pass
                inserted = db.add_companies_bulk(new_cos) if new_cos else 0
                all_stats["discover"] = {"new_companies": inserted}
                if run_id:
                    add_stage_result(run_id, "discover", "success", {"new_companies": inserted})

            # Stage 2: Scrape
            if run_scrape:
                status_el.write("**Stage 2: Scraping jobs...**")
                progress.progress(0.3)
                from job_scout.scraping.ats import scrape_ats_jobs
                from job_scout.scraping.boards import scrape_board_jobs

                prefs = {}
                try:
                    r = db._request("GET", "user_profile", params={"limit": 1})
                    prefs = (r[0].get("preferences") or {}) if r else {}
                except Exception:
                    pass
                criteria = {
                    "title_keywords": prefs.get("title_keywords", ["backend", "developer", "engineer", "python", "golang"]),
                    "required_skills": prefs.get("skills", []),
                    "exclude_keywords": prefs.get("exclude_keywords", ["staff", "principal", "director", "vp"]),
                    "remote_only": prefs.get("remote_only", True),
                    "global_remote_only": prefs.get("global_remote", True),
                    "max_yoe": prefs.get("max_yoe", 5),
                }

                ats_stats = scrape_ats_jobs(db=db, criteria=criteria, max_slugs_per_ats=max_scrape)
                board_stats = scrape_board_jobs(db=db, criteria=criteria)
                all_stats["scrape"] = {
                    "ats_saved": ats_stats.get("saved", 0),
                    "boards_saved": board_stats.get("saved", 0),
                    "total_new": ats_stats.get("saved", 0) + board_stats.get("saved", 0),
                }
                if run_id:
                    add_stage_result(run_id, "scrape", "success", all_stats["scrape"])

            # Stage 4: Score
            if run_score:
                status_el.write("**Stage 4: Scoring jobs...**")
                progress.progress(0.7)
                import os
                from job_scout.ai.gemini import score_all_jobs
                gemini_key = os.getenv("GEMINI_API_KEY", "")
                try:
                    gemini_key = gemini_key or st.secrets.get("GEMINI_API_KEY", "")
                except Exception:
                    pass
                if gemini_key and use_ai:
                    os.environ["GEMINI_API_KEY"] = gemini_key
                prefs2 = prefs if run_scrape else {}
                score_crit = {
                    "title_keywords": prefs2.get("title_keywords", ["backend", "developer", "engineer"]),
                    "required_skills": prefs2.get("skills", []),
                    "remote_only": prefs2.get("remote_only", True),
                    "max_yoe": prefs2.get("max_yoe", 5),
                }
                score_result = score_all_jobs(db=db, criteria=score_crit, use_ai=bool(gemini_key and use_ai), max_jobs=500)
                all_stats["score"] = score_result
                if run_id:
                    add_stage_result(run_id, "score", "success", score_result)

            progress.progress(1.0)
            status_el.write("**Pipeline complete!**")

            if run_id:
                total_new = all_stats.get("scrape", {}).get("total_new", 0)
                scored = all_stats.get("score", {}).get("scored", 0)
                complete_run(run_id, status="success", stats=all_stats)

            # Show summary
            st.success("Pipeline finished!")
            for stage, stats in all_stats.items():
                st.write(f"**{stage.capitalize()}:** {stats}")

        except Exception as e:
            status_el.write(f"**Error:** {e}")
            if run_id:
                from job_scout.db.repositories.pipeline_runs import complete_run
                complete_run(run_id, status="failed", error_log=str(e))
            st.error(f"Pipeline error: {e}")
            import traceback; st.code(traceback.format_exc())

        st.cache_data.clear()


# ── Tab: Auto-Apply Rules ─────────────────────────────────────────────────────
with tab_rules:
    st.subheader("Auto-Apply Rules")
    st.caption("Define conditions under which jobs are automatically applied to. (Auto-apply execution is Phase 6 of V2.)")

    rules = load_rules()
    if rules:
        for rule in rules:
            icon = "✅" if rule.get("is_active") else "⏸️"
            with st.expander(f"{icon} **{rule.get('name', 'Unnamed rule')}** (priority {rule.get('priority', 0)})"):
                st.json({"conditions": rule.get("conditions"), "action": rule.get("action")})
    else:
        st.info("No rules yet. Add one below.")

    st.divider()
    with st.expander("➕ Add New Rule"):
        with st.form("add_rule"):
            rule_name = st.text_input("Rule name", placeholder="High-confidence remote backend")
            priority = st.number_input("Priority", value=0, step=1)
            min_score = st.slider("Min match score", 0, 100, 80)
            ats_filter = st.multiselect("ATS type", ["greenhouse", "lever", "ashby"], default=["greenhouse", "lever"])
            is_active = st.checkbox("Active", value=True)
            if st.form_submit_button("Save Rule"):
                rule_data = {
                    "name": rule_name,
                    "is_active": is_active,
                    "priority": priority,
                    "conditions": {
                        "all_of": [
                            {"field": "match_score", "op": ">=", "value": min_score},
                            {"field": "is_remote_global", "op": "==", "value": True},
                            {"field": "ats_type", "op": "in", "value": ats_filter},
                        ]
                    },
                    "action": {"type": "auto_apply", "tier": 1, "use_tailored_resume": True},
                }
                try:
                    db._request("POST", "auto_apply_rules", json=rule_data)
                    st.success("Rule saved!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")


# ── Tab: History ──────────────────────────────────────────────────────────────
with tab_history:
    st.subheader("Pipeline Run History")
    runs = load_runs()
    if runs:
        for run in runs:
            status = run.get("status", "unknown")
            icon = {"success": "✅", "partial": "⚠️", "failed": "❌", "running": "🔄"}.get(status, "❓")
            started = str(run.get("started_at", ""))[:16]
            triggered = run.get("triggered_by", "manual")
            with st.expander(f"{icon} {started} ({triggered}) — {status}"):
                stats = run.get("stats") or {}
                if stats:
                    st.json(stats)
                if run.get("error_log"):
                    st.code(run["error_log"][:500])
    else:
        st.info("No pipeline runs yet. Click 'Run Now' to start the first one.")
