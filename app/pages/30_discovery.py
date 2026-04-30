import streamlit as st
import os
import sys

st.set_page_config(page_title="Discovery — Job Scout", page_icon="🔍", layout="wide")

try:
    from db import get_db
    db = get_db()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# Load API keys from Streamlit secrets if available
for key in ("SERPER_API_KEY", "GEMINI_API_KEY"):
    try:
        val = st.secrets.get(key)
        if val:
            os.environ[key] = val
    except Exception:
        pass

_serper_available = bool(os.getenv("SERPER_API_KEY"))
_gemini_key = os.getenv("GEMINI_API_KEY", "")

st.title("🔍 Discovery")
st.caption("Find new jobs and companies from all sources in one place.")

tab_scrape, tab_daily, tab_dorking, tab_hunt, tab_signals = st.tabs([
    "🚀 Scrape Jobs", "⚡ Daily (LinkedIn/Indeed)", "🕵️ Serper Dorking", "🏭 Career Hunt", "📡 Signals"
])


# ── Shared criteria loader ────────────────────────────────────────────────────
def _load_prefs():
    """Load preferences from disk (primary) or DB (fallback)."""
    import json as _json
    from pathlib import Path as _Path

    # Primary: disk
    _pref_file = _Path(__file__).parent.parent.parent / "data" / "preferences.json"
    if _pref_file.exists():
        try:
            data = _json.loads(_pref_file.read_text())
            if isinstance(data, dict) and data:
                return data
        except Exception:
            pass

    # Fallback: DB (if preferences column exists)
    try:
        result = db._request("GET", "user_profile", params={"limit": 1})
        prefs = (result[0].get("preferences") or {}) if result else {}
        return prefs if isinstance(prefs, dict) else {}
    except Exception:
        return {}


def _save_prefs(criteria: dict) -> bool:
    """Persist criteria to data/preferences.json (disk) + user_profile DB if possible.
    Disk is the primary store — works without any DB schema changes.
    Returns True on success.
    """
    import json as _json
    from pathlib import Path as _Path

    prefs_update = {
        "title_keywords": criteria.get("title_keywords", []),
        "skills": criteria.get("required_skills", []),
        "exclude_keywords": criteria.get("exclude_keywords", []),
        "remote_only": criteria.get("remote_only", True),
        "global_remote": criteria.get("global_remote_only", True),
        "max_yoe": criteria.get("max_yoe", 5),
        "min_salary": criteria.get("min_salary"),
    }

    # Primary: save to disk (always works, no schema dependency)
    _pref_file = _Path(__file__).parent.parent.parent / "data" / "preferences.json"
    try:
        _pref_file.parent.mkdir(parents=True, exist_ok=True)
        _pref_file.write_text(_json.dumps(prefs_update, indent=2))
    except Exception as _e:
        print(f"_save_prefs disk: {_e}")
        return False

    # Secondary: also try DB (only works if preferences column exists)
    try:
        result = db._request("GET", "user_profile", params={"limit": 1})
        if result:
            db._request("PATCH", f"user_profile?id=eq.{result[0]['id']}",
                        json={"preferences": prefs_update})
    except Exception:
        pass   # DB save optional — disk is the source of truth

    return True

