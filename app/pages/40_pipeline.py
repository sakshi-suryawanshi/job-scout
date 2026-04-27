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
The full 8-stage pipeline:
1. **Discover** — YC + remoteintech + Serper dorking
2. **Scrape** — all enabled ATS + boards
3. **Enrich** — desperation scoring
4. **Classify** — multi-label job categories
5. **Score** — rule-based pre-filter → Gemini AI
6. **Auto-Apply** — evaluate rules, tag queued jobs (Playwright apply in Step 6)
7. **Follow-Ups** — find overdue applications
8. **Digest** — compose + email daily summary
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
        import os

        # Inject API keys from secrets
        for k in ("GEMINI_API_KEY", "SERPER_API_KEY"):
            try:
                val = st.secrets.get(k)
                if val:
                    os.environ[k] = val
            except Exception:
                pass

        from job_scout.pipeline.daily_run import run_pipeline, build_config

        cfg = build_config()
        cfg["max_slugs_per_ats"] = max_scrape
        cfg["use_ai"] = use_ai

        selected_stages = []
        if run_discover: selected_stages.extend([1])
        if run_scrape:   selected_stages.extend([2, 3, 4])
        if run_score:    selected_stages.append(5)
        selected_stages.extend([6, 7, 8])

        progress_bar = st.progress(0)
        status_el = st.empty()

        status_el.write("**Running pipeline...**")
        try:
            run_stats = run_pipeline(
                db=db,
                stages=selected_stages,
                config=cfg,
                triggered_by="manual",
            )
            progress_bar.progress(1.0)
            status_el.write("**Pipeline complete!**")
            st.success(f"Done! Status: {run_stats.get('_status', 'unknown')}")
            for stage, stats in run_stats.items():
                if not stage.startswith("_"):
                    st.write(f"**{stage}:** {stats}")
        except Exception as e:
            status_el.write(f"**Error:** {e}")
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
