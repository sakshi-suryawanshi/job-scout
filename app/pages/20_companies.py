import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Companies — Job Scout", page_icon="🏢", layout="wide")

try:
    from db import get_db
    db = get_db()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# ── ATS / funding options — single source of truth ───────────────────────────
ATS_OPTIONS = ["greenhouse", "lever", "ashby", "workable", "smartrecruiters",
               "workday", "bamboohr", "pallet", "custom", "unknown"]
FUNDING_OPTIONS = ["", "bootstrapped", "pre-seed", "seed", "series_a", "series_b",
                   "series_c", "public"]
REGION_OPTIONS = ["africa", "asia", "europe", "latam", "north_america", "worldwide"]


def _ats_index(val):
    v = (val or "unknown").lower()
    if v not in ATS_OPTIONS:
        ATS_OPTIONS.append(v)
    return ATS_OPTIONS.index(v)


def _funding_index(val):
    v = val or ""
    if v not in FUNDING_OPTIONS:
        FUNDING_OPTIONS.append(v)
    return FUNDING_OPTIONS.index(v)


st.title("🏢 Companies")

tab_browse, tab_add, tab_bulk, tab_discover = st.tabs([
    "📋 Browse & Edit", "➕ Add Single", "📁 Bulk Upload", "🤖 Auto-Discovery"
])


# ── Tab: Browse & Edit ────────────────────────────────────────────────────────
with tab_browse:
    companies = db.get_companies(active_only=False, limit=5000)

    # Dynamic source filter from actual DB values
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        f_active = st.selectbox("Status", ["All", "Active Only", "Inactive Only"])
    with fc2:
        db_sources = sorted({c.get("source", "") for c in companies if c.get("source")})
        f_source = st.selectbox("Source", ["All"] + db_sources)
    with fc3:
        search = st.text_input("Search by name")

    filtered = companies
    if f_active == "Active Only":   filtered = [c for c in filtered if c.get("is_active")]
    elif f_active == "Inactive Only": filtered = [c for c in filtered if not c.get("is_active")]
    if f_source != "All":            filtered = [c for c in filtered if c.get("source") == f_source]
    if search:                       filtered = [c for c in filtered if search.lower() in c.get("name", "").lower()]

    st.write(f"Showing **{len(filtered)}** of {len(companies)} companies")

    if filtered:
        display = []
        for c in filtered:
            url = c.get("career_url", "") or ""
            display.append({
                "ID": c["id"],
                "Name": c.get("name", ""),
                "Career URL": (url[:50] + "…") if len(url) > 50 else url,
                "ATS": c.get("ats_type", "unknown"),
                "Source": c.get("source", "manual"),
                "Active": "✅" if c.get("is_active") else "❌",
                "Last Scraped": str(c.get("last_scraped", ""))[:10] or "Never",
                "Priority": c.get("priority_score", 0),
            })
        df = pd.DataFrame(display)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Edit or Delete")

        company_names = {f"{c['name']} ({c['id'][:8]})": c["id"] for c in filtered}
        sel_label = st.selectbox("Select company", list(company_names.keys()))
        sel_id = company_names.get(sel_label)

        if sel_id:
            company = db.get_company_by_id(sel_id)
            if company:
                left, right = st.columns(2)

                with left:
                    st.write("**Current:**")
                    st.json({
                        "name": company.get("name"),
                        "career_url": company.get("career_url"),
                        "ats_type": company.get("ats_type"),
                        "is_active": company.get("is_active"),
                        "notes": company.get("notes", ""),
                    })

                with right:
                    st.write("**Quick Actions:**")
                    toggle_label = "Deactivate" if company.get("is_active") else "Activate"
                    if st.button(toggle_label, use_container_width=True):
                        db.update_company(sel_id, {"is_active": not company.get("is_active", True)})
                        st.success(f"{toggle_label}d!")
                        st.rerun()

                    confirm_key = f"confirm_del_{sel_id}"
                    if st.button("🗑️ Delete Company", use_container_width=True, type="secondary"):
                        st.session_state[confirm_key] = True

                    if st.session_state.get(confirm_key):
                        st.warning("⚠️ This cannot be undone.")
                        dc1, dc2 = st.columns(2)
                        with dc1:
                            if st.button("Yes, delete", key=f"del_yes_{sel_id}", type="primary", use_container_width=True):
                                db.delete_company(sel_id)
                                st.session_state.pop(confirm_key, None)
                                st.success("Deleted!")
                                st.rerun()
                        with dc2:
                            if st.button("Cancel", key=f"del_no_{sel_id}", use_container_width=True):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()

                with st.expander("✏️ Edit Full Details"):
                    with st.form("edit_co"):
                        name = st.text_input("Name", value=company.get("name", ""))
                        career_url = st.text_input("Career URL", value=company.get("career_url", "") or "")
                        website = st.text_input("Website", value=company.get("website", "") or "")
                        ats_type = st.selectbox("ATS Type", ATS_OPTIONS, index=_ats_index(company.get("ats_type")))
                        funding_stage = st.selectbox("Funding Stage", FUNDING_OPTIONS, index=_funding_index(company.get("funding_stage")))
                        headcount = st.number_input("Headcount", value=company.get("headcount") or 0, min_value=0)
                        regions_default = company.get("regions") or []
                        if isinstance(regions_default, str):
                            regions_default = [r.strip() for r in regions_default.split(",") if r.strip()]
                        regions = st.multiselect("Regions", REGION_OPTIONS, default=[r for r in regions_default if r in REGION_OPTIONS])
                        is_remote_first = st.checkbox("Remote First", value=company.get("is_remote_first", False))
                        notes = st.text_area("Notes", value=company.get("notes", "") or "")
                        if st.form_submit_button("💾 Save"):
                            updates = {
                                "name": name, "career_url": career_url, "website": website or None,
                                "ats_type": ats_type, "funding_stage": funding_stage or None,
                                "headcount": headcount if headcount > 0 else None,
                                "regions": regions, "is_remote_first": is_remote_first, "notes": notes,
                            }
                            if db.update_company(sel_id, updates):
                                st.success("Saved!")
                                st.rerun()
    else:
        st.info("No companies found. Add some below!")

    # Sidebar stats
    try:
        active_cnt = len([c for c in companies if c.get("is_active")])
        st.sidebar.metric("Total Companies", len(companies))
        st.sidebar.metric("Active", active_cnt)
        st.sidebar.metric("Inactive", len(companies) - active_cnt)
        st.sidebar.divider()
        src_counts: dict = {}
        for c in companies:
            src = c.get("source", "unknown")
            src_counts[src] = src_counts.get(src, 0) + 1
        st.sidebar.subheader("By Source")
        for src, cnt in sorted(src_counts.items(), key=lambda x: -x[1]):
            st.sidebar.write(f"- {src}: {cnt}")
    except Exception:
        pass


