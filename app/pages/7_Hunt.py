import streamlit as st
import os
import sys
import re
from urllib.parse import urlparse

st.set_page_config(page_title="Career Hunt", page_icon="🕵️", layout="wide")

st.title("🕵️ Career Page Hunter")
st.markdown(
    "Find companies that **don't post on big job boards** — "
    "unknown startups, niche B2B SaaS, indie companies. "
    "Discover their career pages via Google, then scrape jobs directly."
)

# DB
try:
    from db import get_db
    db = get_db()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# Serper
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "worker", "discovery"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "worker", "scraping"))

try:
    from serper_dorking import SerperDorker
    _serper_key = os.getenv("SERPER_API_KEY", "")
    try:
        _serper_key = _serper_key or st.secrets.get("SERPER_API_KEY", "")
    except Exception:
        pass
    SERPER_AVAILABLE = bool(_serper_key)
except ImportError:
    SERPER_AVAILABLE = False

# Career scraper
try:
    from career_scraper import CareerPageScraper
    from board_scrapers import matches_criteria, to_db_job
    SCRAPER_AVAILABLE = True
except ImportError:
    SCRAPER_AVAILABLE = False


# ─── Query builder for unknown career pages ───────────────────────────────────

def _build_career_hunt_queries(tech: str, role: str, extra: str) -> list[dict]:
    """
    Build Serper queries targeting unknown company career pages —
    explicitly excluding major job boards and ATS platforms so we only
    surface companies that post only on their own site.
    """
    excl = "-site:linkedin.com -site:indeed.com -site:glassdoor.com -site:lever.co -site:greenhouse.io -site:ashbyhq.com -site:wellfound.com -site:linkedin.com/jobs"
    role_q = role or "engineer OR developer"
    tech_q = f'"{tech}"' if tech else ""
    extra_q = extra or ""

    queries = [
        {
            "label": "Career pages (no ATS, no job boards)",
            "q": f'intitle:"careers" OR intitle:"join us" "remote" {role_q} {tech_q} {extra_q} {excl}',
        },
        {
            "label": "\"We're hiring\" posts (direct company)",
            "q": f'"we\'re hiring" OR "we are hiring" "remote" {role_q} {tech_q} {extra_q} {excl}',
        },
        {
            "label": "Open positions pages",
            "q": f'intitle:"open positions" OR intitle:"open roles" "remote" {role_q} {tech_q} {extra_q} {excl}',
        },
        {
            "label": ".io domain startups hiring",
            "q": f'site:.io intitle:"careers" "remote" {role_q} {tech_q} {extra_q} -linkedin -indeed',
        },
        {
            "label": "Small team hiring pages",
            "q": f'"small team" OR "tiny team" "remote" {role_q} {tech_q} "hiring" {extra_q} {excl}',
        },
        {
            "label": "Startup job pages (no aggregators)",
            "q": f'"startup" "remote" "hiring" {role_q} {tech_q} {extra_q} {excl} -remotive -remoteok -weworkremotely',
        },
        {
            "label": "B2B SaaS companies hiring remotely",
            "q": f'"saas" "remote" "engineer" {tech_q} "hiring" {extra_q} {excl}',
        },
        {
            "label": "Developer tool companies (GitHub-active)",
            "q": f'site:github.com "we are hiring" OR "join our team" "remote" {role_q} {tech_q}',
        },
    ]
    return queries


def _extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc.replace("www.", "")
    except Exception:
        return url


def _guess_career_url(domain: str) -> str:
    """Best-guess career URL for a domain."""
    return f"https://{domain}/careers"


def _extract_company_name(result: dict) -> str:
    """Try to extract company name from Serper result."""
    title = result.get("title", "")
    snippet = result.get("snippet", "")
    url = result.get("link", "")
    domain = _extract_domain(url)

    # Try stripping common suffixes from title: "Careers | CompanyName"
    for sep in [" | ", " - ", " – ", " — ", " · "]:
        if sep in title:
            parts = title.split(sep)
            # Last non-generic part is usually the company
            for p in reversed(parts):
                p = p.strip()
                if p.lower() not in ("careers", "jobs", "hiring", "join us", "open positions", "work with us"):
                    return p

    # Fall back to domain slug
    name = domain.split(".")[0].replace("-", " ").replace("_", " ").title()
    return name


# ─── TABS ──────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["🔍 Hunt Career Pages", "🤖 Scrape & Import Jobs"])


