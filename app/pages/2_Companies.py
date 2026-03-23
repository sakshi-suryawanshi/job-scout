import streamlit as st
import pandas as pd
from datetime import datetime
import io

st.set_page_config(page_title="Companies", page_icon="🏢", layout="wide")

st.title("🏢 Company Database")
st.markdown("Manage companies to scout for job opportunities")

# Import db
try:
    from db import get_db
    db = get_db()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# Initialize session state
if "edit_company_id" not in st.session_state:
    st.session_state.edit_company_id = None
if "refresh" not in st.session_state:
    st.session_state.refresh = False

# Tabs for different functions
tab1, tab2, tab3 = st.tabs(["📋 Browse & Edit", "➕ Add Single", "📁 Bulk Upload"])

# ========== TAB 1: BROWSE & EDIT ==========
with tab1:
    st.subheader("All Companies")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        filter_active = st.selectbox("Status", ["All", "Active Only", "Inactive Only"])
    with col2:
        filter_source = st.selectbox("Source", ["All", "Manual", "YC Directory", "Product Hunt", "Job Board", "Funding Signal"])
    with col3:
        search_name = st.text_input("Search by name", "")
    
    # Get companies with filters
    companies = db.get_companies(active_only=False, limit=5000)
    
    # Apply filters
    filtered = companies
    if filter_active == "Active Only":
        filtered = [c for c in filtered if c.get("is_active")]
    elif filter_active == "Inactive Only":
        filtered = [c for c in filtered if not c.get("is_active")]
    
    if filter_source != "All":
        source_map = {
            "Manual": "manual",
            "YC Directory": "yc_directory",
            "Product Hunt": "product_hunt",
            "Job Board": "job_board",
            "Funding Signal": "funding_signal"
        }
        filtered = [c for c in filtered if c.get("source") == source_map.get(filter_source)]
    
    if search_name:
        filtered = [c for c in filtered if search_name.lower() in c.get("name", "").lower()]
    
    st.write(f"Showing {len(filtered)} of {len(companies)} companies")
    
    # Display as table
    if filtered:
        # Prepare display data
        display_data = []
        for c in filtered:
            display_data.append({
                "ID": c["id"],
                "Name": c.get("name", ""),
                "Career URL": (c.get("career_url", "")[:50] + "...") if c.get("career_url") and len(c.get("career_url", "")) > 50 else c.get("career_url", ""),
                "ATS": c.get("ats_type", "unknown"),
                "Source": c.get("source", "manual"),
                "Active": "✅" if c.get("is_active") else "❌",
                "Last Scraped": c.get("last_scraped", "Never")[:10] if c.get("last_scraped") else "Never",
                "Priority": c.get("priority_score", 0)
            })
        
        df = pd.DataFrame(display_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Edit/Delete section
        st.divider()
        st.subheader("Edit or Delete Company")
        
        company_options = {f"{c['name']} ({c['id'][:8]})": c["id"] for c in filtered}
        selected_label = st.selectbox("Select company", list(company_options.keys()))
        selected_id = company_options[selected_label] if selected_label else None
        
        if selected_id:
            company = db.get_company_by_id(selected_id)
            
            if company:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**Current Values:**")
                    st.json({
                        "name": company.get("name"),
                        "career_url": company.get("career_url"),
                        "ats_type": company.get("ats_type"),
                        "is_active": company.get("is_active"),
                        "notes": company.get("notes", "")
                    })
                
                with col2:
                    st.write("**Quick Actions:**")
                    
                    # Toggle active
                    new_status = not company.get("is_active", True)
                    action_text = "Deactivate" if company.get("is_active") else "Activate"
                    if st.button(f"{action_text} Company", use_container_width=True):
                        db.update_company(selected_id, {"is_active": new_status})
                        st.success(f"Company {action_text.lower()}d!")
                        st.session_state.refresh = True
                        st.rerun()
                    
                    # Delete
                    if st.button("🗑️ Delete Company", use_container_width=True, type="secondary"):
                        if st.checkbox("Confirm deletion - this cannot be undone"):
                            db.delete_company(selected_id)
                            st.success("Company deleted!")
                            st.session_state.refresh = True
                            st.rerun()
                
                # Edit form
                with st.expander("✏️ Full Edit"):
                    with st.form("edit_company"):
                        name = st.text_input("Company Name", value=company.get("name", ""))
                        career_url = st.text_input("Career URL", value=company.get("career_url", ""))
                        website = st.text_input("Website", value=company.get("website", ""))
                        
                        ats_type = st.selectbox(
                            "ATS Type",
                            ["greenhouse", "lever", "workday", "ashby", "bamboohr", "custom", "unknown"],
                            index=["greenhouse", "lever", "workday", "ashby", "bamboohr", "custom", "unknown"].index(
                                company.get("ats_type", "unknown")
                            )
                        )
                        
                        funding_stage = st.selectbox(
                            "Funding Stage",
                            ["", "bootstrapped", "pre-seed", "seed", "series_a", "series_b", "series_c", "public"],
                            index=0 if not company.get("funding_stage") else 
                                ["", "bootstrapped", "pre-seed", "seed", "series_a", "series_b", "series_c", "public"].index(
                                    company.get("funding_stage")
                                )
                        )
                        
                        headcount = st.number_input("Headcount", 
                                                   value=company.get("headcount") or 0, 
                                                   min_value=0, 
                                                   step=1)
                        
                        regions = st.multiselect(
                            "Regions",
                            ["africa", "asia", "europe", "latam", "north_america", "worldwide"],
                            default=company.get("regions", [])
                        )
                        
                        is_remote_first = st.checkbox("Remote First", 
                                                     value=company.get("is_remote_first", False))
                        
                        notes = st.text_area("Notes", value=company.get("notes", ""))
                        
                        submitted = st.form_submit_button("💾 Save Changes")
                        
                        if submitted:
                            updates = {
                                "name": name,
                                "career_url": career_url,
                                "website": website,
                                "ats_type": ats_type,
                                "funding_stage": funding_stage or None,
                                "headcount": headcount if headcount > 0 else None,
                                "regions": regions,
                                "is_remote_first": is_remote_first,
                                "notes": notes
                            }
                            
                            if db.update_company(selected_id, updates):
                                st.success("Company updated!")
                                st.rerun()
                            else:
                                st.error("Failed to update")
    else:
        st.info("No companies found. Add some in the 'Add Single' or 'Bulk Upload' tabs!")

# ========== TAB 2: ADD SINGLE ==========
with tab2:
    st.subheader("Add New Company")
    
    with st.form("add_company"):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Company Name *", placeholder="e.g., Wassha Inc")
            career_url = st.text_input("Career Page URL *", placeholder="https://company.com/careers")
            website = st.text_input("Website", placeholder="https://company.com")
            
            ats_type = st.selectbox(
                "ATS Type (if known)",
                ["unknown", "greenhouse", "lever", "workday", "ashby", "bamboohr", "custom"],
                help="Select the applicant tracking system they use"
            )
        
        with col2:
            funding_stage = st.selectbox(
                "Funding Stage",
                ["", "bootstrapped", "pre-seed", "seed", "series_a", "series_b", "series_c", "public"]
            )
            
            headcount = st.number_input("Headcount", min_value=0, step=1, value=0)
            
            regions = st.multiselect(
                "Regions",
                ["africa", "asia", "europe", "latam", "north_america", "worldwide"],
                default=[]
            )
            
            is_remote_first = st.checkbox("Remote First Company")
        
        notes = st.text_area("Notes", placeholder="e.g., Japanese company in Africa, hidden gem, easy to get in")
        
        submitted = st.form_submit_button("➕ Add Company", use_container_width=True)
        
        if submitted:
            if not name or not career_url:
                st.error("Company Name and Career URL are required!")
            else:
                company = {
                    "name": name,
                    "career_url": career_url,
                    "website": website or None,
                    "ats_type": ats_type,
                    "funding_stage": funding_stage or None,
                    "headcount": headcount if headcount > 0 else None,
                    "regions": regions,
                    "is_remote_first": is_remote_first,
                    "source": "manual",
                    "is_active": True,
                    "notes": notes or None,
                    "priority_score": 0
                }
                
                result = db.add_company(company)
                if result:
                    st.success(f"✅ Added {name}!")
                    st.json(result)
                else:
                    st.error("Failed to add company")

# ========== TAB 3: BULK UPLOAD ==========
with tab3:
    st.subheader("Bulk Upload Companies")
    
    st.markdown("""
    Upload a CSV file with company data. Required columns: `name`, `career_url`
    
    Optional columns: `website`, `ats_type`, `funding_stage`, `headcount`, `regions`, `notes`
    """)
    
    # Download template
    template_df = pd.DataFrame({
        "name": ["Wassha Inc", "Example Startup"],
        "career_url": ["https://wassha.com/careers", "https://example.com/jobs"],
        "website": ["https://wassha.com", "https://example.com"],
        "ats_type": ["custom", "greenhouse"],
        "funding_stage": ["series_a", "seed"],
        "headcount": [45, 12],
        "regions": ["africa,asia", "europe"],
        "notes": ["Japanese company in Africa", "Remote first"]
    })
    
    csv_buffer = io.StringIO()
    template_df.to_csv(csv_buffer, index=False)
    st.download_button(
        "📥 Download CSV Template",
        csv_buffer.getvalue(),
        "companies_template.csv",
        "text/csv"
    )
    
    st.divider()
    
    # Upload section
    uploaded_file = st.file_uploader("Upload CSV", type="csv")
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            st.write(f"📄 Found {len(df)} rows")
            st.dataframe(df.head(10), use_container_width=True)
            
            # Validate required columns
            required = ["name", "career_url"]
            missing = [col for col in required if col not in df.columns]
            
            if missing:
                st.error(f"❌ Missing required columns: {missing}")
            else:
                # Prepare data
                companies_to_add = []
                
                for _, row in df.iterrows():
                    company = {
                        "name": str(row["name"]).strip(),
                        "career_url": str(row["career_url"]).strip(),
                        "website": str(row.get("website", "")).strip() if pd.notna(row.get("website")) else None,
                        "ats_type": str(row.get("ats_type", "unknown")).strip() if pd.notna(row.get("ats_type")) else "unknown",
                        "funding_stage": str(row.get("funding_stage", "")).strip() if pd.notna(row.get("funding_stage")) else None,
                        "headcount": int(row["headcount"]) if pd.notna(row.get("headcount")) else None,
                        "regions": [r.strip() for r in str(row.get("regions", "")).split(",") if r.strip()] if pd.notna(row.get("regions")) else [],
                        "notes": str(row.get("notes", "")).strip() if pd.notna(row.get("notes")) else None,
                        "source": "manual",
                        "is_active": True,
                        "priority_score": 0
                    }
                    companies_to_add.append(company)
                
                st.write(f"✅ Validated {len(companies_to_add)} companies")
                
                if st.button("🚀 Import All Companies", use_container_width=True, type="primary"):
                    with st.spinner(f"Adding {len(companies_to_add)} companies..."):
                        inserted = db.add_companies_bulk(companies_to_add)
                        st.success(f"✅ Successfully imported {inserted} companies!")
                        if inserted < len(companies_to_add):
                            st.warning(f"⚠️ {len(companies_to_add) - inserted} failed (possibly duplicates)")
                        
        except Exception as e:
            st.error(f"Error reading CSV: {e}")

# Sidebar stats
st.sidebar.divider()
st.sidebar.subheader("Database Stats")

try:
    all_companies = db.get_companies(active_only=False, limit=10000)
    active = len([c for c in all_companies if c.get("is_active")])
    inactive = len([c for c in all_companies if not c.get("is_active")])
    
    st.sidebar.metric("Total Companies", len(all_companies))
    st.sidebar.metric("Active", active)
    st.sidebar.metric("Inactive", inactive)
    
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