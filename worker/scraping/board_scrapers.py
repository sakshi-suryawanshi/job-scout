# worker/scraping/board_scrapers.py — backward-compat stub
# All logic now lives in job_scout/scraping/boards/
from job_scout.scraping.boards import scrape_board_jobs, _get_enabled_boards  # noqa: F401
from job_scout.scraping.boards._api import (  # noqa: F401
    RemoteOKScraper, RemotiveScraper, HimalayasScraper, ArbeitnowScraper,
    JobicyScraper, TheMuseScraper, WorkingNomadsScraper, WFHioScraper,
    DevITJobsScraper, JustJoinScraper, FourDayWeekScraper, CryptoJobsListScraper,
    ClimateBaseScraper, RemoteFirstJobsScraper, Web3CareerScraper,
    RemotiveDevOpsScraper, RemotiveDataScraper, WorkingNomadsDevOpsScraper,
    JobicyAllScraper,
)
from job_scout.scraping.boards._rss import (  # noqa: F401
    WeWorkRemotelyScraper, JobspressoScraper, RemoteCo, AuthenticJobsScraper,
    DjangoJobsScraper, LaraJobsScraper, NodeDeskScraper, VueJobsScraper,
    GolangJobsScraper, DynamiteJobsScraper, SmashingMagJobsScraper,
    FreshRemoteScraper, PowerToFlyScraper, WWRDevOpsScraper, WWRFrontendScraper,
    parse_rss_feed as _parse_rss_feed,
)
from job_scout.scraping.boards._community import HackerNewsScraper, RedditScraper  # noqa: F401
from job_scout.scraping.boards._salary import (  # noqa: F401
    CordScraper, WellfoundScraper, HiredScraper, TalentioScraper, PalletScraper,
)
from job_scout.scraping.base import to_db_job  # noqa: F401
from job_scout.enrichment.filters import matches_criteria  # noqa: F401