# ── Tab: Add Single ───────────────────────────────────────────────────────────
with tab_add:
    st.subheader("Add New Company")
    with st.form("add_co"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Company Name *", placeholder="e.g., Acme Inc")
            career_url = st.text_input("Career Page URL *", placeholder="https://company.com/careers")
            website = st.text_input("Website", placeholder="https://company.com")
            ats_type = st.selectbox("ATS Type", ATS_OPTIONS)
        with c2:
            funding_stage = st.selectbox("Funding Stage", FUNDING_OPTIONS)
            headcount = st.number_input("Headcount", min_value=0, step=1)
            regions = st.multiselect("Regions", REGION_OPTIONS)
            is_remote_first = st.checkbox("Remote First")
        notes = st.text_area("Notes")
        if st.form_submit_button("➕ Add Company", use_container_width=True):
            if not name or not career_url:
                st.error("Name and Career URL are required.")
            else:
                result = db.add_company({
                    "name": name, "career_url": career_url, "website": website or None,
                    "ats_type": ats_type, "funding_stage": funding_stage or None,
                    "headcount": headcount if headcount > 0 else None,
                    "regions": regions, "is_remote_first": is_remote_first,
                    "source": "manual", "is_active": True, "notes": notes or None, "priority_score": 5,
                })
                if result:
                    st.success(f"✅ Added {name}!")
                else:
                    st.error("Failed to add (may be a duplicate name).")


# ── Tab: Bulk Upload ──────────────────────────────────────────────────────────
with tab_bulk:
    st.subheader("Bulk Upload via CSV")
    st.caption("Required columns: `name`, `career_url`. Optional: `website`, `ats_type`, `funding_stage`, `headcount`, `regions`, `notes`")

    tpl = pd.DataFrame({
        "name": ["Acme Corp", "Startup XYZ"],
        "career_url": ["https://acme.com/careers", "https://startup.xyz/jobs"],
        "website": ["https://acme.com", "https://startup.xyz"],
        "ats_type": ["greenhouse", "unknown"],
        "funding_stage": ["series_a", "seed"],
        "headcount": [80, 12],
        "regions": ["worldwide", "europe"],
        "notes": ["", "Remote-first team"],
    })
    buf = io.StringIO()
    tpl.to_csv(buf, index=False)
    st.download_button("📥 Download Template", buf.getvalue(), "companies_template.csv", "text/csv")

    uploaded = st.file_uploader("Upload CSV", type="csv")
    if uploaded:
        try:
            df = pd.read_csv(uploaded)
            st.write(f"Found **{len(df)}** rows")
            st.dataframe(df.head(5), use_container_width=True)
            missing = [c for c in ["name", "career_url"] if c not in df.columns]
            if missing:
                st.error(f"Missing required columns: {missing}")
            else:
                companies_to_add = []
                for _, row in df.iterrows():
                    regions_raw = str(row.get("regions", "") or "")
                    companies_to_add.append({
                        "name": str(row["name"]).strip(),
                        "career_url": str(row["career_url"]).strip(),
                        "website": str(row.get("website", "")).strip() or None,
                        "ats_type": str(row.get("ats_type", "unknown")).strip() if pd.notna(row.get("ats_type")) else "unknown",
                        "funding_stage": str(row.get("funding_stage", "")).strip() or None,
                        "headcount": int(row["headcount"]) if pd.notna(row.get("headcount")) else None,
                        "regions": [r.strip() for r in regions_raw.split(",") if r.strip()],
                        "notes": str(row.get("notes", "")).strip() or None,
                        "source": "manual", "is_active": True, "priority_score": 5,
                    })
                if st.button("🚀 Import All", use_container_width=True, type="primary"):
                    with st.spinner(f"Importing {len(companies_to_add)} companies..."):
                        inserted = db.add_companies_bulk(companies_to_add)
                    st.success(f"✅ Imported {inserted} companies!")
                    if inserted < len(companies_to_add):
                        st.warning(f"{len(companies_to_add) - inserted} skipped (duplicates).")
        except Exception as e:
            st.error(f"Error reading CSV: {e}")


# ── Tab: Auto-Discovery ───────────────────────────────────────────────────────
with tab_discover:
    st.subheader("Auto-Discovery")

    d1, d2 = st.columns(2)

    with d1:
        st.write("**Y Combinator**")
        yc_batch = st.selectbox("Batch", ["W24", "S23", "W23", "S22", "Recent"], key="yc_b")
        yc_limit = st.slider("Max companies", 10, 200, 50, key="yc_l")
        if st.button("🚀 Fetch YC Companies", use_container_width=True, key="yc_btn"):
            with st.spinner("Fetching from yclist.com..."):
                try:
                    from job_scout.discovery.yc import fetch_yc_companies
                    batch = None if yc_batch == "Recent" else yc_batch
                    companies_yc = fetch_yc_companies(batch=batch, limit=yc_limit)
                    existing = db.get_companies(active_only=False, limit=10000)
                    existing_names = {c["name"].lower() for c in existing}
                    new = [c for c in companies_yc if c["name"].lower() not in existing_names]
                    if new:
                        inserted = db.add_companies_bulk(new)
                        st.success(f"✅ Added {inserted} new YC companies!")
                        st.balloons()
                    else:
                        st.info("No new companies (all already in DB).")
                except Exception as e:
                    st.error(f"Error: {e}")

    with d2:
        st.write("**Alternative Sources**")
        st.caption("Wellfound RSS, RemoteOK, WeWorkRemotely")
        if st.button("🌐 Fetch Alternative Sources", use_container_width=True, key="alt_btn"):
            with st.spinner("Fetching..."):
                try:
                    from job_scout.discovery.alternative import fetch_alternative_sources
                    alt_companies = fetch_alternative_sources()
                    existing = db.get_companies(active_only=False, limit=10000)
                    existing_names = {c["name"].lower() for c in existing}
                    new = [c for c in alt_companies if (c.get("name") or "").lower() not in existing_names]
                    if new:
                        inserted = db.add_companies_bulk(new)
                        st.success(f"✅ Added {inserted} companies!")
                    else:
                        st.info("No new companies found.")
                except Exception as e:
                    st.error(f"Error: {e}")

    st.divider()
    st.write("**Product Hunt**")
    st.info("⚠️ Product Hunt (403 Forbidden). Use Discovery → Serper Dorking with `job_boards` or `hidden_gems` categories instead.")