# ─── TAB 1: HUNT ──────────────────────────────────────────────────────────────
with tab1:
    if not SERPER_AVAILABLE:
        st.warning("SERPER_API_KEY not set — needed to hunt career pages via Google.")
        st.code("# .env\nSERPER_API_KEY=your_key_here", language="bash")
        st.stop()

    st.subheader("Search for Unknown Company Career Pages")
    st.caption(
        "Targets companies that don't use Greenhouse/Lever/Ashby and don't post on LinkedIn/Indeed. "
        "Results are their own /careers pages."
    )

    hcol1, hcol2, hcol3 = st.columns(3)
    with hcol1:
        hunt_tech = st.text_input(
            "Tech stack focus",
            placeholder="python, fastapi, react",
            help="Tech keywords to narrow results",
        )
    with hcol2:
        hunt_role = st.text_input(
            "Role type",
            value="engineer OR developer",
            help='e.g. "backend engineer" or "fullstack developer"',
        )
    with hcol3:
        hunt_extra = st.text_input(
            "Extra filters (optional)",
            placeholder='"seed" OR "series a"',
            help="Additional Google search terms",
        )

    hcol4, hcol5 = st.columns(2)
    with hcol4:
        hunt_results_per = st.slider("Results per query", 5, 20, 10)
    with hcol5:
        max_hunt_queries = st.slider("Max queries to run", 1, 8, 4)

    queries = _build_career_hunt_queries(hunt_tech, hunt_role, hunt_extra)

    st.markdown(f"**{len(queries[:max_hunt_queries])} queries ready** — each uses 1 Serper credit")
    with st.expander("Preview queries"):
        for q in queries[:max_hunt_queries]:
            st.caption(f"**{q['label']}**")
            st.code(q["q"], language="text")

    if st.button("🕵️ Hunt Career Pages", use_container_width=True, type="primary"):
        dorker = SerperDorker(_serper_key)
        discovered = {}  # domain -> {company_name, career_url, snippet, source_label}

        prog = st.progress(0)
        status = st.empty()

        for i, q_info in enumerate(queries[:max_hunt_queries]):
            status.write(f"Searching: **{q_info['label']}**...")
            prog.progress(i / max_hunt_queries)

            results = dorker.search(q_info["q"], num_results=hunt_results_per)
            for r in results:
                url = r.get("link", "")
                if not url:
                    continue
                domain = _extract_domain(url)
                if not domain or domain in discovered:
                    continue
                # Skip known job board domains
                skip_domains = {
                    "linkedin.com", "indeed.com", "glassdoor.com", "lever.co",
                    "greenhouse.io", "ashbyhq.com", "wellfound.com", "remoteok.com",
                    "remotive.com", "weworkremotely.com", "himalayas.app",
                    "jobicy.com", "arbeitnow.com", "themuse.com", "workingnomads.com",
                    "jobspresso.co", "wfh.io", "hackernews.com", "reddit.com",
                    "x.com", "twitter.com", "github.com",
                }
                if any(skip in domain for skip in skip_domains):
                    continue

                company_name = _extract_company_name(r)
                # Guess career URL: prefer the actual URL if it looks like a career page
                career_url = url
                path = urlparse(url).path.lower()
                if not any(kw in path for kw in ["/careers", "/jobs", "/hiring", "/positions", "/roles", "/openings"]):
                    career_url = _guess_career_url(domain)

                discovered[domain] = {
                    "company_name": company_name,
                    "career_url": career_url,
                    "domain": domain,
                    "snippet": r.get("snippet", "")[:200],
                    "source_label": q_info["label"],
                }

        prog.progress(1.0)
        status.write(f"✅ Done — {len(discovered)} unique companies found ({dorker.queries_used} queries used)")

        st.session_state["hunt_results"] = list(discovered.values())

    # Show results
    if "hunt_results" in st.session_state and st.session_state["hunt_results"]:
        results_list = st.session_state["hunt_results"]
        st.divider()
        st.subheader(f"{len(results_list)} Unknown Companies Found")
        st.caption("These companies post jobs only on their own websites — low competition!")

        # Already in DB?
        existing_companies = db.get_companies(active_only=False, limit=10000)
        existing_domains = set()
        for c in existing_companies:
            site = c.get("website", "") or c.get("career_url", "") or ""
            if site:
                existing_domains.add(_extract_domain(site))

        new_count = sum(1 for r in results_list if r["domain"] not in existing_domains)
        if new_count < len(results_list):
            st.info(f"{len(results_list) - new_count} already in your DB. {new_count} are new.")

        # Table
        import pandas as pd
        df_data = []
        for r in results_list:
            in_db = r["domain"] in existing_domains
            df_data.append({
                "Company": r["company_name"],
                "Career URL": r["career_url"],
                "In DB": "✅" if in_db else "🆕",
                "Found via": r["source_label"][:40],
                "Snippet": r["snippet"][:80],
            })
        st.dataframe(pd.DataFrame(df_data), use_container_width=True, hide_index=True)

        st.divider()
        icol1, icol2 = st.columns(2)
        with icol1:
            if st.button(
                f"💾 Import all {new_count} new companies to DB",
                use_container_width=True,
                type="primary",
                disabled=new_count == 0,
            ):
                imported = 0
                for r in results_list:
                    if r["domain"] not in existing_domains:
                        cid = db.find_or_create_company(r["company_name"], defaults={
                            "career_url": r["career_url"],
                            "website": f"https://{r['domain']}",
                            "source": "career_hunt",
                            "ats_type": "unknown",
                            "is_active": True,
                            "priority_score": 8,
                        })
                        if cid:
                            imported += 1
                st.success(f"✅ Imported {imported} companies! Head to **Scrape & Import Jobs** tab to pull their jobs.")
                st.session_state.pop("hunt_results", None)
                st.rerun()

        with icol2:
            if st.button("🗑️ Clear results", use_container_width=True):
                st.session_state.pop("hunt_results", None)
                st.rerun()


