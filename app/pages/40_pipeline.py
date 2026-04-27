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

tab_schedule, tab_run, tab_rules, tab_history = st.tabs(["🕐 Schedule", "▶ Run Now", "📋 Auto-Apply Rules", "📜 History"])


# ── Tab: Schedule ────────────────────────────────────────────────────────────
with tab_schedule:
    import json, os
    from pathlib import Path

    _CFG_FILE = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "data" / "schedule_config.json"

    def _load_cfg():
        try:
            with open(_CFG_FILE) as f:
                return json.load(f)
        except Exception:
            return {"enabled": True, "run_time": "07:00", "stages": list(range(1, 9)),
                    "digest_email": "", "daily_auto_apply_cap": 50}

    def _save_cfg(cfg):
        _CFG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CFG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)

    cfg = _load_cfg()

    st.subheader("Daily Pipeline Schedule")
    st.caption("Changes saved here are picked up by the scheduler on its next tick (≤30 seconds).")

    # Status card
    from datetime import datetime, timedelta
    runs = load_runs(5)
    last_run = runs[0] if runs else None

    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        status_label = "✅ Enabled" if cfg.get("enabled") else "⏸️ Paused"
        st.metric("Scheduler", status_label)
    with sc2:
        st.metric("Daily run time", cfg.get("run_time", "07:00"))
    with sc3:
        if last_run:
            started = str(last_run.get("started_at", ""))[:16]
            st.metric("Last run", started)
        else:
            st.metric("Last run", "Never")

    # Next run time
    run_time = cfg.get("run_time", "07:00")
    try:
        h, m = [int(x) for x in run_time.split(":")]
        now = datetime.now()
        candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        delta = candidate - now
        hours_away = int(delta.total_seconds() // 3600)
        mins_away  = int((delta.total_seconds() % 3600) // 60)
        st.info(f"⏰ Next scheduled run: **{candidate.strftime('%Y-%m-%d %H:%M')}** (in {hours_away}h {mins_away}m)")
    except Exception:
        pass

    st.divider()

    # Config form
    with st.form("schedule_form"):
        c1, c2 = st.columns(2)
        with c1:
            new_enabled = st.checkbox("Scheduler enabled", value=cfg.get("enabled", True))
            new_time = st.text_input("Run time (HH:MM local)", value=cfg.get("run_time", "07:00"),
                                      help="24-hour format. Matches the time zone of the machine running the scheduler.")
            new_email = st.text_input("Digest email recipient",
                                       value=cfg.get("digest_email", "") or os.getenv("DIGEST_EMAIL", ""),
                                       placeholder="you@gmail.com")
        with c2:
            new_cap = st.slider("Max auto-apply per day", 0, 50, cfg.get("daily_auto_apply_cap", 50))
            all_stages = {
                1: "Discover companies",
                2: "Scrape jobs",
                3: "Enrich (desperation)",
                4: "Classify",
                5: "Score",
                6: "Auto-apply",
                7: "Follow-ups",
                8: "Email digest",
            }
            enabled_stages = cfg.get("stages", list(range(1, 9)))
            selected = st.multiselect(
                "Stages to run",
                options=list(all_stages.keys()),
                default=enabled_stages,
                format_func=lambda n: f"Stage {n}: {all_stages[n]}",
            )

        if st.form_submit_button("💾 Save Schedule", type="primary", use_container_width=True):
            # Validate time format
            try:
                h2, m2 = [int(x) for x in new_time.split(":")]
                assert 0 <= h2 <= 23 and 0 <= m2 <= 59
            except Exception:
                st.error("Invalid time format — use HH:MM (e.g. 07:00)")
                st.stop()

            new_cfg = {
                "enabled": new_enabled,
                "run_time": new_time,
                "stages": sorted(selected),
                "digest_email": new_email,
                "daily_auto_apply_cap": new_cap,
                "headless": True,
                "max_slugs_per_ats": 100,
            }
            _save_cfg(new_cfg)
            st.success("Schedule saved! The scheduler will pick this up within 30 seconds.")
            st.rerun()

    st.divider()
    st.write("**How to start the scheduler:**")
    st.code("""# Option A — Docker Compose (recommended)
docker compose up pipeline -d

# Option B — direct Python (for local dev / VPS cron)
python -m job_scout.pipeline.scheduler

# Option C — one-shot via cron (add to crontab -e)
0 7 * * * /path/to/job_scout/scripts/run_pipeline.sh >> ~/job_scout.log 2>&1
""", language="bash")


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
