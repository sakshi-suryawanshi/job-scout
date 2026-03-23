import streamlit as st
import os
import sys

# Page config FIRST (before any other code)
st.set_page_config(
    page_title="Job Scout",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Secrets handling
def get_secrets():
    """Get secrets from Streamlit Cloud or local .env"""
    try:
        return {
            "SUPABASE_URL": st.secrets["SUPABASE_URL"],
            "SUPABASE_KEY": st.secrets["SUPABASE_KEY"]
        }
    except Exception:
        # Already loaded by db.py, but ensure env is set
        return {
            "SUPABASE_URL": os.getenv("SUPABASE_URL"),
            "SUPABASE_KEY": os.getenv("SUPABASE_KEY")
        }

# Set environment from secrets
secrets = get_secrets()
os.environ["SUPABASE_URL"] = secrets["SUPABASE_URL"] or ""
os.environ["SUPABASE_KEY"] = secrets["SUPABASE_KEY"] or ""

# Now import db (after env is set)
db = None  # Initialize as None first
try:
    from db import get_db
    db = get_db()
    db_status = "✅ Database connected"
except Exception as e:
    db_status = f"❌ Database error: {str(e)[:50]}"

# Sidebar
st.sidebar.title("🔍 Job Scout")
st.sidebar.markdown("AI-Powered Job Discovery")
st.sidebar.write(db_status)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #FF4B4B;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
    }
</style>
""", unsafe_allow_html=True)

# Main content
st.markdown('<p class="main-header">Job Scout</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Discover hidden gem jobs across the web</p>', unsafe_allow_html=True)

# Metrics - only if db connected
col1, col2, col3, col4 = st.columns(4)

if db:
    try:
        companies = db.get_companies(active_only=True)
        jobs = db.get_jobs(is_new=True, limit=1000)
        
        with col1:
            st.metric("Companies Tracked", len(companies))
        with col2:
            st.metric("New Jobs", len([j for j in jobs if j.get('is_new')]))
        with col3:
            st.metric("Recommended", len([j for j in jobs if j.get('is_recommended')]))
        with col4:
            st.metric("Sources", len(set(c.get('source') for c in companies if c.get('source'))))
    except Exception as e:
        st.error(f"Error loading stats: {e}")
else:
    st.warning("Database not connected. Check secrets configuration.")

# Quick actions
st.divider()
st.subheader("Quick Actions")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("🔍 Start Job Search", use_container_width=True):
        st.switch_page("pages/1_Search.py")

with col2:
    if st.button("🏢 Manage Companies", use_container_width=True):
        st.switch_page("pages/2_Companies.py")

with col3:
    if st.button("📡 View Signals", use_container_width=True):
        st.switch_page("pages/3_Signals.py")