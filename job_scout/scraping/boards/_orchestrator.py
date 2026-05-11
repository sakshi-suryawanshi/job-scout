# job_scout/scraping/boards/_orchestrator.py
"""scrape_board_jobs: unified board scraping pipeline."""

import json
import os
from typing import List, Dict

from job_scout.scraping.base import to_db_job
from job_scout.enrichment.filters import matches_criteria

from job_scout.scraping.boards._api import (
    RemoteOKScraper, RemotiveScraper, HimalayasScraper, ArbeitnowScraper,
    JobicyScraper, TheMuseScraper, WorkingNomadsScraper, WFHioScraper,
    DevITJobsScraper, JustJoinScraper, FourDayWeekScraper, CryptoJobsListScraper,
    ClimateBaseScraper, RemoteFirstJobsScraper, Web3CareerScraper,
    RemotiveDevOpsScraper, RemotiveDataScraper, WorkingNomadsDevOpsScraper,
    JobicyAllScraper,
)
from job_scout.scraping.boards._rss import (
    WeWorkRemotelyScraper, JobspressoScraper,
    RemoteCo, AuthenticJobsScraper, DjangoJobsScraper, LaraJobsScraper,
    NodeDeskScraper, VueJobsScraper, GolangJobsScraper, DynamiteJobsScraper,
    SmashingMagJobsScraper, FreshRemoteScraper, PowerToFlyScraper,
    WWRDevOpsScraper, WWRFrontendScraper,
)
from job_scout.scraping.boards._community import HackerNewsScraper, RedditScraper
from job_scout.scraping.boards._salary import (
    CordScraper, WellfoundScraper, HiredScraper, TalentioScraper, PalletScraper,
)
from job_scout.scraping.boards._extra import (
    # Easy tier
    PythonOrgJobsScraper, BerlinStartupJobsScraper, SkipTheDriveScraper,
    PyJobsScraper, HiringCafeScraper, EchoJobsScraper, LandingJobsScraper,
    # Medium tier
    TheHubScraper, StartupJobsCZScraper, GermanTechJobsScraper,
    SwissDevJobsScraper, RelocateMeScraper, CryptocurrencyJobsCoScraper,
    DiversifyTechScraper, StartupSuchtScraper, JustRemoteScraper,
    DailyRemoteScraper, RemoteYeahScraper, RemoteBackendJobsScraper,
    RemoteFrontendJobsScraper, RealWorkFromAnywhereScraper, RemoteesScraper,
    OSSJobsScraper, JSPythonGoRemotelyScraper, BuiltInScraper,
    Remote100kScraper, TechHireScraper, JobanniScraper, FindJobsDevScraper,
    DevJobsProScraper, OneRemoteJobsScraper, JobsRemoteAIScraper,
    SlasifyScraper, PangianScraper,
)

_BOARDS_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "data", "boards_config.json",
)

_DEFAULT_BOARDS = {
    "remoteok", "remotive", "weworkremotely", "himalayas", "arbeitnow", "themuse",
    "justjoin", "hackernews", "hackernews_jobs", "jobicy", "jobicy_all",
    "workingnomads", "jobspresso", "wfhio", "remoteco", "authenticjobs", "nodesk",
    "4dayweek", "dynamitejobs", "freshremote", "remotefirstjobs", "devitjobs",
    "djangojobs", "golangjobs", "cord", "wellfound", "hired", "talentio", "pallet",
}

_DEFAULT_CRITERIA = {
    "title_keywords": ["backend", "developer", "engineer", "software", "python", "golang", "full stack", "fullstack"],
    "required_skills": [],
    "exclude_keywords": ["staff", "principal", "director", "vp", "head of", "lead architect"],
    "remote_only": True,
    "max_yoe": 5,
}


def _get_enabled_boards(all_keys: list) -> list:
    try:
        with open(_BOARDS_CONFIG_FILE) as f:
            cfg = json.load(f)
        enabled = cfg.get("enabled_boards")
        if enabled:
            return [k for k in enabled if k in all_keys]
    except Exception:
        pass
    return [k for k in all_keys if k in _DEFAULT_BOARDS]


