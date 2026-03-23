import streamlit as st
import os

st.set_page_config(page_title="Job Scout", page_icon="🔍")

st.title("Debug: Secret Loading")

# Show what we have (masked)
supabase_url = os.getenv("SUPABASE_URL", "NOT_SET")
supabase_key = os.getenv("SUPABASE_KEY", "NOT_SET")

st.write(f"SUPABASE_URL: {'✅ Set' if supabase_url and supabase_url != 'NOT_SET' else '❌ Not Set'}")
st.write(f"SUPABASE_KEY: {'✅ Set (masked)' if supabase_key and supabase_key != 'NOT_SET' else '❌ Not Set'}")

if supabase_url and supabase_url != "NOT_SET":
    st.write(f"URL starts with: {supabase_url[:20]}...")

# Try loading
try:
    from db import Database
    db = Database()
    st.success("✅ Database connected!")
except Exception as e:
    st.error(f"❌ Error: {str(e)}")
    import traceback
    st.code(traceback.format_exc())