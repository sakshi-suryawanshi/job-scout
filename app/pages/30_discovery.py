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

tab_scrape, tab_dorking, tab_hunt, tab_signals = st.tabs([
    "🚀 Scrape Jobs", "🕵️ Serper Dorking", "🏭 Career Hunt", "📡 Signals"
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
        # Registry-driven: every board registered in _all_boards_registry() shows
        # up here automatically. Initial-checked state comes from boards_config.json.
        from job_scout.scraping.boards._orchestrator import (
            _all_boards_registry, _get_enabled_boards,
        )
        _registry = _all_boards_registry({})
        _all_keys = sorted(_registry.keys(), key=lambda k: _registry[k][0].lower())
        _enabled = set(_get_enabled_boards(_all_keys))

        col_select_all, col_clear = st.columns(2)
        if col_select_all.button("Select all", key="b_sel_all", use_container_width=True):
            for k in _all_keys:
                st.session_state[f"b_{k}"] = True
            st.rerun()
        if col_clear.button("Clear", key="b_clear", use_container_width=True):
            for k in _all_keys:
                st.session_state[f"b_{k}"] = False
            st.rerun()

        board_checks = {}
        # Show all boards in a scrollable container so 70+ checkboxes don't overwhelm the page.
        with st.container(height=420):
            for key in _all_keys:
                label = _registry[key][0]
                board_checks[key] = st.checkbox(
                    f"{label}  `{key}`",
                    value=st.session_state.get(f"b_{key}", key in _enabled),
                    key=f"b_{key}",
                )
        st.caption(f"{sum(board_checks.values())} / {len(_all_keys)} boards selected")

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
        grand = {"total_scraped": 0, "matched": 0, "saved": 0, "errors": 0, "by_board": {}}
        phases = sum([bool(ats_types), bool(boards), career_pages])
        phase = 0

        def _merge_by_board(grand_dict, stats_dict, default_key="other"):
            """Merge a phase's by_board dict into grand. ATS/career phases get
            a single composite key since they don't report per-source counts."""
            by_board = stats_dict.get("by_board") or {}
            if by_board:
                for k, v in by_board.items():
                    bucket = grand_dict["by_board"].setdefault(k, {"scraped": 0, "matched": 0, "saved": 0})
                    for kk in ("scraped", "matched", "saved"):
                        bucket[kk] += int(v.get(kk, 0) or 0)
            else:
                bucket = grand_dict["by_board"].setdefault(default_key, {"scraped": 0, "matched": 0, "saved": 0})
                bucket["scraped"] += int(stats_dict.get("total_scraped", 0) or 0)
                bucket["matched"] += int(stats_dict.get("matched", 0) or 0)
                bucket["saved"]   += int(stats_dict.get("saved", 0) or 0)

        if ats_types:
            status.write("**Scraping ATS boards...**")
            for i, ats in enumerate(ats_types):
                def _ap(msg, p, _i=i):
                    progress.progress(min((phase + (_i + p) / len(ats_types)) / phases, 0.99))
                    status.write(f"ATS: {msg}")
                stats = scrape_ats_jobs(db=db, ats_types=[ats], criteria=criteria, max_slugs_per_ats=max_slugs, progress_callback=_ap)
                for k, v in stats.items():
                    if k in grand and isinstance(grand[k], int):
                        grand[k] += (v if isinstance(v, int) else 0)
                _merge_by_board(grand, stats, default_key=f"ats:{ats}")
            phase += 1

        if boards:
            status.write("**Scraping job boards...**")
            def _bp(msg, p):
                progress.progress(min((phase + p) / phases, 0.99))
                status.write(f"Boards: {msg}")
            stats = scrape_board_jobs(db=db, boards=boards, criteria=criteria, progress_callback=_bp)
            for k, v in stats.items():
                if k in grand and isinstance(grand[k], int):
                    grand[k] += (v if isinstance(v, int) else 0)
            _merge_by_board(grand, stats)
            phase += 1

        if career_pages:
            status.write("**Scraping career pages...**")
            def _cp(msg, p):
                progress.progress(min((phase + p) / phases, 0.99))
                status.write(f"Career pages: {msg}")
            stats = scrape_career_pages(db=db, criteria=criteria, max_companies=max_cp, progress_callback=_cp)
            for k, v in stats.items():
                if k in grand and isinstance(grand[k], int):
                    grand[k] += (v if isinstance(v, int) else 0)
            _merge_by_board(grand, stats, default_key="career_pages")

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

        # ── Per-board breakdown ──────────────────────────────────────────────
        from job_scout.scraping.boards._orchestrator import _all_boards_registry as _reg_fn
        _reg = _reg_fn({})
        rows = []
        for k, bs in grand["by_board"].items():
            display_name = _reg[k][0] if k in _reg else k
            rows.append({
                "Board":   display_name,
                "Key":     k,
                "Scraped": bs["scraped"],
                "Matched": bs["matched"],
                "Saved":   bs["saved"],
            })
        rows.sort(key=lambda r: (-r["Saved"], -r["Scraped"]))

        if rows:
            st.divider()
            st.subheader(f"📊 Per-board breakdown ({len(rows)} sources)")
            empty = [r for r in rows if r["Scraped"] == 0]
            if empty:
                st.caption(
                    f"⚠️ **{len(empty)} board(s) returned 0 jobs** — likely a wrong feed URL or rate-limit. "
                    f"Check `_extra.py` for: {', '.join(r['Key'] for r in empty[:8])}"
                    + ("…" if len(empty) > 8 else "")
                )
            st.dataframe(rows, use_container_width=True, hide_index=True)

        # Score new jobs
        from job_scout.ai.gemini import score_all_jobs
        if _gemini_key and grand["saved"] > 0:
            with st.spinner("Scoring new jobs with AI..."):
                os.environ["GEMINI_API_KEY"] = _gemini_key
                score_result = score_all_jobs(db=db, criteria=criteria, use_ai=True, max_jobs=300)
            st.info(f"Scored {score_result['scored']} jobs (avg {score_result['avg_score']}).")


# ── Tab 2: Serper Dorking (Daily LinkedIn/Indeed merged in as a preset) ─────
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

        all_cats = sorted(DORK_QUERIES.keys())
        default_cats = ["distress_signals", "funding_signals", "hidden_gems", "yc_latest", "ats_hiring"]

        # New categories added in the 2026-05 audit — surface them so the user
        # discovers them without having to scan the dropdown.
        new_cats = ["founding_engineer", "tech_stack_specific", "community_boards",
                    "filetype_hidden", "industry_vertical", "culture_filters"]
        new_present = [c for c in new_cats if c in all_cats]
        total_dorks = sum(len(v) for v in DORK_QUERIES.values())
        st.caption(
            f"📚 **{len(all_cats)} categories · {total_dorks} dorks** total. "
            + (f"✨ **{len(new_present)} new categories** available — "
               + ", ".join(f"`{c}`" for c in new_present)
               if new_present else "")
        )

        # Buttons to seed the selection. "📅 Daily" also flags an auto-run on
        # the next rerun (preserves the old Daily-tab one-click workflow).
        bc1, bc2, bc3, bc4 = st.columns(4)
        if bc1.button("Default 5", use_container_width=True, key="dork_seed_default"):
            st.session_state["dork_selected"] = default_cats
            st.rerun()
        if bc2.button("✨ Add new 6", use_container_width=True, key="dork_seed_new"):
            current = st.session_state.get("dork_selected", default_cats)
            st.session_state["dork_selected"] = sorted(set(current) | set(new_present))
            st.rerun()
        if bc3.button("Select all", use_container_width=True, key="dork_seed_all"):
            st.session_state["dork_selected"] = all_cats
            st.rerun()
        if bc4.button("📅 Daily LinkedIn+Indeed", use_container_width=True, key="dork_seed_daily",
                      help="One-click preset: runs linkedin_daily + indeed_daily immediately (1-day cooldown, auto-saves signals)."):
            st.session_state["dork_selected"] = ["linkedin_daily", "indeed_daily"]
            st.session_state["dork_auto_run_daily"] = True
            st.rerun()

        selected_cats = st.multiselect(
            "Select dork categories",
            all_cats,
            default=st.session_state.get("dork_selected", default_cats),
            key="dork_selected_widget",
        )
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

        def _run_dorking(cats_to_run, results_per_q, max_q_per_cat, force_run, save_signals):
            """Shared run path for both the explicit Run button and the Daily preset.
            max_q_per_cat=None means 'no per-category cap' (Daily preset uses this)."""
            from job_scout.discovery.serper_dorking import SerperDorker, create_signal_from_result
            progress = st.progress(0)
            status_txt = st.empty()
            try:
                dorker = SerperDorker()
                all_companies = []
                for i, cat in enumerate(cats_to_run):
                    status_txt.write(f"Category: **{cat}** ({i+1}/{len(cats_to_run)})")
                    progress.progress((i + 1) / len(cats_to_run))
                    companies = dorker.run_dork_category(
                        cat,
                        **({"max_queries": max_q_per_cat} if max_q_per_cat else {}),
                        results_per_query=results_per_q,
                        force=force_run,
                    )
                    all_companies.extend(companies)

                db_companies = [dorker.to_db_format(c) for c in all_companies]
                existing = {c["name"].lower() for c in db.get_companies(active_only=False, limit=10000)}
                new_cos = [c for c in db_companies if (c.get("name") or "").lower() not in existing and c.get("name")]

                inserted = db.add_companies_bulk(new_cos) if new_cos else 0

                sig_count = 0
                if save_signals:
                    signal_cats = {"distress", "funding", "hidden", "regional", "hackernews", "indiehackers"}
                    for company in all_companies:
                        cat_found = company.get("source_category", "")
                        if cat_found in signal_cats:
                            sig = create_signal_from_result(company, cat_found)
                            if db.add_signal(sig):
                                sig_count += 1

                progress.progress(1.0)
                status_txt.write("**Done!**")
                st.success(
                    f"Found {len(all_companies)} results → {inserted} new companies added. "
                    f"{sig_count if save_signals else 0} signals saved."
                )
                st.write(f"Serper queries used: **{dorker.queries_used}**")
            except ValueError as e:
                st.error(f"{e}")
            except Exception as e:
                st.error(f"Error: {e}")
                import traceback; st.code(traceback.format_exc())

        # Auto-run path: triggered by the 📅 Daily preset button. Uses 1-day-cooldown
        # categories with auto-signal-saving on and no per-category query cap.
        if st.session_state.pop("dork_auto_run_daily", False):
            st.info("📅 Running Daily LinkedIn+Indeed preset…")
            _run_dorking(
                cats_to_run=["linkedin_daily", "indeed_daily"],
                results_per_q=10,
                max_q_per_cat=None,
                force_run=False,
                save_signals=True,
            )

        if st.button("🔎 Run Dorking", type="primary", use_container_width=True, disabled=not selected_cats):
            _run_dorking(
                cats_to_run=selected_cats,
                results_per_q=results_per,
                max_q_per_cat=max_q,
                force_run=force,
                save_signals=save_sigs,
            )


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

    def _sig_field(sig: dict, key: str) -> str:
        """Pull a field from a signal row.

        `create_signal_from_result()` writes company_name/snippet/url into the
        `metadata` JSON column, not the top-level columns. Try top-level first
        for forward-compat, then fall back to metadata.
        """
        val = sig.get(key)
        if val:
            return val
        meta = sig.get("metadata") or {}
        return meta.get(key) or ""

    @st.cache_data(ttl=60, show_spinner=False)
    def _load_signals(limit: int = 200):
        # No silent except — let the error bubble so we can show it in the UI.
        rows = db._request("GET", "signals", params={
            "order": "created_at.desc", "limit": limit,
        }) or []
        return rows

    # Refresh + load
    refresh_col, _ = st.columns([1, 5])
    if refresh_col.button("🔄 Refresh", key="sig_refresh", use_container_width=True):
        _load_signals.clear()
        st.rerun()

    try:
        signals = _load_signals()
    except Exception as e:
        st.error(f"Failed to load signals from DB: {e}")
        signals = []

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
            needle = sig_search.lower()
            filtered_sigs = [s for s in filtered_sigs if needle in _sig_field(s, "company_name").lower()]

        # Clear distinction between "DB empty" and "filtered to nothing"
        if filtered_sigs:
            st.write(f"**{len(filtered_sigs)}** signals (of {len(signals)} in DB)")
        else:
            st.warning(
                f"0 of **{len(signals)}** signals match your filter — "
                f"clear the search box{' / change Filter by type' if f_type != 'All' else ''} to see all."
            )

        for sig in filtered_sigs[:100]:
            company  = _sig_field(sig, "company_name") or "Unknown"
            sig_type = sig.get("signal_type", "unknown")
            snippet  = _sig_field(sig, "snippet")
            created  = str(sig.get("created_at", ""))[:10]
            url      = _sig_field(sig, "url")
            src      = sig.get("source_signal", "")

            icon = {"distress": "🆘", "funding": "💰", "hidden": "💎",
                    "hiring": "📢", "github_activity": "🐙", "regional": "🌍"}.get(
                sig_type, "📡"
            )
            with st.expander(f"{icon} **{company}** — {sig_type} ({created})"):
                if snippet:
                    st.caption(snippet[:300])
                if src:
                    st.caption(f"Source: `{src}`")
                if url:
                    st.markdown(f"[🔗 Open]({url})")