def _all_boards_registry(criteria: Dict = None) -> dict:
    tags = (criteria or {}).get("title_keywords", [])
    return {
        "remoteok":             ("RemoteOK",             lambda: RemoteOKScraper().get_jobs(tags=tags or None)),
        "remotive":             ("Remotive",              lambda: RemotiveScraper().get_jobs(category="software-dev", limit=200)),
        "weworkremotely":       ("WeWorkRemotely",        lambda: WeWorkRemotelyScraper().get_jobs()),
        "hackernews":           ("HN Who's Hiring",       lambda: HackerNewsScraper().get_jobs(months=2)),
        "hackernews_jobs":      ("HN Job Stories",        lambda: HackerNewsScraper()._scrape_job_stories()),
        "reddit":               ("Reddit",                lambda: RedditScraper().get_jobs(limit_per_sub=50)),
        "himalayas":            ("Himalayas",             lambda: HimalayasScraper().get_jobs(limit=100)),
        "arbeitnow":            ("Arbeitnow",             lambda: ArbeitnowScraper().get_jobs(limit=100)),
        "jobicy":               ("Jobicy",                lambda: JobicyScraper().get_jobs(limit=50)),
        "themuse":              ("The Muse",              lambda: TheMuseScraper().get_jobs(limit=100)),
        "workingnomads":        ("WorkingNomads",         lambda: WorkingNomadsScraper().get_jobs(limit=100)),
        "jobspresso":           ("Jobspresso",            lambda: JobspressoScraper().get_jobs(limit=50)),
        "wfhio":                ("WFH.io",                lambda: WFHioScraper().get_jobs(limit=60)),
        "remoteco":             ("Remote.co",             lambda: RemoteCo().get_jobs()),
        "authenticjobs":        ("Authentic Jobs",        lambda: AuthenticJobsScraper().get_jobs()),
        "djangojobs":           ("DjangoJobs",            lambda: DjangoJobsScraper().get_jobs()),
        "larajobs":             ("LaraJobs",              lambda: LaraJobsScraper().get_jobs()),
        "nodesk":               ("NodeDesk",              lambda: NodeDeskScraper().get_jobs()),
        "4dayweek":             ("4DayWeek",              lambda: FourDayWeekScraper().get_jobs()),
        "vuejobs":              ("VueJobs",               lambda: VueJobsScraper().get_jobs()),
        "golangjobs":           ("GolangJobs",            lambda: GolangJobsScraper().get_jobs()),
        "dynamitejobs":         ("Dynamite Jobs",         lambda: DynamiteJobsScraper().get_jobs()),
        "smashingmag":          ("Smashing Mag Jobs",     lambda: SmashingMagJobsScraper().get_jobs()),
        "devitjobs":            ("DevITjobs EU",          lambda: DevITJobsScraper().get_jobs(limit=100)),
        "cryptojobslist":       ("CryptoJobsList",        lambda: CryptoJobsListScraper().get_jobs(limit=60)),
        "web3career":           ("Web3.career",           lambda: Web3CareerScraper().get_jobs()),
        "climatebase":          ("ClimateBase",           lambda: ClimateBaseScraper().get_jobs(limit=60)),
        "justjoin":             ("JustJoin.it",           lambda: JustJoinScraper().get_jobs(limit=100)),
        "remotive_devops":      ("Remotive DevOps",       lambda: RemotiveDevOpsScraper().get_jobs()),
        "remotive_data":        ("Remotive Data",         lambda: RemotiveDataScraper().get_jobs()),
        "workingnomads_devops": ("WorkingNomads DevOps",  lambda: WorkingNomadsDevOpsScraper().get_jobs()),
        "wwr_devops":           ("WWR DevOps",            lambda: WWRDevOpsScraper().get_jobs()),
        "wwr_frontend":         ("WWR Frontend",          lambda: WWRFrontendScraper().get_jobs()),
        "reddit_remotejs":      ("Reddit RemoteJS",       lambda: RedditScraper()._scrape_subreddit("remotejs", 50)),
        "jobicy_all":           ("Jobicy (all)",          lambda: JobicyAllScraper().get_jobs()),
        "freshremote":          ("Fresh Remote",          lambda: FreshRemoteScraper().get_jobs()),
        "powertofly":           ("PowerToFly",            lambda: PowerToFlyScraper().get_jobs()),
        "remotefirstjobs":      ("Remote First Jobs",     lambda: RemoteFirstJobsScraper().get_jobs()),
        "cord":                 ("Cord.co",               lambda: CordScraper().get_jobs(limit=100)),
        "wellfound":            ("Wellfound",             lambda: WellfoundScraper().get_jobs(limit=100)),
        "hired":                ("Hired.com",             lambda: HiredScraper().get_jobs(limit=80)),
        "talentio":             ("Talent.io",             lambda: TalentioScraper().get_jobs(limit=80)),
        "pallet":               ("Pallet Boards",         lambda: PalletScraper().get_jobs(limit=100)),

        # ── Tier 1: Easy (RSS / JSON) ────────────────────────────────
        "python_jobs":          ("Python.org Jobs",       lambda: PythonOrgJobsScraper().get_jobs()),
        "berlin_startup_jobs":  ("Berlin Startup Jobs",   lambda: BerlinStartupJobsScraper().get_jobs()),
        "skipthedrive":         ("SkipTheDrive",          lambda: SkipTheDriveScraper().get_jobs()),
        "pyjobs":               ("PyJobs",                lambda: PyJobsScraper().get_jobs()),
        "hiring_cafe":          ("Hiring.cafe",           lambda: HiringCafeScraper().get_jobs(limit=100)),
        "echojobs":             ("EchoJobs",              lambda: EchoJobsScraper().get_jobs(limit=100)),
        "landing_jobs":         ("Landing.jobs",          lambda: LandingJobsScraper().get_jobs(limit=100)),

        # ── Tier 2: Medium (probable RSS) ────────────────────────────
        "the_hub":              ("The Hub",               lambda: TheHubScraper().get_jobs()),
        "startupjobs_cz":       ("StartupJobs.com",       lambda: StartupJobsCZScraper().get_jobs()),
        "germantechjobs":       ("GermanTechJobs",        lambda: GermanTechJobsScraper().get_jobs()),
        "swissdevjobs":         ("SwissDev Jobs",         lambda: SwissDevJobsScraper().get_jobs()),
        "relocate_me":          ("Relocate.me",           lambda: RelocateMeScraper().get_jobs()),
        "cryptocurrencyjobs_co":("CryptocurrencyJobs.co", lambda: CryptocurrencyJobsCoScraper().get_jobs()),
        "diversify_tech":       ("Diversify Tech",        lambda: DiversifyTechScraper().get_jobs()),
        "startup_sucht":        ("Startup Sucht",         lambda: StartupSuchtScraper().get_jobs()),
        "justremote":           ("JustRemote",            lambda: JustRemoteScraper().get_jobs()),
        "dailyremote":          ("DailyRemote",           lambda: DailyRemoteScraper().get_jobs()),
        "remoteyeah":           ("RemoteYeah",            lambda: RemoteYeahScraper().get_jobs()),
        "remote_backend_jobs":  ("Remote Backend Jobs",   lambda: RemoteBackendJobsScraper().get_jobs()),
        "remote_frontend_jobs": ("Remote Frontend Jobs",  lambda: RemoteFrontendJobsScraper().get_jobs()),
        "realworkfromanywhere": ("Real Work From Anywhere", lambda: RealWorkFromAnywhereScraper().get_jobs()),
        "remotees":             ("Remotees",              lambda: RemoteesScraper().get_jobs()),
        "ossjobs":              ("OSSJobs.dev",           lambda: OSSJobsScraper().get_jobs()),
        "js_python_go_remotely":("JS/Python/Go Remotely", lambda: JSPythonGoRemotelyScraper().get_jobs()),
        "builtin":              ("Built In",              lambda: BuiltInScraper().get_jobs()),
        "remote100k":           ("Remote100k",            lambda: Remote100kScraper().get_jobs()),
        "techhire":             ("TechHire.ai",           lambda: TechHireScraper().get_jobs()),
        "jobanni":              ("Jobanni",               lambda: JobanniScraper().get_jobs()),
        "findjobs_dev":         ("findjobs.dev",          lambda: FindJobsDevScraper().get_jobs()),
        "devjobs_pro":          ("DevJobs.pro",           lambda: DevJobsProScraper().get_jobs()),
        "oneremotejobs":        ("OneRemoteJobs",         lambda: OneRemoteJobsScraper().get_jobs()),
        "jobsremote_ai":        ("JobsRemote.ai",         lambda: JobsRemoteAIScraper().get_jobs()),
        "slasify":              ("Slasify",               lambda: SlasifyScraper().get_jobs()),
        "pangian":              ("Pangian",               lambda: PangianScraper().get_jobs()),
    }


