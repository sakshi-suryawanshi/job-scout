import streamlit as st
import json
import os

st.set_page_config(page_title="Settings — Job Scout", page_icon="⚙️", layout="wide")

_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "boards_config.json",
)

# ── Board registry (moved from 6_Boards.py) ──────────────────────────────────
ALL_BOARDS = {
    "remoteok":             ("RemoteOK",              "Large boards",       "~100 jobs/day. remoteok.com JSON API.", True),
    "remotive":             ("Remotive (software)",   "Large boards",       "~200 jobs. remotive.com API, software-dev.", True),
    "remotive_devops":      ("Remotive DevOps",        "Large boards",       "remotive.com devops-sysadmin category.", False),
    "remotive_data":        ("Remotive Data",          "Large boards",       "remotive.com data category.", False),
    "weworkremotely":       ("WeWorkRemotely",         "Large boards",       "RSS — backend/fullstack/devops.", True),
    "wwr_devops":           ("WWR DevOps",             "Large boards",       "WeWorkRemotely devops RSS.", False),
    "wwr_frontend":         ("WWR Frontend",           "Large boards",       "WeWorkRemotely frontend RSS.", False),
    "himalayas":            ("Himalayas",              "Large boards",       "~100 jobs. Remote-only, salary data.", True),
    "arbeitnow":            ("Arbeitnow",              "Large boards",       "~100 jobs. EU + worldwide remote.", True),
    "themuse":              ("The Muse",               "Large boards",       "~100 jobs. Startup/mid-size.", True),
    "justjoin":             ("JustJoin.it",            "Large boards",       "EU tech. Many globally remote.", True),
    "hackernews":           ("HN Who's Hiring",        "Communities",        "Monthly Ask HN threads. YC + startups.", True),
    "hackernews_jobs":      ("HN Job Stories",         "Communities",        "HN /jobstories — YC company jobs.", True),
    "reddit":               ("Reddit r/forhire",       "Communities",        "r/forhire [Hiring] posts.", False),
    "reddit_remotejs":      ("Reddit r/remotejs",      "Communities",        "r/remotejs JS-focused hiring.", False),
    "jobicy":               ("Jobicy",                 "Low competition",    "~50 jobs. Small board, best odds.", True),
    "jobicy_all":           ("Jobicy (all eng)",       "Low competition",    "Jobicy with no category filter.", True),
    "workingnomads":        ("WorkingNomads",          "Low competition",    "~100 jobs. Remote-only dev.", True),
    "workingnomads_devops": ("WorkingNomads DevOps",   "Low competition",    "WorkingNomads devops-sysadmin.", False),
    "jobspresso":           ("Jobspresso",             "Low competition",    "~50 curated remote jobs.", True),
    "wfhio":                ("WFH.io",                 "Low competition",    "~60 jobs. Niche remote board.", True),
    "remoteco":             ("Remote.co",              "Low competition",    "Curated remote jobs RSS.", True),
    "authenticjobs":        ("Authentic Jobs",         "Low competition",    "Web/dev/design jobs RSS.", True),
    "nodesk":               ("NodeDesk",               "Low competition",    "Very small curated remote board.", True),
    "4dayweek":             ("4DayWeek.io",            "Low competition",    "4-day week remote jobs. Ultra-niche.", True),
    "dynamitejobs":         ("Dynamite Jobs",          "Low competition",    "Remote entrepreneur-focused jobs.", True),
    "freshremote":          ("Fresh Remote",           "Low competition",    "Remote-focused aggregator.", True),
    "remotefirstjobs":      ("Remote First Jobs",      "Low competition",    "Only remote-first companies.", True),
    "devitjobs":            ("DevITjobs EU",           "Low competition",    "EU developer jobs with salary.", True),
    "djangojobs":           ("DjangoJobs.net",         "Tech niche",         "Python/Django only. Near-zero competition.", True),
    "golangjobs":           ("GolangJobs.xyz",         "Tech niche",         "Go/Golang only. Small, RSS.", True),
    "larajobs":             ("LaraJobs.com",           "Tech niche",         "PHP/Laravel. Niche = fewer applicants.", False),
    "vuejobs":              ("VueJobs.com",            "Tech niche",         "Vue.js developer jobs.", False),
    "smashingmag":          ("Smashing Mag Jobs",      "Tech niche",         "Frontend/dev jobs RSS.", False),
    "cryptojobslist":       ("CryptoJobsList",         "Startup niche",      "Web3/blockchain startups. Remote-first.", False),
    "web3career":           ("Web3.career",            "Startup niche",      "Blockchain developer jobs RSS.", False),
    "climatebase":          ("ClimateBase",            "Startup niche",      "Climate tech startups. Often urgent.", False),
    "powertofly":           ("PowerToFly",             "Startup niche",      "Inclusive remote tech hiring.", False),
    "cord":                 ("Cord.co",                "Salary transparent", "UK/global startup jobs. Salary always shown.", True),
    "wellfound":            ("Wellfound",              "Salary transparent", "Startup-only. Salary shown. ATS verified.", True),
    "hired":                ("Hired.com",              "Salary transparent", "Salary-first marketplace.", True),
    "talentio":             ("Talent.io",              "Salary transparent", "EU tech jobs. Salary upfront.", True),
    "pallet":               ("Pallet Boards",          "Salary transparent", "Hundreds of indie startup job boards.", True),
}