def _criteria_form(key_prefix: str):
    prefs = _load_prefs()
    c1, c2 = st.columns(2)
    with c1:
        title_kw = st.text_input(
            "Title keywords",
            value=", ".join(prefs.get("title_keywords", ["backend", "developer", "engineer", "software", "python", "golang"])),
            key=f"{key_prefix}_title",
        )
        skills = st.text_input(
            "Required skills (optional)",
            value=", ".join(prefs.get("skills", [])),
            key=f"{key_prefix}_skills",
        )
        exclude = st.text_input(
            "Exclude from title",
            value=", ".join(prefs.get("exclude_keywords", ["staff", "principal", "director", "vp", "head of"])),
            key=f"{key_prefix}_excl",
        )
    with c2:
        remote = st.checkbox("Remote only", value=prefs.get("remote_only", True), key=f"{key_prefix}_rem")
        global_rem = st.checkbox("Global remote (exclude US-only, India-based)", value=prefs.get("global_remote", True), key=f"{key_prefix}_grem")
        max_yoe = st.slider("Max YOE", 0, 15, prefs.get("max_yoe", 5), key=f"{key_prefix}_yoe")
        min_sal = st.number_input("Min salary (0 = any)", value=prefs.get("min_salary") or 0, step=5000, key=f"{key_prefix}_msal")

    return {
        "title_keywords": [k.strip() for k in title_kw.split(",") if k.strip()],
        "required_skills": [k.strip() for k in skills.split(",") if k.strip()],
        "exclude_keywords": [k.strip() for k in exclude.split(",") if k.strip()],
        "remote_only": remote,
        "global_remote_only": global_rem,
        "max_yoe": max_yoe,
        "min_salary": min_sal if min_sal > 0 else None,
    }


