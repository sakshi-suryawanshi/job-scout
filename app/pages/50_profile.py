import streamlit as st
import os
import io
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

def _extract_pdf(file_bytes: bytes) -> str:
    """Extract plain text from a PDF file using pdfminer.six."""
    try:
        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.layout import LAParams
        output = io.StringIO()
        extract_text_to_fp(
            io.BytesIO(file_bytes),
            output,
            laparams=LAParams(),
            output_type="text",
            codec="utf-8",
        )
        text = output.getvalue()
        # Collapse excessive blank lines left by pdfminer
        import re
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text
    except Exception as e:
        st.error(f"PDF parse error: {e}")
        return ""


def _extract_tex(file_bytes: bytes) -> str:
    """Strip LaTeX markup and return plain text.

    Primary:  pylatexenc — handles most LaTeX constructs.
    Fallback: regex stripper — used when pylatexenc crashes on
              unsupported commands (e.g. \\href with URL arguments).
    """
    import re
    source = file_bytes.decode("utf-8", errors="replace")

    # Pre-process: replace \href{url}{label} → label  (pylatexenc crashes on these)
    source_clean = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", source)
    # Also flatten \url{...} → the URL text
    source_clean = re.sub(r"\\url\{([^}]*)\}", r"\1", source_clean)

    # Primary: pylatexenc
    try:
        from pylatexenc.latex2text import LatexNodes2Text
        plain = LatexNodes2Text().latex_to_text(source_clean)
        plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
        if len(plain) > 100:      # sanity check — at least some content
            return plain
    except Exception:
        pass   # fall through to regex stripper

    # Fallback: regex-based LaTeX stripper
    text = source
    text = re.sub(r"\\begin\{[^}]+\}|\\end\{[^}]+\}", "", text)   # environments
    text = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", text)     # \href{url}{label}
    text = re.sub(r"\\url\{([^}]*)\}", r"\1", text)               # \url{...}
    text = re.sub(r"\\[a-zA-Z]+\*?\{([^}]*)\}", r"\1", text)      # \cmd{content} → content
    text = re.sub(r"\\[a-zA-Z]+\*?\s*", " ", text)                # bare \commands
    text = re.sub(r"[{}]", " ", text)                              # leftover braces
    text = re.sub(r"%[^\n]*", "", text)                            # % comments
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) > 100:
        return text

    st.error("Could not extract text from the .tex file. Use the plain-text fallback below.")
    return ""


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
    st.caption("Upload your resume as **PDF** or **LaTeX (.tex)** — used for AI scoring, tailored applications, and Playwright form fills.")

    # ── Current resume status ─────────────────────────────────────────────────
    existing_text = (profile.get("resume_text", "") or "") if profile else ""
    if existing_text:
        word_count = len(existing_text.split())
        st.success(f"✅ Resume on file — {word_count:,} words. Upload a new file to replace it.")
    else:
        st.warning("No resume on file yet. Upload your PDF or .tex file below.")

    st.divider()

    # ── PRIMARY: File upload (PDF or .tex) ───────────────────────────────────
    st.write("**Upload resume file**")
    uploaded = st.file_uploader(
        "Choose a PDF or LaTeX (.tex) file",
        type=["pdf", "tex"],
        help="PDF: any standard resume PDF. LaTeX: .tex source file (LaTeX markup is stripped automatically).",
        key="resume_upload",
    )

    extracted_text = ""
    if uploaded is not None:
        file_bytes = uploaded.read()
        ext = uploaded.name.rsplit(".", 1)[-1].lower()

        with st.spinner(f"Parsing {ext.upper()} file…"):
            if ext == "pdf":
                extracted_text = _extract_pdf(file_bytes)
            elif ext == "tex":
                extracted_text = _extract_tex(file_bytes)

        if extracted_text:
            st.success(f"✅ Extracted {len(extracted_text.split()):,} words from **{uploaded.name}**")
            with st.expander("Preview extracted text (first 800 chars)"):
                st.text(extracted_text[:800] + ("…" if len(extracted_text) > 800 else ""))
        else:
            st.error("Could not extract text from the file. Try a different file or paste manually below.")

    # Action buttons (only active when a file was just uploaded)
    b1, b2 = st.columns(2)
    with b1:
        save_disabled = not extracted_text.strip()
        if st.button("💾 Save Resume", use_container_width=True, type="primary",
                     disabled=save_disabled,
                     help="Upload a file above first" if save_disabled else "Save extracted text to DB"):
            if _save_profile({"resume_text": extracted_text.strip()},
                             profile.get("id") if profile else None):
                st.success("Resume saved!")
                st.cache_data.clear()
                profile = _load_profile()
                st.rerun()

    with b2:
        gemini_key = _gemini_key()
        analyze_disabled = not extracted_text.strip() or not gemini_key
        if st.button("🤖 Save & Analyze with AI", use_container_width=True,
                     disabled=analyze_disabled,
                     help="Saves resume and extracts skills / experience / roles using Gemini" if gemini_key else "Set GEMINI_API_KEY first"):
            os.environ["GEMINI_API_KEY"] = gemini_key
            try:
                from job_scout.ai.gemini import GeminiClient
                gemini = GeminiClient()
                prompt = f"""Analyze this resume and return JSON with:
- "summary": 2-3 sentence professional summary
- "skills": array of technical skills (languages, frameworks, tools)
- "experience_years": integer (total years of professional experience)
- "preferred_roles": array of job titles that best fit this person
- "strengths": array of 3-5 key professional strengths

Resume:
{extracted_text[:3000]}

Return ONLY valid JSON."""
                with st.spinner("Analyzing with Gemini…"):
                    resp = gemini.generate_json(prompt, max_tokens=1000)
                if resp:
                    update = {
                        "resume_text":     extracted_text.strip(),
                        "resume_summary":  resp.get("summary", ""),
                        "skills":          json.dumps(resp.get("skills", [])),
                        "experience_years": resp.get("experience_years", 0),
                        "preferred_roles": json.dumps(resp.get("preferred_roles", [])),
                    }
                    if _save_profile(update, profile.get("id") if profile else None):
                        st.success("✅ Resume saved and analyzed!")
                        st.cache_data.clear()
                        profile = _load_profile()
                    else:
                        st.warning("Analysis complete but DB save failed — check connection.")
                    ac1, ac2 = st.columns(2)
                    ac1.write(f"**Summary:** {resp.get('summary','')}")
                    ac1.write(f"**Experience:** ~{resp.get('experience_years','?')} years")
                    if resp.get("skills"):
                        ac2.write(f"**Skills:** {', '.join(resp['skills'][:15])}")
                    if resp.get("preferred_roles"):
                        ac2.write(f"**Best fit:** {', '.join(resp['preferred_roles'])}")
            except Exception as e:
                st.error(f"AI error: {e}")

    # ── FALLBACK: Plain text paste ────────────────────────────────────────────
    st.divider()
    with st.expander("✏️ Paste plain text instead (fallback option)"):
        st.caption("Use this if your file won't upload, or you want to paste a plain-text version.")
        resume_text_manual = st.text_area(
            "Resume text",
            value=existing_text,
            height=340,
            placeholder="Paste your full resume here…",
            key="resume_manual_input",
        )
        mc1, mc2 = st.columns(2)
        with mc1:
            if st.button("💾 Save text", use_container_width=True, key="save_manual"):
                if resume_text_manual.strip():
                    if _save_profile({"resume_text": resume_text_manual.strip()},
                                     profile.get("id") if profile else None):
                        st.success("Saved!")
                        st.cache_data.clear()
                        profile = _load_profile()
                        st.rerun()
                else:
                    st.warning("Nothing to save.")
        with mc2:
            gemini_key2 = _gemini_key()
            if st.button("🤖 Analyze text", use_container_width=True, key="analyze_manual",
                         disabled=not resume_text_manual.strip() or not gemini_key2):
                os.environ["GEMINI_API_KEY"] = gemini_key2
                try:
                    from job_scout.ai.gemini import GeminiClient
                    gemini2 = GeminiClient()
                    prompt2 = f"""Analyze this resume and return JSON:
{{"summary":"...","skills":[...],"experience_years":0,"preferred_roles":[...]}}

Resume:\n{resume_text_manual[:3000]}\n\nReturn ONLY valid JSON."""
                    with st.spinner("Analyzing…"):
                        resp2 = gemini2.generate_json(prompt2, max_tokens=1000)
                    if resp2:
                        update2 = {
                            "resume_text":      resume_text_manual.strip(),
                            "resume_summary":   resp2.get("summary", ""),
                            "skills":           json.dumps(resp2.get("skills", [])),
                            "experience_years": resp2.get("experience_years", 0),
                            "preferred_roles":  json.dumps(resp2.get("preferred_roles", [])),
                        }
                        if _save_profile(update2, profile.get("id") if profile else None):
                            st.success("Analyzed and saved!")
                            profile = _load_profile()
                except Exception as e:
                    st.error(f"AI error: {e}")

    # ── Saved analysis display ────────────────────────────────────────────────
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