def _load_cfg() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cfg(enabled: set):
    data = {"enabled_boards": sorted(enabled)}
    try:
        os.makedirs(os.path.dirname(_CONFIG_FILE), exist_ok=True)
        with open(_CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        st.error(f"Could not save: {e}")


st.title("⚙️ Settings")

tab_boards, tab_keys, tab_about = st.tabs(["🗂️ Boards", "🔑 API Keys", "ℹ️ About"])


# ── Boards ────────────────────────────────────────────────────────────────────
with tab_boards:
    st.subheader("Job Board Manager")
    st.caption("Choose which boards are scraped by default. Changes persist to data/boards_config.json.")

    cfg = _load_cfg()
    currently_enabled = (
        set(cfg["enabled_boards"])
        if "enabled_boards" in cfg
        else {k for k, (_, _, _, d) in ALL_BOARDS.items() if d}
    )

    qc1, qc2, qc3, qc4 = st.columns(4)
    with qc1:
        if st.button("✅ Enable all"):
            st.session_state["boards_pending"] = set(ALL_BOARDS.keys())
            st.rerun()
    with qc2:
        if st.button("❌ Disable all"):
            st.session_state["boards_pending"] = set()
            st.rerun()
    with qc3:
        if st.button("🎯 Defaults"):
            st.session_state["boards_pending"] = {k for k, (_, _, _, d) in ALL_BOARDS.items() if d}
            st.rerun()
    with qc4:
        if st.button("💡 Low-competition only"):
            st.session_state["boards_pending"] = {k for k, (_, cat, _, _) in ALL_BOARDS.items()
                                                    if cat in ("Low competition", "Tech niche", "Communities")}
            st.rerun()

    working = st.session_state.get("boards_pending", currently_enabled).copy()
    st.info(f"**{len(working)} of {len(ALL_BOARDS)}** boards currently selected.")

    categories: dict = {}
    for key, (name, cat, desc, _) in ALL_BOARDS.items():
        categories.setdefault(cat, []).append(key)

    new_enabled: set = set()
    for cat, keys in categories.items():
        enabled_count = sum(1 for k in keys if k in working)
        st.subheader(f"{cat}  ({enabled_count}/{len(keys)})")
        for key in keys:
            name, _, desc, _ = ALL_BOARDS[key]
            rc1, rc2, rc3 = st.columns([1, 2, 5])
            with rc1:
                checked = st.checkbox("", value=(key in working), key=f"brd_{key}", label_visibility="collapsed")
            with rc2:
                st.write(f"**{name}**")
            with rc3:
                st.caption(desc)
            if checked:
                new_enabled.add(key)
        st.divider()

    save_col, info_col = st.columns([1, 3])
    with save_col:
        if st.button("💾 Save", use_container_width=True, type="primary"):
            _save_cfg(new_enabled)
            st.session_state.pop("boards_pending", None)
            st.success(f"Saved! {len(new_enabled)} boards enabled.")
            st.rerun()
    with info_col:
        removed = currently_enabled - new_enabled
        added = new_enabled - currently_enabled
        if removed:
            st.warning(f"Will disable: {', '.join(sorted(removed))}")
        if added:
            st.info(f"Will enable: {', '.join(sorted(added))}")
        if not removed and not added:
            st.caption("No changes pending.")


# ── API Keys ──────────────────────────────────────────────────────────────────
with tab_keys:
    st.subheader("API Keys")
    st.caption("All keys are read from `.env` or Streamlit secrets. Never stored in DB. Shown masked.")

    def _key_status(env_var: str, label: str, link: str):
        val = os.getenv(env_var, "")
        try:
            val = val or st.secrets.get(env_var, "")
        except Exception:
            pass
        if val and val not in ("your_key_here", f"your_{env_var.lower()}_here"):
            st.success(f"**{label}**: ✅ Set (`{val[:6]}…`)")
        else:
            st.error(f"**{label}**: ❌ Not set — [Get free key]({link})")

    _key_status("SUPABASE_URL", "Supabase URL", "https://supabase.com")
    _key_status("SUPABASE_KEY", "Supabase anon key", "https://supabase.com")
    _key_status("GEMINI_API_KEY", "Gemini API key (1500 req/day free)", "https://aistudio.google.com/app/apikey")
    _key_status("SERPER_API_KEY", "Serper.dev key (2500 searches/month free)", "https://serper.dev")

    st.divider()
    st.caption("To set keys: add them to your `.env` file or Streamlit Cloud secrets (`Manage app → Secrets`).")


# ── About ─────────────────────────────────────────────────────────────────────
with tab_about:
    st.subheader("About Job Scout V2")
    st.markdown("""
**Job Scout** is an open-source AI-powered job search tool built for remote software engineers.

**Stack:** Streamlit · Supabase (PostgREST) · Gemini 2.0 Flash · Serper.dev

**V2 features:**
- 40+ job boards scraped in parallel
- ATS direct scraping (Greenhouse, Lever, Ashby)
- Google dorking via Serper.dev (LinkedIn, Indeed, hidden gems)
- AI job scoring + resume tailoring (Gemini)
- Desperation signal detection
- Application tracking + follow-up reminders
- Daily automated pipeline (coming soon)

**Free tier only.** Zero paid services required.
""")
