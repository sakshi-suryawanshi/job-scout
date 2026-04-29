import streamlit as st
import os
import json
from pathlib import Path

st.set_page_config(page_title="Profile — Job Scout", page_icon="📄", layout="wide")

try:
    from db import get_db
    db = get_db()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_PDF_PATH  = _DATA_DIR / "resume.pdf"
_TEX_PATH  = _DATA_DIR / "resume.tex"


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

# ── Tab 1: Resume ──────────────────────────────────────────────────────────────
with tab1:
    st.subheader("Your Resume")

    # ── Status row ────────────────────────────────────────────────────────────
    sc1, sc2 = st.columns(2)
    with sc1:
        if _PDF_PATH.exists():
            sc1.success(f"✅ PDF on file — {_PDF_PATH.stat().st_size // 1024} KB  *(used by Playwright for form uploads)*")
        else:
            sc1.info("No PDF uploaded yet.")
    with sc2:
        if _TEX_PATH.exists():
            sc2.success(f"✅ .tex on file — {_TEX_PATH.stat().st_size // 1024} KB  *(sent to Gemini for tailoring)*")
        else:
            sc2.info("No .tex file uploaded yet.")

    st.divider()

    col_pdf, col_tex = st.columns(2)

    # ── LEFT: PDF ─────────────────────────────────────────────────────────────
    with col_pdf:
        st.write("**📄 PDF — ATS form attachment**")
        st.caption(
            "Playwright attaches this file directly to the resume upload field "
            "on Greenhouse / Lever / Ashby forms. **Never modified — sent as-is.**"
        )
        pdf_file = st.file_uploader(
            "Upload PDF", type=["pdf"], key="upload_pdf",
            label_visibility="collapsed",
        )
        if pdf_file:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            _PDF_PATH.write_bytes(pdf_file.read())
            st.success(f"✅ Saved **{pdf_file.name}**")
            st.rerun()

        if _PDF_PATH.exists():
            if st.button("🗑️ Remove PDF", key="del_pdf", use_container_width=True):
                _PDF_PATH.unlink()
                st.rerun()

    # ── RIGHT: .tex ───────────────────────────────────────────────────────────
    with col_tex:
        st.write("**🔧 LaTeX (.tex) — Gemini tailoring**")
        st.caption(
            "The **raw .tex source** is sent directly to Gemini when tailoring your resume "
            "for a job. Gemini reads LaTeX natively — no text extraction, no information lost."
        )
        tex_file = st.file_uploader(
            "Upload .tex", type=["tex"], key="upload_tex",
            label_visibility="collapsed",
        )
        if tex_file:
            raw_bytes = tex_file.read()
            raw_tex   = raw_bytes.decode("utf-8", errors="replace")
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            _TEX_PATH.write_bytes(raw_bytes)

            # Save raw LaTeX source to DB — Gemini will receive it as-is
            if _save_profile({"resume_text": raw_tex}, profile.get("id") if profile else None):
                st.success(
                    f"✅ Saved **{tex_file.name}** to disk and DB "
                    f"({len(raw_bytes)} bytes). "
                    "Gemini will receive the full LaTeX source."
                )
                st.cache_data.clear()
                profile = _load_profile()
                st.rerun()
            else:
                st.warning("File saved to disk but DB save failed — check connection.")

        if _TEX_PATH.exists():
            with st.expander("Preview raw .tex source (first 600 chars)"):
                st.code(_TEX_PATH.read_text(encoding="utf-8", errors="replace")[:600], language="latex")
            if st.button("🗑️ Remove .tex", key="del_tex", use_container_width=True):
                _TEX_PATH.unlink()
                st.rerun()

    # ── Analyze with AI ───────────────────────────────────────────────────────
    st.divider()
    existing_tex = profile.get("resume_text", "") if profile else ""
    gemini_key   = _gemini_key()

    if st.button(
        "🤖 Analyze with AI (extract skills & summary)",
        use_container_width=True,
        disabled=not existing_tex or not gemini_key,
        help="Gemini reads the raw .tex source and extracts your skills, experience, and best-fit roles"
              if gemini_key else "Set GEMINI_API_KEY first",
    ):
        os.environ["GEMINI_API_KEY"] = gemini_key
        try:
            from job_scout.ai.gemini import GeminiClient
            gemini = GeminiClient()
            prompt = f"""This is a LaTeX resume source file. Analyze it and return JSON with:
- "summary": 2-3 sentence professional summary (plain text, no LaTeX)
- "skills": array of technical skills extracted from the resume
- "experience_years": integer — total years of professional experience
- "preferred_roles": array of job titles this person is best suited for

LaTeX resume:
{existing_tex[:4000]}

Return ONLY valid JSON."""
            with st.spinner("Gemini reading your .tex resume…"):
                resp = gemini.generate_json(prompt, max_tokens=1000)
            if resp:
                update = {
                    "resume_summary":   resp.get("summary", ""),
                    "skills":           json.dumps(resp.get("skills", [])),
                    "experience_years": resp.get("experience_years", 0),
                    "preferred_roles":  json.dumps(resp.get("preferred_roles", [])),
                }
                if _save_profile(update, profile.get("id") if profile else None):
                    st.success("✅ Analysis saved!")
                    st.cache_data.clear()
                    profile = _load_profile()
                ac1, ac2 = st.columns(2)
                ac1.write(f"**Summary:** {resp.get('summary', '')}")
                ac1.write(f"**Experience:** ~{resp.get('experience_years', '?')} yrs")
                if resp.get("skills"):
                    ac2.write(f"**Skills:** {', '.join(resp['skills'][:15])}")
                if resp.get("preferred_roles"):
                    ac2.write(f"**Roles:** {', '.join(resp['preferred_roles'])}")
        except Exception as e:
            st.error(f"AI error: {e}")

    # ── Saved Analysis ────────────────────────────────────────────────────────
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


# ── Tab 2: Preferences ─────────────────────────────────────────────────────────
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
        remote_only    = st.checkbox("Remote only",    value=prefs_raw.get("remote_only", True))
        global_remote  = st.checkbox("Global remote (exclude US-only, India-based)", value=prefs_raw.get("global_remote", True))
        min_salary = st.number_input("Min salary (USD, 0 = no filter)", value=prefs_raw.get("min_salary", 0), step=5000)
        max_salary = st.number_input("Max salary (USD, 0 = no filter)", value=prefs_raw.get("max_salary", 0), step=5000)

    if st.button("💾 Save Preferences", use_container_width=True, type="primary"):
        prefs = {
            "title_keywords":  [k.strip() for k in title_kw.split(",") if k.strip()],
            "skills":          [k.strip() for k in skills.split(",") if k.strip()],
            "exclude_keywords":[k.strip() for k in exclude_kw.split(",") if k.strip()],
            "max_yoe":         max_yoe,
            "remote_only":     remote_only,
            "global_remote":   global_remote,
            "min_salary":      min_salary if min_salary > 0 else None,
            "max_salary":      max_salary if max_salary > 0 else None,
        }
        if _save_profile({"preferences": prefs}, profile.get("id") if profile else None):
            st.success("Preferences saved!")
            st.cache_data.clear()