# ── Tab 1: Scrape Jobs ────────────────────────────────────────────────────────
with tab_scrape:
    st.subheader("Scrape ATS Boards + Job Boards")

    criteria = _criteria_form("scrape")

    # Explicit save button visible regardless of which action the user takes
    if st.button("💾 Save as default preferences", key="save_prefs_explicit"):
        if _save_prefs(criteria):
            st.success("Preferences saved — they'll pre-fill this form on next visit.")
        else:
            st.warning("Could not save preferences — check your DB connection.")

    st.divider()
    st.write("**Sources**")
    sc1, sc2 = st.columns(2)

    with sc1:
        st.caption("**ATS Boards**")
        ats_gh  = st.checkbox("Greenhouse (~80 cos)", value=True,  key="sc_ats_gh")
        ats_lv  = st.checkbox("Lever (~15 cos)",      value=True,  key="sc_ats_lv")
        ats_ash = st.checkbox("Ashby (~60 cos)",      value=True,  key="sc_ats_ash")
        ats_wb  = st.checkbox("Workable",             value=False, key="sc_ats_wb")
        ats_sr  = st.checkbox("SmartRecruiters",      value=False, key="sc_ats_sr")
        max_slugs = st.slider("Max companies per ATS", 10, 200, 50, key="sc_max_slugs")

    with sc2:
        st.caption("**Job Boards**")
        from job_scout.scraping.boards._orchestrator import _get_enabled_boards
        _ALL_KEYS = [
            "remoteok","remotive","remotive_devops","remotive_data","weworkremotely","wwr_devops",
            "wwr_frontend","himalayas","arbeitnow","themuse","justjoin","hackernews","hackernews_jobs",
            "reddit","reddit_remotejs","jobicy","jobicy_all","workingnomads","workingnomads_devops",
            "jobspresso","wfhio","remoteco","authenticjobs","nodesk","4dayweek","dynamitejobs",
            "freshremote","remotefirstjobs","devitjobs","djangojobs","larajobs","vuejobs","golangjobs",
            "smashingmag","cryptojobslist","web3career","climatebase","powertofly",
            "cord","wellfound","hired","talentio","pallet",
        ]
        _enabled = set(_get_enabled_boards(_ALL_KEYS))
        def _on(k): return k in _enabled

        board_checks = {}
        for key, label in [
            ("remoteok","RemoteOK"),("remotive","Remotive"),("weworkremotely","WeWorkRemotely"),
            ("himalayas","Himalayas"),("arbeitnow","Arbeitnow"),("justjoin","JustJoin.it"),
            ("hackernews","HN Who's Hiring"),("hackernews_jobs","HN Job Stories"),
            ("jobicy","Jobicy"),("jobicy_all","Jobicy all"),("workingnomads","WorkingNomads"),
            ("jobspresso","Jobspresso"),("wfhio","WFH.io"),("remoteco","Remote.co"),
            ("authenticjobs","Authentic Jobs"),("nodesk","NodeDesk"),("4dayweek","4DayWeek"),
            ("dynamitejobs","Dynamite Jobs"),("freshremote","Fresh Remote"),
            ("remotefirstjobs","Remote First Jobs"),("devitjobs","DevITjobs EU"),
            ("djangojobs","DjangoJobs"),("golangjobs","GolangJobs"),
            ("cord","Cord.co"),("wellfound","Wellfound"),("hired","Hired.com"),
            ("talentio","Talent.io"),("pallet","Pallet"),
            ("cryptojobslist","CryptoJobsList"),("climatebase","ClimateBase"),
        ]:
            board_checks[key] = st.checkbox(label, value=_on(key), key=f"b_{key}")

    career_pages = st.checkbox("Scrape career pages of DB companies (slow)", value=False)
    max_cp = st.slider("Max career pages", 10, 100, 30) if career_pages else 30

    ats_types = [a for a, c in [
        ("greenhouse", ats_gh), ("lever", ats_lv), ("ashby", ats_ash),
        ("workable", ats_wb), ("smartrecruiters", ats_sr),
    ] if c]
    boards = [k for k, v in board_checks.items() if v]
    total = len(ats_types) + len(boards) + (1 if career_pages else 0)

    st.write(f"**{total} sources selected**")

    if st.button("🚀 Start Scraping", use_container_width=True, type="primary", disabled=total == 0):
        _save_prefs(criteria)   # Auto-save; errors are non-fatal (just logged to stdout)
        from job_scout.scraping.ats import scrape_ats_jobs
        from job_scout.scraping.boards import scrape_board_jobs
        from job_scout.scraping.careers import scrape_career_pages

        progress = st.progress(0)
        status = st.empty()
        grand = {"total_scraped": 0, "matched": 0, "saved": 0, "errors": 0}
        phases = sum([bool(ats_types), bool(boards), career_pages])
        phase = 0

        if ats_types:
            status.write("**Scraping ATS boards...**")
            for i, ats in enumerate(ats_types):
                def _ap(msg, p, _i=i):
                    progress.progress(min((phase + (_i + p) / len(ats_types)) / phases, 0.99))
                    status.write(f"ATS: {msg}")
                stats = scrape_ats_jobs(db=db, ats_types=[ats], criteria=criteria, max_slugs_per_ats=max_slugs, progress_callback=_ap)
                for k, v in stats.items():
                    if k in grand:
                        grand[k] = grand[k] + (v if isinstance(v, int) else 0)
            phase += 1

        if boards:
            status.write("**Scraping job boards...**")
            def _bp(msg, p):
                progress.progress(min((phase + p) / phases, 0.99))
                status.write(f"Boards: {msg}")
            stats = scrape_board_jobs(db=db, boards=boards, criteria=criteria, progress_callback=_bp)
            for k, v in stats.items():
                if k in grand:
                    grand[k] = grand[k] + (v if isinstance(v, int) else 0)
            phase += 1

        if career_pages:
            status.write("**Scraping career pages...**")
            def _cp(msg, p):
                progress.progress(min((phase + p) / phases, 0.99))
                status.write(f"Career pages: {msg}")
            stats = scrape_career_pages(db=db, criteria=criteria, max_companies=max_cp, progress_callback=_cp)
            for k, v in stats.items():
                if k in grand:
                    grand[k] = grand[k] + (v if isinstance(v, int) else 0)

        progress.progress(1.0)
        status.write("**Done!**")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Found", grand["total_scraped"])
        m2.metric("Matched criteria", grand["matched"])
        m3.metric("Saved to DB", grand["saved"])
        m4.metric("Errors", grand["errors"])
        if grand["saved"] > 0:
            st.success(f"Added {grand['saved']} new jobs! Go to Jobs → Apply Queue.")
            st.balloons()

        # Score new jobs
        from job_scout.ai.gemini import score_all_jobs
        if _gemini_key and grand["saved"] > 0:
            with st.spinner("Scoring new jobs with AI..."):
                os.environ["GEMINI_API_KEY"] = _gemini_key
                score_result = score_all_jobs(db=db, criteria=criteria, use_ai=True, max_jobs=300)
            st.info(f"Scored {score_result['scored']} jobs (avg {score_result['avg_score']}).")


