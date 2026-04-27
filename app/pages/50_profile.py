import streamlit as st
import os
import json

st.set_page_config(page_title="Profile — Job Scout", page_icon="📄", layout="wide")

try:
    from db import get_db
    db = get_db()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

def _gemini_key():
    key = os.getenv("GEMINI_API_KEY", "")
    try:
        key = key or st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        pass
    return key if key and key != "your_gemini_api_key_here" else ""

def _load_profile():
    try:
        result = db._request("GET", "user_profile", params={"limit": 1})
        return result[0] if result else None
    except Exception:
        return None

def _save_profile(data: dict, profile_id: str = None):
    try:
        if profile_id:
            db._request("PATCH", f"user_profile?id=eq.{profile_id}", json=data)
        else:
            db._request("POST", "user_profile", json=data)
        return True
    except Exception as e:
        st.error(f"Save error: {e}")
        return False


st.title("📄 Profile")

tab1, tab2 = st.tabs(["📝 Resume", "⚙️ Preferences"])

profile = _load_profile()

# ── Tab 1: Resume ─────────────────────────────────────────────────────────────
with tab1:
    st.subheader("Your Resume")
    st.caption("Used by AI scoring and tailored resume generation.")

    resume_text = st.text_area(
        "Resume (plain text)",
        value=profile.get("resume_text", "") if profile else "",
        height=420,
        placeholder="Paste your full resume here...",
        key="resume_input",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Save Resume", use_container_width=True, type="primary"):
            if resume_text.strip():
                if _save_profile({"resume_text": resume_text.strip()}, profile.get("id") if profile else None):
                    st.success("Resume saved!")
                    st.cache_data.clear()
            else:
                st.warning("Nothing to save.")

    with c2:
        key = _gemini_key()
        if st.button(
            "🤖 Analyze with AI",
            use_container_width=True,
            disabled=not key or not resume_text.strip(),
            help="Extracts skills, experience, roles using Gemini" if key else "Set GEMINI_API_KEY first",
        ):
            os.environ["GEMINI_API_KEY"] = key
            try:
                from job_scout.ai.gemini import GeminiClient
                gemini = GeminiClient()
                prompt = f"""Analyze this resume and return JSON with:
- "summary": 2-3 sentence summary
- "skills": array of technical skills
- "experience_years": integer
- "preferred_roles": array of job titles
- "strengths": array of key strengths

Resume:\n{resume_text[:3000]}\n\nReturn ONLY valid JSON."""
                with st.spinner("Analyzing..."):
                    resp = gemini.generate_json(prompt, max_tokens=1000)
                if resp:
                    update = {
                        "resume_text": resume_text.strip(),
                        "resume_summary": resp.get("summary", ""),
                        "skills": json.dumps(resp.get("skills", [])),
                        "experience_years": resp.get("experience_years", 0),
                        "preferred_roles": json.dumps(resp.get("preferred_roles", [])),
                    }
                    _save_profile(update, profile.get("id") if profile else None)
                    st.success("Analyzed and saved!")
                    st.write(f"**Summary:** {resp.get('summary', '')}")
                    st.write(f"**Experience:** ~{resp.get('experience_years', '?')} years")
                    skills = resp.get("skills", [])
                    if skills:
                        st.write(f"**Skills:** {', '.join(skills[:15])}")
                    roles = resp.get("preferred_roles", [])
                    if roles:
                        st.write(f"**Best fit:** {', '.join(roles)}")
                    profile = _load_profile()
            except Exception as e:
                st.error(f"AI error: {e}")

    # Show existing analysis
    if profile and profile.get("resume_summary"):
        st.divider()
        st.subheader("Saved Analysis")
        st.write(f"**Summary:** {profile.get('resume_summary', '')}")
        st.write(f"**Experience:** {profile.get('experience_years', '?')} years")
        for field, label in [("skills", "Skills"), ("preferred_roles", "Best fit roles")]:
            raw = profile.get(field, "[]")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = []
            if raw:
                st.write(f"**{label}:** {', '.join(raw)}")


# ── Tab 2: Preferences ────────────────────────────────────────────────────────
with tab2:
    st.subheader("Job Search Preferences")
    st.caption("These feed into scoring and filtering across the app — set once, used everywhere.")

    prefs_raw = {}
    if profile and profile.get("preferences"):
        raw = profile["preferences"]
        prefs_raw = raw if isinstance(raw, dict) else {}

    p1, p2 = st.columns(2)
    with p1:
        title_kw = st.text_input(
            "Title keywords (comma-separated)",
            value=", ".join(prefs_raw.get("title_keywords", ["backend", "developer", "engineer", "python", "golang"])),
        )
        skills = st.text_input(
            "Key skills (comma-separated)",
            value=", ".join(prefs_raw.get("skills", ["python", "go", "django", "fastapi", "postgresql", "docker"])),
        )
        exclude_kw = st.text_input(
            "Exclude from title (comma-separated)",
            value=", ".join(prefs_raw.get("exclude_keywords", ["staff", "principal", "director", "vp", "head of"])),
        )
        max_yoe = st.slider("Max years of experience", 0, 15, prefs_raw.get("max_yoe", 5))

    with p2:
        remote_only = st.checkbox("Remote only", value=prefs_raw.get("remote_only", True))
        global_remote = st.checkbox("Global remote (exclude US-only, India-based)", value=prefs_raw.get("global_remote", True))
        min_salary = st.number_input("Min salary (USD, 0 = no filter)", value=prefs_raw.get("min_salary", 0), step=5000)
        max_salary = st.number_input("Max salary (USD, 0 = no filter)", value=prefs_raw.get("max_salary", 0), step=5000)

    if st.button("💾 Save Preferences", use_container_width=True, type="primary"):
        prefs = {
            "title_keywords": [k.strip() for k in title_kw.split(",") if k.strip()],
            "skills": [k.strip() for k in skills.split(",") if k.strip()],
            "exclude_keywords": [k.strip() for k in exclude_kw.split(",") if k.strip()],
            "max_yoe": max_yoe,
            "remote_only": remote_only,
            "global_remote": global_remote,
            "min_salary": min_salary if min_salary > 0 else None,
            "max_salary": max_salary if max_salary > 0 else None,
        }
        if _save_profile({"preferences": prefs}, profile.get("id") if profile else None):
            st.success("Preferences saved!")
            st.cache_data.clear()
