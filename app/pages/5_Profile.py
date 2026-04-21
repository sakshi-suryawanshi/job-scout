import streamlit as st
import os
import sys
import json

st.set_page_config(page_title="Profile", page_icon="👤", layout="wide")

st.title("👤 My Profile")
st.markdown("Paste your resume for better job matching with AI scoring")

# Import db
try:
    from db import get_db
    db = get_db()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# Import Gemini
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "worker", "ai"))

# ========== TABS ==========
tab1, tab2 = st.tabs(["📝 Resume", "⚙️ Preferences"])

# ========== TAB 1: RESUME ==========
with tab1:
    st.subheader("Your Resume")
    st.markdown("Paste your resume text below. This will be used to score jobs more accurately.")

    # Load existing profile
    existing_profile = None
    try:
        result = db._request("GET", "user_profile", params={"limit": 1})
        if result:
            existing_profile = result[0]
    except Exception:
        pass

    resume_text = st.text_area(
        "Resume text",
        value=existing_profile.get("resume_text", "") if existing_profile else "",
        height=400,
        placeholder="Paste your full resume here...\n\nExample:\nSakshi Suryawanshi\nSoftware Engineer | Python, Go, Django, FastAPI\n\n2+ years of experience building backend services...",
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("💾 Save Resume", use_container_width=True, type="primary"):
            if resume_text.strip():
                profile_data = {
                    "resume_text": resume_text.strip(),
                }
                try:
                    if existing_profile:
                        db._request("PATCH", f"user_profile?id=eq.{existing_profile['id']}", json=profile_data)
                    else:
                        db._request("POST", "user_profile", json=profile_data)
                    st.success("Resume saved!")
                except Exception as e:
                    st.error(f"Error saving: {e}")
            else:
                st.warning("Please paste your resume first.")

    with col2:
        # Check for Gemini
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        try:
            gemini_key = gemini_key or st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            pass
        has_gemini = gemini_key and gemini_key != "your_gemini_api_key_here"

        if st.button(
            "🤖 Analyze with AI",
            use_container_width=True,
            disabled=not has_gemini or not resume_text.strip(),
            help="Extracts skills, experience level, and summary using Gemini AI",
        ):
            if has_gemini:
                os.environ["GEMINI_API_KEY"] = gemini_key

            try:
                from gemini_client import GeminiClient
                gemini = GeminiClient()

                with st.spinner("Analyzing resume with Gemini..."):
                    prompt = f"""Analyze this resume and extract structured information.
Return a JSON object with these fields:
- "summary": a 2-3 sentence professional summary
- "skills": array of technical skills mentioned
- "experience_years": estimated total years of experience (integer)
- "preferred_roles": array of job titles this person would be a good fit for
- "strengths": array of key strengths

Resume:
{resume_text[:3000]}

Return ONLY valid JSON, no markdown."""

                    response = gemini.generate(prompt)
                    if response:
                        # Parse JSON from response
                        try:
                            # Try to find JSON in response
                            json_text = response.strip()
                            if "```" in json_text:
                                json_text = json_text.split("```")[1]
                                if json_text.startswith("json"):
                                    json_text = json_text[4:]
                            analysis = json.loads(json_text)

                            # Save to profile
                            profile_update = {
                                "resume_text": resume_text.strip(),
                                "resume_summary": analysis.get("summary", ""),
                                "skills": json.dumps(analysis.get("skills", [])),
                                "experience_years": analysis.get("experience_years", 0),
                                "preferred_roles": json.dumps(analysis.get("preferred_roles", [])),
                            }

                            if existing_profile:
                                db._request("PATCH", f"user_profile?id=eq.{existing_profile['id']}", json=profile_update)
                            else:
                                db._request("POST", "user_profile", json=profile_update)

                            st.success("Resume analyzed and saved!")

                            # Display results
                            st.divider()
                            st.write(f"**Summary:** {analysis.get('summary', 'N/A')}")
                            st.write(f"**Experience:** ~{analysis.get('experience_years', 'N/A')} years")

                            skills = analysis.get("skills", [])
                            if skills:
                                st.write(f"**Skills:** {', '.join(skills)}")

                            roles = analysis.get("preferred_roles", [])
                            if roles:
                                st.write(f"**Best fit roles:** {', '.join(roles)}")

                            strengths = analysis.get("strengths", [])
                            if strengths:
                                st.write(f"**Strengths:** {', '.join(strengths)}")

                        except json.JSONDecodeError:
                            st.warning("AI returned non-JSON response. Resume saved as text only.")
                            st.code(response[:500])
                    else:
                        st.error("No response from Gemini.")

            except Exception as e:
                st.error(f"AI analysis error: {e}")

        if not has_gemini:
            st.caption("Set GEMINI_API_KEY in .env to enable AI analysis.")

    # Show existing analysis
    if existing_profile and existing_profile.get("resume_summary"):
        st.divider()
        st.subheader("Current Profile Analysis")
        st.write(f"**Summary:** {existing_profile.get('resume_summary', '')}")
        st.write(f"**Experience:** {existing_profile.get('experience_years', 'N/A')} years")

        skills = existing_profile.get("skills", "[]")
        if isinstance(skills, str):
            try:
                skills = json.loads(skills)
            except Exception:
                skills = []
        if skills:
            st.write(f"**Skills:** {', '.join(skills)}")

        roles = existing_profile.get("preferred_roles", "[]")
        if isinstance(roles, str):
            try:
                roles = json.loads(roles)
            except Exception:
                roles = []
        if roles:
            st.write(f"**Best fit roles:** {', '.join(roles)}")


# ========== TAB 2: PREFERENCES ==========
with tab2:
    st.subheader("Job Search Preferences")
    st.markdown("These preferences are used as defaults when scraping and scoring.")

    pcol1, pcol2 = st.columns(2)

    with pcol1:
        pref_roles = st.text_input(
            "Target roles (comma-separated)",
            value="software engineer, backend developer, full stack developer",
        )
        pref_skills = st.text_input(
            "Key skills (comma-separated)",
            value="python, go, django, fastapi, postgresql, docker",
        )
        pref_yoe = st.slider("Years of experience", 0, 15, 3)

    with pcol2:
        pref_remote = st.checkbox("Remote only", value=True)
        pref_global = st.checkbox("Global remote (exclude US-only, India-based)", value=True)
        pref_company_size = st.selectbox("Preferred company size", [
            "Any",
            "Small (< 50 people)",
            "Mid (50-200 people)",
            "Small + Mid (< 200 people)",
        ])

    st.info("These preferences are for reference. The actual filtering happens on the Search page.")