# ── Tab 2: Daily Discovery ────────────────────────────────────────────────────
with tab_daily:
    st.subheader("LinkedIn + Indeed Daily Discovery")
    st.caption("Pulls fresh job listings from LinkedIn and Indeed via Google dorking. ~20 Serper credits/run. 1-day cooldown.")

    if not _serper_available:
        st.warning("SERPER_API_KEY not set. Add it to your .env or Streamlit secrets.")
    else:
        try:
            from job_scout.discovery.serper_dorking import get_serper_usage, is_category_on_cooldown
            s = get_serper_usage()
            pct = s["calls_this_month"] / s["limit"]
            st.progress(min(pct, 1.0), text=f"Serper: {s['calls_this_month']}/{s['limit']} this month ({s['remaining']} left)")

            li_cd, li_days = is_category_on_cooldown("linkedin_daily")
            in_cd, in_days = is_category_on_cooldown("indeed_daily")
            cc1, cc2 = st.columns(2)
            with cc1:
                st.warning(f"LinkedIn: cooldown ({li_days}d ago)") if li_cd else st.success("LinkedIn: ready")
            with cc2:
                st.warning(f"Indeed: cooldown ({in_days}d ago)") if in_cd else st.success("Indeed: ready")
        except Exception:
            pass

        rc1, rc2, rc3 = st.columns(3)
        run_li = rc1.checkbox("LinkedIn daily", value=True, key="d_li")
        run_in = rc2.checkbox("Indeed daily", value=True, key="d_in")
        force_d = rc3.checkbox("Force re-run (ignore cooldown)", key="d_force")
        results_per_q = st.slider("Results per query", 5, 20, 10, key="d_rpq")
        cats = (["linkedin_daily"] if run_li else []) + (["indeed_daily"] if run_in else [])

        if st.button("⚡ Run Daily Discovery", type="primary", use_container_width=True, disabled=not cats):
            from job_scout.discovery.serper_dorking import SerperDorker, create_signal_from_result
            with st.spinner("Running…"):
                try:
                    dorker = SerperDorker()
                    total_companies, sig_count = 0, 0
                    for cat in cats:
                        companies_found = dorker.run_dork_category(cat, results_per_query=results_per_q, force=force_d)
                        db_companies = [dorker.to_db_format(c) for c in companies_found]
                        existing = {c["name"].lower() for c in db.get_companies(active_only=False, limit=10000)}
                        new_cos = [c for c in db_companies if (c.get("name") or "").lower() not in existing]
                        if new_cos:
                            total_companies += db.add_companies_bulk(new_cos)
                        # Auto-save signals from Daily Discovery (item 17)
                        for company in companies_found:
                            src_cat = company.get("source_category", "")
                            if src_cat in {"distress", "funding", "hidden", "regional"}:
                                try:
                                    sig = create_signal_from_result(company, src_cat)
                                    if db.add_signal(sig):
                                        sig_count += 1
                                except Exception:
                                    pass
                    msg = f"Added **{total_companies}** new companies from LinkedIn/Indeed"
                    if sig_count:
                        msg += f" + **{sig_count}** signals saved"
                    st.success(
                        msg + ". Job listings will be scraped in the next pipeline run "
                        "(or use the **Scrape Jobs** tab now)."
                    )
                except Exception as e:
                    st.error(f"Error: {e}")
                    import traceback; st.code(traceback.format_exc())


