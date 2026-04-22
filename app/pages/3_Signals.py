import streamlit as st
import pandas as pd
import os
import sys

st.set_page_config(page_title="Signals & Discovery", page_icon="📡", layout="wide")

st.title("📡 Signals & Discovery")
st.markdown("Google dorking via Serper.dev + signal monitoring for hidden gem startups")

# Import db
try:
    from db import get_db
    db = get_db()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# Load SERPER_API_KEY from Streamlit secrets if available
try:
    serper_key = st.secrets.get("SERPER_API_KEY")
    if serper_key:
        os.environ["SERPER_API_KEY"] = serper_key
except Exception:
    pass

# Import serper dorking
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "worker", "discovery"))
    from serper_dorking import SerperDorker, create_signal_from_result
    serper_available = bool(os.getenv("SERPER_API_KEY"))
except ImportError:
    serper_available = False

# ========== TABS ==========
tab1, tab2, tab3 = st.tabs(["🔎 Serper Dorking", "📊 Signal Dashboard", "⚙️ Query Builder"])

# ========== TAB 1: SERPER DORKING ==========
with tab1:
    if not serper_available:
        st.warning("SERPER_API_KEY not set. Add it to your .env file to enable Google dorking.")
        st.code("# Add to your .env file:\nSERPER_API_KEY=your_key_here", language="bash")
        st.markdown("Get a free API key at [serper.dev](https://serper.dev) (2,500 searches/month free)")
        st.stop()

    st.subheader("Google Dorking Discovery")
    st.markdown("Search Google for hidden startup jobs using targeted dork queries.")

    # Category selection
    st.write("**Select categories to search:**")

    category_descriptions = {
        "ats_hiring": "🏢 ATS Boards (Greenhouse, Lever, Ashby) — direct job listings",
        "job_boards": "📋 Job Boards (Wellfound 1-10 employees, WWR, Arbeitnow, Jobicy)",
        "career_pages": "🌐 Career Pages — direct company career pages",
        "distress_signals": "🚨 Distress Signals — founding engineers, solo founders, desperate hiring",
        "funding_signals": "💰 Funding Signals — recently funded startups (dynamic year)",
        "hidden_gems": "💎 Hidden Gems — founding engineer roles, first hires, obscure markets",
        "github_signals": "🐙 GitHub Signals — active open source companies",
        "regional_gems": "🌍 Regional Gems — Japan, Africa, SEA, Eastern Europe",
        "yc_latest": "🚀 Latest YC Batch — newest YC companies hiring remotely",
        "twitter_x": "🐦 Twitter/X — startups posting hiring on X (via Serper)",
        "salary_targeted": "💵 Salary Targeted — explicitly $40k-$70k remote roles",
        "linkedin_jobs": "💼 LinkedIn Jobs — remote roles via Google dorking (no scraping)",
        "pallet_boards": "🎨 Pallet Boards — indie startup job boards (site:pallet.xyz)",
        "x_urgent_hiring": "🚨 X Urgent Hiring — founders posting urgently on X/Twitter",
        "salary_transparent": "🏷️ Salary Transparent — Glassdoor/Cord/Hired with $40-60k shown",
    }

    col1, col2 = st.columns(2)
    selected_categories = []

    for i, (cat, desc) in enumerate(category_descriptions.items()):
        target_col = col1 if i % 2 == 0 else col2
        with target_col:
            if st.checkbox(desc, value=cat in (
                "distress_signals", "hidden_gems", "funding_signals", "yc_latest",
                "job_boards", "salary_targeted", "linkedin_jobs", "pallet_boards",
                "x_urgent_hiring", "salary_transparent",
            ), key=f"cat_{cat}"):
                selected_categories.append(cat)

    # Budget controls
    st.divider()
    st.write("**Budget Controls** (free tier: 2,500 searches/month)")

    # Show live quota + cooldown status
    try:
        from serper_dorking import get_serper_usage, is_category_on_cooldown
        s_usage = get_serper_usage()
        pct = s_usage["calls_this_month"] / s_usage["limit"]
        if pct >= 0.9:
            st.error(f"Serper quota: {s_usage['calls_this_month']}/{s_usage['limit']} this month — almost full!")
        elif pct >= 0.6:
            st.warning(f"Serper quota: {s_usage['calls_this_month']}/{s_usage['limit']} used — {s_usage['remaining']} left this month")
        else:
            st.caption(f"Serper quota: {s_usage['calls_this_month']}/{s_usage['limit']} used — {s_usage['remaining']} remaining this month")

        # Show cooldown status for selected categories
        cooled = []
        for cat in selected_categories:
            on_cd, days_ago = is_category_on_cooldown(cat)
            if on_cd:
                cooled.append(f"{cat} ({days_ago}d ago)")
        if cooled:
            st.info(f"These categories are on 7-day cooldown and will be skipped: {', '.join(cooled)}. Check 'Force re-run' to override.")
    except Exception:
        pass

    bcol1, bcol2, bcol3, bcol4 = st.columns(4)
    with bcol1:
        max_queries = st.slider("Max queries per category", 1, 10, 2, help="Each query = 1 Serper credit")
    with bcol2:
        results_per_query = st.slider("Results per query", 5, 20, 10)
    with bcol3:
        total_estimate = len(selected_categories) * max_queries
        st.metric("Estimated queries", total_estimate)
        st.caption("of 2,500/month free")
    with bcol4:
        force_rerun = st.checkbox("Force re-run (ignore cooldown)", value=False,
                                  help="Override 7-day cooldown and re-query all selected categories")

    # Run discovery
    st.divider()

    if st.button("🚀 Run Serper Discovery", use_container_width=True, type="primary", disabled=not selected_categories):
        dorker = SerperDorker()

        progress_bar = st.progress(0)
        status_text = st.empty()
        results_container = st.container()

        all_companies = []
        all_signals = []
        total_steps = len(selected_categories)

        for i, category in enumerate(selected_categories):
            status_text.write(f"🔍 Searching **{category}**... ({i+1}/{total_steps})")
            progress_bar.progress((i) / total_steps)

            try:
                companies = dorker.run_dork_category(
                    category,
                    max_queries=max_queries,
                    results_per_query=results_per_query,
                    force=force_rerun,
                )

                # Convert to DB format
                db_companies = [dorker.to_db_format(c) for c in companies]

                # Create signals for relevant categories
                signal_cats = {"distress_signals", "funding_signals", "hidden_gems", "regional_gems"}
                if category in signal_cats:
                    for c in companies:
                        sig = create_signal_from_result(c, c.get("source_category", category))
                        all_signals.append(sig)

                all_companies.extend(db_companies)

            except Exception as e:
                st.warning(f"Error in {category}: {e}")

        progress_bar.progress(1.0)
        status_text.write("✅ Dorking complete!")

        # Deduplicate
        seen = set()
        unique_companies = []
        for c in all_companies:
            name_key = c["name"].lower().strip()
            if name_key and name_key not in seen and len(name_key) > 1:
                seen.add(name_key)
                unique_companies.append(c)

        # Show results
        with results_container:
            st.subheader(f"Results: {len(unique_companies)} unique companies found")
            st.caption(f"Serper queries used: {dorker.queries_used}")

            if unique_companies:
                # Display as table
                display_data = []
                for c in unique_companies:
                    display_data.append({
                        "Name": c["name"],
                        "Career URL": c.get("career_url", "")[:60],
                        "ATS": c.get("ats_type", "unknown"),
                        "Priority": c.get("priority_score", 0),
                        "Notes": (c.get("notes") or "")[:80],
                    })

                df = pd.DataFrame(display_data)
                st.dataframe(df, use_container_width=True, hide_index=True)

                # Import button
                st.divider()
                if st.button(
                    f"💾 Import {len(unique_companies)} companies to database",
                    use_container_width=True,
                    type="primary",
                ):
                    with st.spinner("Importing..."):
                        # Check duplicates against DB
                        existing = db.get_companies(active_only=False, limit=10000)
                        existing_names = {c["name"].lower() for c in existing}

                        new_companies = [
                            c for c in unique_companies
                            if c["name"].lower() not in existing_names
                        ]

                        if new_companies:
                            inserted = db.add_companies_bulk(new_companies)
                            st.success(f"✅ Imported {inserted} new companies! ({len(unique_companies) - len(new_companies)} duplicates skipped)")

                            # Save signals
                            if all_signals:
                                saved = 0
                                for sig in all_signals:
                                    if db.add_signal(sig):
                                        saved += 1
                                st.info(f"📡 Saved {saved} discovery signals")

                            st.balloons()
                        else:
                            st.info("All companies already exist in the database.")
            else:
                st.info("No companies found. Try different categories or increase query limits.")


