import streamlit as st
import os

st.set_page_config(
    page_title="Job Scout V2",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load secrets into env before any DB import
for key in ("SUPABASE_URL", "SUPABASE_KEY", "GEMINI_API_KEY", "SERPER_API_KEY"):
    try:
        val = st.secrets.get(key)
        if val:
            os.environ[key] = val
    except Exception:
        pass

st.switch_page("pages/00_dashboard.py")