# ── Tab 3: Serper Dorking ─────────────────────────────────────────────────────
with tab_dorking:
    st.subheader("Serper.dev Google Dorking")
    st.caption("Discover hidden companies via targeted Google searches. 2,500 queries/month free.")

    if not _serper_available:
        st.warning("SERPER_API_KEY not set.")
    else:
        from job_scout.discovery.serper_dorking import DORK_QUERIES, get_serper_usage, is_category_on_cooldown
        s = get_serper_usage()
        st.progress(min(s["calls_this_month"] / s["limit"], 1.0),
                    text=f"Serper: {s['calls_this_month']}/{s['limit']} this month")

        st.divider()

        all_cats = list(DORK_QUERIES.keys())
        default_cats = ["distress_signals", "funding_signals", "hidden_gems", "yc_latest", "ats_hiring"]

        selected_cats = st.multiselect("Select dork categories", all_cats, default=default_cats)
        results_per = st.slider("Results per query", 5, 20, 10, key="dork_rpq")
        max_q = st.slider("Max queries per category", 1, 10, 3, key="dork_mq")
        force = st.checkbox("Force (ignore cooldowns)", key="dork_force")
        save_sigs = st.checkbox("Save distress/funding signals to DB", value=True, key="dork_sigs")

        est = len(selected_cats) * max_q
        st.caption(f"Estimated Serper credits: ~{est}")

        # Cooldown status
        if selected_cats:
            st.write("**Cooldown status:**")
            for cat in selected_cats:
                on_cd, days_ago = is_category_on_cooldown(cat)
                icon = "⏳" if on_cd else "✅"
                msg = f"on cooldown ({days_ago}d ago)" if on_cd else "ready"
                st.caption(f"{icon} **{cat}**: {msg}")

        if st.button("🔎 Run Dorking", type="primary", use_container_width=True, disabled=not selected_cats):
            from job_scout.discovery.serper_dorking import SerperDorker, create_signal_from_result
            progress = st.progress(0)
            status_txt = st.empty()
            try:
                dorker = SerperDorker()
                all_companies = []
                for i, cat in enumerate(selected_cats):
                    status_txt.write(f"Category: **{cat}** ({i+1}/{len(selected_cats)})")
                    progress.progress((i + 1) / len(selected_cats))
                    companies = dorker.run_dork_category(cat, max_queries=max_q, results_per_query=results_per, force=force)
                    all_companies.extend(companies)

                db_companies = [dorker.to_db_format(c) for c in all_companies]
                existing = {c["name"].lower() for c in db.get_companies(active_only=False, limit=10000)}
                new_cos = [c for c in db_companies if (c.get("name") or "").lower() not in existing and c.get("name")]

                inserted = db.add_companies_bulk(new_cos) if new_cos else 0

                if save_sigs:
                    signal_cats = {"distress", "funding", "hidden", "regional", "hackernews", "indiehackers"}
                    sig_count = 0
                    for company in all_companies:
                        cat_found = company.get("source_category", "")
                        if cat_found in signal_cats:
                            sig = create_signal_from_result(company, cat_found)
                            if db.add_signal(sig):
                                sig_count += 1

                progress.progress(1.0)
                status_txt.write("**Done!**")
                st.success(f"Found {len(all_companies)} results → {inserted} new companies added. {sig_count if save_sigs else 0} signals saved.")
                st.write(f"Serper queries used: **{dorker.queries_used}**")
            except ValueError as e:
                st.error(f"{e}")
            except Exception as e:
                st.error(f"Error: {e}")