# ========== TAB 2: SIGNAL DASHBOARD ==========
with tab2:
    st.subheader("Signal Dashboard")

    # Fetch signals
    try:
        unprocessed = db.get_unprocessed_signals(limit=200)
    except Exception:
        unprocessed = []

    if unprocessed:
        # Group by signal type
        signal_types = {}
        for sig in unprocessed:
            stype = sig.get("signal_type", "unknown")
            signal_types.setdefault(stype, []).append(sig)

        # Metrics
        mcols = st.columns(4)
        type_list = list(signal_types.keys())
        for i, stype in enumerate(type_list[:4]):
            with mcols[i]:
                st.metric(stype.replace("_", " ").title(), len(signal_types[stype]))

        st.divider()

        # Signal table
        signal_data = []
        for sig in unprocessed:
            meta = sig.get("metadata", {}) or {}
            signal_data.append({
                "Type": sig.get("signal_type", "unknown"),
                "Confidence": f"{sig.get('confidence_score', 0):.0%}",
                "Source": sig.get("source_signal", ""),
                "Company": meta.get("company_name", "N/A"),
                "Context": meta.get("snippet", "")[:100],
                "Created": str(sig.get("created_at", ""))[:10],
            })

        df = pd.DataFrame(signal_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Mark processed button
        if st.button("✅ Mark all as processed"):
            processed = 0
            for sig in unprocessed:
                if db.mark_signal_processed(sig["id"]):
                    processed += 1
            st.success(f"Marked {processed} signals as processed")
            st.rerun()
    else:
        st.info("No unprocessed signals. Run Serper Dorking to discover new signals!")


# ========== TAB 3: QUERY BUILDER ==========
with tab3:
    st.subheader("Custom Query Builder")
    st.markdown("Build and test custom Google dork queries for specific targets.")

    if not serper_available:
        st.warning("SERPER_API_KEY not set.")
        st.stop()

    # Preset templates
    st.write("**Quick Templates:**")
    templates = {
        "Seed startups on Greenhouse": 'site:boards.greenhouse.io "remote" "seed" "engineer"',
        "Remote jobs in Africa": '"hiring" "remote" "developer" "africa" startup',
        "Desperate founders on HN": 'site:news.ycombinator.com "hiring" "urgently" "remote"',
        "Recently funded + hiring": '"raised" "seed" "million" "hiring" "remote" 2025 OR 2026',
        "Small teams hiring": '"join our team" "remote" "<50 employees" "engineer"',
        "Japan hidden gems": '"hiring" "remote" "engineer" "japan" "startup"',
    }

    selected_template = st.selectbox("Load template", ["Custom..."] + list(templates.keys()))

    if selected_template != "Custom...":
        default_query = templates[selected_template]
    else:
        default_query = ""

    custom_query = st.text_input(
        "Google dork query",
        value=default_query,
        placeholder='site:boards.greenhouse.io "remote" "python"',
    )

    num_results = st.slider("Number of results", 5, 30, 10, key="custom_num")

    if st.button("🔍 Test Query", disabled=not custom_query):
        with st.spinner("Searching..."):
            try:
                dorker = SerperDorker()
                results = dorker.search(custom_query, num_results=num_results)

                if results:
                    st.success(f"Found {len(results)} results (1 query used)")

                    for i, r in enumerate(results):
                        with st.expander(f"{i+1}. {r.get('title', 'No title')[:80]}"):
                            st.write(f"**URL:** {r.get('link', '')}")
                            st.write(f"**Snippet:** {r.get('snippet', '')}")

                            # Try to parse as company
                            companies = dorker.parse_results([r], "custom")
                            if companies:
                                c = companies[0]
                                st.write("---")
                                st.write(f"**Extracted company:** {c.get('name')}")
                                st.write(f"**Career URL:** {c.get('career_url')}")
                                st.write(f"**ATS:** {c.get('ats_type')}")
                else:
                    st.warning("No results found. Try adjusting the query.")
            except Exception as e:
                st.error(f"Error: {e}")

    # Dork syntax help
    with st.expander("📖 Google Dork Syntax Reference"):
        st.markdown("""
| Operator | Usage | Example |
|----------|-------|---------|
| `site:` | Search within a specific site | `site:boards.greenhouse.io` |
| `intitle:` | Search in page title | `intitle:"careers"` |
| `"..."` | Exact phrase match | `"remote engineer"` |
| `OR` | Match either term | `"python" OR "golang"` |
| `-` | Exclude term | `-linkedin -glassdoor` |
| `*` | Wildcard | `"hiring * engineer"` |

**Tips for finding hidden gems:**
- Use `site:boards.greenhouse.io` or `site:jobs.lever.co` for ATS-based companies
- Add `"seed"` or `"series a"` to target early-stage startups
- Use `"<50 employees"` or `"small team"` to filter company size
- Combine region terms like `"africa"`, `"southeast asia"` for regional gems
- Add `-linkedin -glassdoor -indeed` to exclude major boards
        """)


# ========== SIDEBAR STATS ==========
try:
    all_companies = db.get_companies(active_only=False, limit=10000)
    serper_companies = [c for c in all_companies if c.get("source") == "serper"]

    st.sidebar.divider()
    st.sidebar.subheader("📡 Discovery Stats")
    st.sidebar.metric("Total Companies", len(all_companies))
    st.sidebar.metric("From Serper", len(serper_companies))

    try:
        unprocessed_count = len(db.get_unprocessed_signals(limit=1000))
        st.sidebar.metric("Pending Signals", unprocessed_count)
    except Exception:
        pass

    # Source breakdown
    st.sidebar.divider()
    st.sidebar.subheader("By Source")
    sources = {}
    for c in all_companies:
        src = c.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        st.sidebar.write(f"- {src}: {count}")

except Exception as e:
    st.sidebar.error(f"Stats error: {e}")