# ─── TAB 2: SCRAPE & IMPORT JOBS ──────────────────────────────────────────────
with tab2:
    st.subheader("Scrape Career Pages → Import Jobs")
    st.markdown(
        "Pull job listings directly from the career pages of companies tagged `career_hunt` in your DB. "
        "These are the hidden-gem companies discovered above."
    )

    if not SCRAPER_AVAILABLE:
        st.error("Career scraper not available — check imports.")
        st.stop()

    # Fetch hunt companies
    try:
        all_cos = db.get_companies(active_only=True, limit=5000)
        hunt_cos = [c for c in all_cos if c.get("source") == "career_hunt" and c.get("career_url")]
    except Exception as e:
        st.error(f"DB error: {e}")
        hunt_cos = []

    st.metric("Companies to scrape", len(hunt_cos))

    if not hunt_cos:
        st.info(
            "No career-hunt companies yet. Use the **Hunt Career Pages** tab to discover them first, "
            "then import them to your DB."
        )
    else:
        scol1, scol2, scol3 = st.columns(3)
        with scol1:
            max_to_scrape = st.slider("Max companies to scrape", 5, min(100, len(hunt_cos)), min(20, len(hunt_cos)))
        with scol2:
            remote_only_hunt = st.checkbox("Remote jobs only", value=True, key="hunt_remote")
        with scol3:
            hunt_title_kws = st.text_input(
                "Title keywords filter",
                value="engineer, developer, backend, fullstack",
                key="hunt_kws",
            )

        criteria = {
            "title_keywords": [k.strip() for k in hunt_title_kws.split(",") if k.strip()],
            "required_skills": [],
            "exclude_keywords": ["staff", "principal", "director", "vp", "head of", "manager"],
            "remote_only": remote_only_hunt,
            "max_yoe": 6,
        }

        if st.button("🚀 Scrape Career Pages & Import Jobs", use_container_width=True, type="primary"):
            scraper = CareerPageScraper()
            prog2 = st.progress(0)
            status2 = st.empty()
            total_saved = 0
            targets = hunt_cos[:max_to_scrape]

            for i, company in enumerate(targets):
                name = company.get("name", "Unknown")
                career_url = company.get("career_url", "")
                status2.write(f"Scraping **{name}** — {career_url}")
                prog2.progress(i / len(targets))

                try:
                    raw_jobs = scraper.scrape_company(career_url, name)
                    matching = [j for j in raw_jobs if matches_criteria(j, criteria)]

                    for job in matching:
                        db_job = to_db_job(job, company.get("id"))
                        if db.upsert_job(db_job):
                            total_saved += 1

                except Exception as e:
                    st.caption(f"  ⚠️ {name}: {e}")

            prog2.progress(1.0)
            status2.write(f"✅ Done! Saved **{total_saved}** new jobs from {len(targets)} career pages.")
            if total_saved > 0:
                st.success(f"Imported {total_saved} jobs. Go to Search → Browse Jobs to see them (filter Source = career_page).")
                st.balloons()

    # Also show a summary of all sources in DB
    st.divider()
    st.subheader("All Career-Hunt Companies in DB")
    try:
        if hunt_cos:
            import pandas as pd
            st.dataframe(pd.DataFrame([{
                "Company": c.get("name"),
                "Career URL": c.get("career_url", ""),
                "Active": c.get("is_active", True),
            } for c in hunt_cos]), use_container_width=True, hide_index=True)
        else:
            st.info("None yet.")
    except Exception:
        pass


# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
try:
    all_co = db.get_companies(active_only=False, limit=10000)
    hunt_count = len([c for c in all_co if c.get("source") == "career_hunt"])
    st.sidebar.divider()
    st.sidebar.subheader("🕵️ Career Hunt Stats")
    st.sidebar.metric("Hunt Companies in DB", hunt_count)

    if SERPER_AVAILABLE:
        try:
            from serper_dorking import get_serper_usage
            u = get_serper_usage()
            st.sidebar.caption(f"Serper: {u['calls_this_month']}/{u['limit']} used this month")
        except Exception:
            pass
except Exception:
    pass