# ── Tab 4: Career Hunt ────────────────────────────────────────────────────────
with tab_hunt:
    st.subheader("Career Page Hunter")
    st.caption("Find companies that don't post on big job boards — unknown startups, niche B2B SaaS, indie companies.")

    if not _serper_available:
        st.warning("SERPER_API_KEY not set.")
    else:
        hc1, hc2 = st.columns(2)
        with hc1:
            hunt_tech = st.text_input("Tech / stack", placeholder="python, django, fastapi", key="hunt_tech")
            hunt_role = st.text_input("Role", placeholder="backend engineer", key="hunt_role")
        with hc2:
            hunt_extra = st.text_input("Extra filters", placeholder="startup, remote, seed", key="hunt_extra")
            hunt_results = st.slider("Results per query", 5, 20, 10, key="hunt_res")
            hunt_scrape = st.checkbox("Also scrape found career pages for jobs", value=True, key="hunt_scrape")

        if st.button("🕵️ Hunt Career Pages", type="primary", use_container_width=True):
            from job_scout.discovery.serper_dorking import SerperDorker
            from job_scout.enrichment.filters import matches_criteria
            from job_scout.scraping.base import to_db_job
            from job_scout.scraping.careers import CareerPageScraper

            excl = "-site:linkedin.com -site:indeed.com -site:glassdoor.com -site:lever.co -site:greenhouse.io -site:ashbyhq.com"
            role_q = hunt_role or "engineer OR developer"
            tech_q = f'"{hunt_tech}"' if hunt_tech else ""
            queries = [
                f'intitle:"careers" OR intitle:"join us" "remote" {role_q} {tech_q} {hunt_extra} {excl}',
                f'"we\'re hiring" "remote" {role_q} {tech_q} {hunt_extra} {excl}',
                f'intitle:"open positions" "remote" {role_q} {tech_q} {hunt_extra} {excl}',
                f'site:.io intitle:"careers" "remote" {role_q} {tech_q} -linkedin -indeed',
            ]

            progress = st.progress(0)
            status_t = st.empty()
            results_all = []
            try:
                dorker = SerperDorker()
                for i, q in enumerate(queries):
                    status_t.write(f"Searching ({i+1}/{len(queries)})...")
                    progress.progress((i + 1) / len(queries))
                    results = dorker.search(q, num_results=hunt_results)
                    results_all.extend(results)

                # Extract unique companies
                companies_found = []
                seen_domains: set = set()
                for r in results_all:
                    url = r.get("link", "")
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc.replace("www.", "")
                    if domain and domain not in seen_domains:
                        seen_domains.add(domain)
                        c = dorker.extract_company_from_generic(url, r.get("title", ""), r.get("snippet", ""))
                        if c:
                            companies_found.append(dorker.to_db_format(c))

                existing = {c["name"].lower() for c in db.get_companies(active_only=False, limit=10000)}
                new_cos = [c for c in companies_found if (c.get("name") or "").lower() not in existing]
                inserted = db.add_companies_bulk(new_cos) if new_cos else 0

                progress.progress(1.0)
                status_t.write("**Done!**")
                st.success(f"Found {len(companies_found)} career pages → {inserted} new companies added.")

                if hunt_scrape and new_cos:
                    st.info(f"Scraping career pages of {min(len(new_cos), 20)} newly found companies...")
                    scraper = CareerPageScraper()
                    hunt_criteria = {
                        "title_keywords": [hunt_role] if hunt_role else ["engineer", "developer", "backend"],
                        "required_skills": [hunt_tech] if hunt_tech else [],
                        "remote_only": True,
                        "max_yoe": 5,
                    }
                    jobs_found = 0
                    for co in new_cos[:20]:
                        if co.get("career_url"):
                            try:
                                jobs = scraper.scrape_company(co["career_url"], co.get("name", "Unknown"))
                                matching = [j for j in jobs if matches_criteria(j, hunt_criteria)]
                                company_id = db.find_or_create_company(co["name"], defaults=co)
                                for job in matching:
                                    db_job = to_db_job(job, company_id)
                                    if db.upsert_job(db_job):
                                        jobs_found += 1
                            except Exception:
                                pass
                    if jobs_found:
                        st.success(f"Found {jobs_found} jobs from career pages!")

            except ValueError as e:
                st.error(f"{e}")
            except Exception as e:
                st.error(f"Error: {e}")
                import traceback; st.code(traceback.format_exc())

        # ── Save / load custom queries ────────────────────────────────────────
        st.divider()
        st.write("**Saved Queries**")
        import json as _json
        from pathlib import Path as _Path

        _QFILE = _Path(__file__).parent.parent.parent / "data" / "custom_queries.json"

        def _load_queries() -> list:
            try:
                return _json.loads(_QFILE.read_text())
            except Exception:
                return []

        def _save_query(label: str, tech: str, role: str, extra: str, scheduled: bool = False):
            queries = _load_queries()
            queries = [q for q in queries if q.get("label") != label]  # replace if exists
            queries.append({"label": label, "tech": tech, "role": role, "extra": extra, "scheduled": scheduled})
            _QFILE.parent.mkdir(parents=True, exist_ok=True)
            _QFILE.write_text(_json.dumps(queries, indent=2))

        saved_queries = _load_queries()
        if saved_queries:
            selected_q = st.selectbox(
                "Load saved query",
                ["—"] + [q["label"] for q in saved_queries],
                key="hunt_load_q",
            )
            if selected_q != "—":
                q = next(q for q in saved_queries if q["label"] == selected_q)
                st.caption(f"tech: `{q['tech']}` · role: `{q['role']}` · extra: `{q['extra']}`")
                col_load, col_del = st.columns(2)
                if col_load.button("📂 Load into form", key="hunt_load_btn", use_container_width=True):
                    st.session_state["hunt_tech"] = q["tech"]
                    st.session_state["hunt_role"] = q["role"]
                    st.session_state["hunt_extra"] = q["extra"]
                    st.rerun()
                if col_del.button("🗑️ Delete query", key="hunt_del_btn", use_container_width=True):
                    queries = [x for x in saved_queries if x["label"] != selected_q]
                    _QFILE.write_text(_json.dumps(queries, indent=2))
                    st.rerun()

        with st.expander("💾 Save current query"):
            q_label = st.text_input("Query name", placeholder="Python backend remote seed", key="hunt_qlabel")
            q_scheduled = st.checkbox(
                "Add to daily pipeline (runs with Stage 1 every morning)",
                value=False, key="hunt_qsched",
                help="When checked, this query runs automatically each day as part of the scheduled pipeline.",
            )
            if st.button("Save", key="hunt_save_btn") and q_label:
                _save_query(
                    q_label,
                    st.session_state.get("hunt_tech", ""),
                    st.session_state.get("hunt_role", ""),
                    st.session_state.get("hunt_extra", ""),
                    scheduled=q_scheduled,
                )
                sched_note = " (added to daily pipeline)" if q_scheduled else ""
                st.success(f"Saved query: **{q_label}**{sched_note}")
                st.rerun()


