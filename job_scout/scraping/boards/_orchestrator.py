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

_BOARDS_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))),
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


def _all_boards_registry() -> dict:
    return {
        "remoteok":             ("RemoteOK",             lambda: RemoteOKScraper().get_jobs()),
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
    }


def scrape_board_jobs(
    db,
    boards: List[str] = None,
    criteria: Dict = None,
    progress_callback=None,
) -> Dict:
    """
    Scrape jobs from all job boards, filter, save to DB.
    Returns {"total_scraped", "matched", "saved", "errors", "by_board"}.
    """
    if criteria is None:
        criteria = _DEFAULT_CRITERIA

    all_boards = _all_boards_registry()

    if boards is None:
        boards = _get_enabled_boards(list(all_boards.keys()))

    stats = {"total_scraped": 0, "matched": 0, "saved": 0, "errors": 0, "by_board": {}}
    total_boards = len(boards)

    for i, board_key in enumerate(boards):
        if board_key not in all_boards:
            continue

        board_name, fetch_fn = all_boards[board_key]

        if progress_callback:
            progress_callback(f"Scraping {board_name}...", i / total_boards)

        board_stats = {"scraped": 0, "matched": 0, "saved": 0}

        try:
            print(f"\n--- {board_name} ---")
            jobs = fetch_fn()
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

            print(f"  Saved {board_stats['saved']} new jobs")

        except Exception as e:
            stats["errors"] += 1
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()

        stats["by_board"][board_key] = board_stats
        stats["total_scraped"] += board_stats["scraped"]
        stats["matched"] += board_stats["matched"]
        stats["saved"] += board_stats["saved"]

    if progress_callback:
        progress_callback("Done!", 1.0)

    print(f"\nBoard scraping: {stats['total_scraped']} scraped, {stats['matched']} matched, {stats['saved']} saved")
    return stats
