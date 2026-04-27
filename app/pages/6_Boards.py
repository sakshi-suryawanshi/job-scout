import streamlit as st
import json
import os

st.set_page_config(page_title="Board Manager", page_icon="🗂️", layout="wide")

st.title("🗂️ Board Manager")
st.markdown("Enable or disable job boards. Disabled boards are skipped during scraping.")

# ── Config file (volume-mounted so persists across rebuilds) ─────────────────
_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "boards_config.json",
)

# ── Master board registry ─────────────────────────────────────────────────────
# key → (display_name, category, description, default_on)
ALL_BOARDS = {
    # ── Large / popular boards ────────────────────────────────────────────────
    "remoteok":          ("RemoteOK",              "Large boards",    "~100 jobs/day. remoteok.com JSON API. High volume, high competition.", True),
    "remotive":          ("Remotive (software)",   "Large boards",    "~200 jobs. remotive.com API, software-dev category.", True),
    "remotive_devops":   ("Remotive (DevOps)",     "Large boards",    "remotive.com devops-sysadmin category.", False),
    "remotive_data":     ("Remotive (Data)",       "Large boards",    "remotive.com data category.", False),
    "weworkremotely":    ("WeWorkRemotely",        "Large boards",    "RSS feed — backend/fullstack/devops. Medium competition.", True),
    "wwr_devops":        ("WWR DevOps",            "Large boards",    "WeWorkRemotely devops/sysadmin RSS feed.", False),
    "wwr_frontend":      ("WWR Frontend",          "Large boards",    "WeWorkRemotely front-end RSS feed.", False),
    "himalayas":         ("Himalayas",             "Large boards",    "~100 jobs. himalayas.app JSON API. Remote-only, includes salary data.", True),
    "arbeitnow":         ("Arbeitnow",             "Large boards",    "~100 jobs. EU + worldwide remote. Free JSON API.", True),
    "themuse":           ("The Muse",              "Large boards",    "~100 jobs. Startup/mid-size focus. Free public API.", True),
    "justjoin":          ("JustJoin.it",           "Large boards",    "Biggest EU tech board. Many roles are globally remote. Free API.", True),

    # ── Hacker News / communities ─────────────────────────────────────────────
    "hackernews":        ("HN Who's Hiring",       "Communities",     "Monthly 'Ask HN: Who is hiring?' threads via Algolia API. YC + startups.", True),
    "hackernews_jobs":   ("HN Job Stories",        "Communities",     "HN /jobstories Firebase feed — YC company job posts.", True),
    "reddit":            ("Reddit r/forhire",      "Communities",     "Reddit r/forhire [Hiring] posts. Variable quality.", False),
    "reddit_remotejs":   ("Reddit r/remotejs",     "Communities",     "Reddit r/remotejs hiring posts. JavaScript-focused.", False),

    # ── Low-competition curated boards ────────────────────────────────────────
    "jobicy":            ("Jobicy",                "Low competition", "~50 jobs. Small board. Free API with geo/industry filter. Best odds.", True),
    "jobicy_all":        ("Jobicy (all eng)",      "Low competition", "Jobicy with no category filter — catches broader engineering roles.", True),
    "workingnomads":     ("WorkingNomads",         "Low competition", "~100 jobs. Free REST API. Remote-only. Development category.", True),
    "workingnomads_devops": ("WorkingNomads DevOps","Low competition","WorkingNomads devops-sysadmin category.", False),
    "jobspresso":        ("Jobspresso",            "Low competition", "~50 curated remote jobs. WordPress RSS. Very low applicant pool.", True),
    "wfhio":             ("WFH.io",                "Low competition", "~60 jobs. Free JSON API. Niche remote board. Minimal competition.", True),
    "remoteco":          ("Remote.co",             "Low competition", "Curated remote jobs. RSS feed. Smaller audience than RemoteOK.", True),
    "authenticjobs":     ("Authentic Jobs",        "Low competition", "Web/dev/design jobs RSS. 15+ years old, loyal small audience.", True),
    "nodesk":            ("NodeDesk",              "Low competition", "Very small curated remote board. RSS. Tiny applicant pool.", True),
    "4dayweek":          ("4DayWeek.io",           "Low competition", "4-day work week remote jobs. Ultra-niche. Almost no competition.", True),
    "dynamitejobs":      ("Dynamite Jobs",         "Low competition", "Remote/location-independent jobs. Entrepreneur-focused. RSS.", True),
    "freshremote":       ("Fresh Remote",          "Low competition", "Remote-focused aggregator. RSS feed. Smaller audience.", True),
    "remotefirstjobs":   ("Remote First Jobs",     "Low competition", "Only companies that are remote-first by policy.", True),
    "devitjobs":         ("DevITjobs EU",          "Low competition", "EU developer jobs with salary data. Free JSON API. Many globally remote.", True),

    # ── Tech-specific niche ───────────────────────────────────────────────────
    "djangojobs":        ("DjangoJobs.net",        "Tech niche",      "Python/Django only. Very small board. Near-zero competition.", True),
    "golangjobs":        ("GolangJobs.xyz",        "Tech niche",      "Go/Golang only. Small. RSS feed.", True),
    "larajobs":          ("LaraJobs.com",          "Tech niche",      "PHP/Laravel ecosystem. RSS. Niche = fewer applicants.", False),
    "vuejobs":           ("VueJobs.com",           "Tech niche",      "Vue.js developer jobs. RSS/Atom. JS-specific.", False),
    "smashingmag":       ("Smashing Mag Jobs",     "Tech niche",      "Frontend/design/dev jobs. RSS. Quality companies.", False),

    # ── Startup / mission-driven ──────────────────────────────────────────────
    "cryptojobslist":    ("CryptoJobsList",        "Startup niche",   "Web3/blockchain startups. Remote-first. Small teams. Desperate to hire.", False),
    "web3career":        ("Web3.career",           "Startup niche",   "Blockchain/crypto developer jobs. RSS. Many small startups.", False),
    "climatebase":       ("ClimateBase",           "Startup niche",   "Climate tech startups. Mission-driven. Remote. Often urgent hiring.", False),
    "powertofly":        ("PowerToFly",            "Startup niche",   "Inclusive remote tech hiring. RSS. Mid-size companies.", False),
    # ── Salary-transparent / low-fraud ────────────────────────────────────────
    "cord":              ("Cord.co",               "Salary transparent", "UK/global startup jobs. Salary always shown. Verified companies only.", True),
    "wellfound":         ("Wellfound",             "Salary transparent", "Startup-only job board. Salary shown. ATS verified. AngelList successor.", True),
    "hired":             ("Hired.com",             "Salary transparent", "Salary-first marketplace. $40-80k focus. Companies apply to you.", True),
    "talentio":          ("Talent.io",             "Salary transparent", "EU tech jobs. Salary always upfront. Vetted companies.", True),
    "pallet":            ("Pallet Boards",         "Salary transparent", "Hundreds of indie startup job boards. Very small audiences.", True),
}


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(enabled: set):
    data = {"enabled_boards": sorted(enabled)}
    try:
        os.makedirs(os.path.dirname(_CONFIG_FILE), exist_ok=True)
        with open(_CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        st.error(f"Could not save config: {e}")


def get_enabled_boards() -> list:
    """Return list of enabled board keys. Called by scraping pipeline."""
    cfg = _load_config()
    if "enabled_boards" in cfg:
        return cfg["enabled_boards"]
    # Default: return all boards that are default_on=True
    return [k for k, (_, _, _, default) in ALL_BOARDS.items() if default]


# ── Load current config ───────────────────────────────────────────────────────
cfg = _load_config()
if "enabled_boards" in cfg:
    currently_enabled = set(cfg["enabled_boards"])
else:
    currently_enabled = {k for k, (_, _, _, default) in ALL_BOARDS.items() if default}

st.info(f"**{len(currently_enabled)} boards currently enabled** out of {len(ALL_BOARDS)} total. Uncheck boards you don't want, then click Save.")

# ── Quick actions ─────────────────────────────────────────────────────────────
qcol1, qcol2, qcol3, qcol4 = st.columns(4)
with qcol1:
    if st.button("✅ Enable all", use_container_width=True):
        st.session_state["pending"] = set(ALL_BOARDS.keys())
        st.rerun()
with qcol2:
    if st.button("❌ Disable all", use_container_width=True):
        st.session_state["pending"] = set()
        st.rerun()
with qcol3:
    if st.button("🎯 Defaults (recommended)", use_container_width=True):
        st.session_state["pending"] = {k for k, (_, _, _, d) in ALL_BOARDS.items() if d}
        st.rerun()
with qcol4:
    if st.button("💡 Low-competition only", use_container_width=True):
        st.session_state["pending"] = {
            k for k, (_, cat, _, _) in ALL_BOARDS.items()
            if cat in ("Low competition", "Tech niche", "Communities")
        }
        st.rerun()

working_set = st.session_state.get("pending", currently_enabled).copy()

st.divider()

# ── Board table grouped by category ──────────────────────────────────────────
categories = {}
for key, (name, cat, desc, _) in ALL_BOARDS.items():
    categories.setdefault(cat, []).append(key)

new_enabled = set()

for cat, keys in categories.items():
    cat_enabled = sum(1 for k in keys if k in working_set)
    st.subheader(f"{cat}  ({cat_enabled}/{len(keys)} enabled)")

    # Column headers
    hcol1, hcol2, hcol3 = st.columns([1, 2, 5])
    with hcol1: st.caption("Enable")
    with hcol2: st.caption("Board")
    with hcol3: st.caption("Description")

    for key in keys:
        name, _, desc, _ = ALL_BOARDS[key]
        rcol1, rcol2, rcol3 = st.columns([1, 2, 5])
        with rcol1:
            checked = st.checkbox("", value=(key in working_set), key=f"board_{key}", label_visibility="collapsed")
        with rcol2:
            st.write(f"**{name}**")
        with rcol3:
            st.caption(desc)
        if checked:
            new_enabled.add(key)

    st.divider()

# ── Save button ───────────────────────────────────────────────────────────────
save_col, stat_col = st.columns([1, 3])
with save_col:
    if st.button("💾 Save Board Config", use_container_width=True, type="primary"):
        _save_config(new_enabled)
        # Clear pending
        st.session_state.pop("pending", None)
        st.success(f"Saved! {len(new_enabled)} boards enabled, {len(ALL_BOARDS) - len(new_enabled)} disabled.")
        st.rerun()

with stat_col:
    removed = currently_enabled - new_enabled
    added = new_enabled - currently_enabled
    if removed:
        st.warning(f"Will disable: {', '.join(sorted(removed))}")
    if added:
        st.info(f"Will enable: {', '.join(sorted(added))}")
    if not removed and not added:
        st.caption("No changes pending.")