# ── Tab 5: Signals ────────────────────────────────────────────────────────────
with tab_signals:
    st.subheader("📡 Saved Signals")
    st.caption(
        "Signals are saved when you run **Serper Dorking** with distress/funding/hidden_gems categories. "
        "They indicate companies that may be urgently hiring."
    )

    @st.cache_data(ttl=60, show_spinner=False)
    def _load_signals(limit: int = 200):
        try:
            return db._request("GET", "signals", params={
                "order": "created_at.desc", "limit": limit,
            }) or []
        except Exception:
            return []

    signals = _load_signals()

    if not signals:
        st.info(
            "No signals saved yet.\n\n"
            "**How to generate signals:**\n"
            "1. Go to **Serper Dorking** tab\n"
            "2. Select `distress_signals`, `funding_signals`, or `hidden_gems` categories\n"
            "3. Check **Save distress/funding signals to DB**\n"
            "4. Click **Run Dorking**"
        )
    else:
        # Filters
        sf1, sf2 = st.columns(2)
        with sf1:
            sig_types = sorted({s.get("signal_type", "unknown") for s in signals})
            f_type = st.selectbox("Filter by type", ["All"] + sig_types, key="sig_type_f")
        with sf2:
            sig_search = st.text_input("Search company name", key="sig_search")

        filtered_sigs = signals
        if f_type != "All":
            filtered_sigs = [s for s in filtered_sigs if s.get("signal_type") == f_type]
        if sig_search:
            filtered_sigs = [s for s in filtered_sigs if sig_search.lower() in (s.get("company_name") or "").lower()]

        st.write(f"**{len(filtered_sigs)}** signals")

        for sig in filtered_sigs[:100]:
            company = sig.get("company_name") or sig.get("company") or "Unknown"
            sig_type = sig.get("signal_type", "unknown")
            snippet = sig.get("snippet") or sig.get("detail") or ""
            created = str(sig.get("created_at", ""))[:10]
            url = sig.get("url", "")

            icon = {"distress": "🆘", "funding": "💰", "hidden_gem": "💎", "regional": "🌍"}.get(
                sig_type.split("_")[0], "📡"
            )
            with st.expander(f"{icon} **{company}** — {sig_type} ({created})"):
                if snippet:
                    st.caption(snippet[:300])
                if url:
                    st.markdown(f"[🔗 Source]({url})")