_MAX_FETCH_WORKERS = 10  # concurrent HTTP fetches


def scrape_board_jobs(
    db,
    boards: List[str] = None,
    criteria: Dict = None,
    progress_callback=None,
) -> Dict:
    """
    Scrape jobs from all job boards, filter, save to DB.
    Fetches boards in parallel (up to _MAX_FETCH_WORKERS at once) then
    saves results serially so DB access is single-threaded.
    Returns {"total_scraped", "matched", "saved", "errors", "by_board"}.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if criteria is None:
        criteria = _DEFAULT_CRITERIA

    all_boards = _all_boards_registry(criteria)

    if boards is None:
        boards = _get_enabled_boards(list(all_boards.keys()))

    active = [(k, all_boards[k][0], all_boards[k][1]) for k in boards if k in all_boards]
    stats = {"total_scraped": 0, "matched": 0, "saved": 0, "errors": 0, "by_board": {}}

    if not active:
        return stats

    # ── Phase 1: parallel HTTP fetch ──────────────────────────────────────────
    if progress_callback:
        progress_callback("Fetching job boards in parallel…", 0.0)

    fetch_results: Dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=_MAX_FETCH_WORKERS) as executor:
        futures = {executor.submit(fn): key for key, _, fn in active}
        done = 0
        for future in as_completed(futures):
            key = futures[future]
            done += 1
            try:
                fetch_results[key] = future.result()
            except Exception as exc:
                fetch_results[key] = exc
            if progress_callback:
                progress_callback(
                    f"Fetched {done}/{len(active)} boards…",
                    done / len(active) * 0.5,
                )

    # ── Phase 2: serial filter + save ────────────────────────────────────────
    for i, (key, name, _fn) in enumerate(active):
        result = fetch_results.get(key)
        board_stats = {"scraped": 0, "matched": 0, "saved": 0}

        if progress_callback:
            progress_callback(f"Saving {name}…", 0.5 + i / len(active) * 0.5)

        if isinstance(result, Exception):
            stats["errors"] += 1
            print(f"  {name}: fetch error — {result}")
            stats["by_board"][key] = board_stats
            continue

        try:
            print(f"\n--- {name} ---")
            jobs = result or []
            board_stats["scraped"] = len(jobs)
            print(f"  Fetched {len(jobs)} jobs")

            matching = [j for j in jobs if matches_criteria(j, criteria)]
            board_stats["matched"] = len(matching)
            print(f"  {len(matching)} match criteria")

            for job in matching:
                company_id = db.find_or_create_company(
                    job["company_name"],
                    defaults={"source": "job_board", "ats_type": "unknown"},
                )
                db_job = to_db_job(job, company_id)
                if db.upsert_job(db_job):
                    board_stats["saved"] += 1
                    # Compute rule-based score at ingest so Browse Jobs is useful immediately
                    try:
                        from job_scout.ai.gemini import score_job_rule_based
                        score_result = score_job_rule_based(db_job, criteria)
                        if score_result.get("score", 0) > 0 and db_job.get("fingerprint"):
                            db._request(
                                "PATCH", f"jobs?fingerprint=eq.{db_job['fingerprint']}",
                                json={
                                    "match_score": score_result["score"],
                                    "match_reason": score_result.get("match_reason", ""),
                                },
                            )
                    except Exception:
                        pass  # Non-fatal — scoring can run in Stage 5 instead

            print(f"  Saved {board_stats['saved']} new jobs")

        except Exception as e:
            stats["errors"] += 1
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()

        stats["by_board"][key] = board_stats
        stats["total_scraped"] += board_stats["scraped"]
        stats["matched"] += board_stats["matched"]
        stats["saved"] += board_stats["saved"]

    if progress_callback:
        progress_callback("Done!", 1.0)

    print(f"\nBoard scraping: {stats['total_scraped']} scraped, {stats['matched']} matched, {stats['saved']} saved")
    return stats
