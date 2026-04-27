# job_scout/pipeline/scheduler.py
"""
Long-running scheduler for the daily Job Scout pipeline.
Reads config from data/schedule_config.json (written by the Auto-Pilot UI).

Usage:
  python -m job_scout.pipeline.scheduler           # block forever, run on schedule
  python -m job_scout.pipeline.scheduler --now     # run once immediately and exit
  python -m job_scout.pipeline.scheduler --dry-run # print next run time and exit
"""

import json
import os
import sys
import time
import signal
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [scheduler] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("scheduler")

_CONFIG_FILE = Path(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))) / "data" / "schedule_config.json"

_DEFAULTS: Dict = {
    "enabled": True,
    "run_time": "07:00",          # HH:MM local time
    "stages": [1, 2, 3, 4, 5, 6, 7, 8],
    "digest_email": os.getenv("DIGEST_EMAIL", ""),
    "headless": True,
    "max_slugs_per_ats": 100,
    "daily_auto_apply_cap": 50,
}


def load_schedule_config() -> Dict:
    try:
        with open(_CONFIG_FILE) as f:
            saved = json.load(f)
        return {**_DEFAULTS, **saved}
    except Exception:
        return dict(_DEFAULTS)


def save_schedule_config(cfg: Dict) -> None:
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    log.info(f"Schedule config saved: run_time={cfg.get('run_time')}, enabled={cfg.get('enabled')}")


def _run_pipeline_now(cfg: Dict) -> None:
    from job_scout.pipeline.daily_run import run_pipeline, build_config

    pipeline_cfg = build_config()
    # Override with schedule config
    if cfg.get("digest_email"):
        pipeline_cfg["digest_email"] = cfg["digest_email"]
    pipeline_cfg["headless"] = cfg.get("headless", True)
    pipeline_cfg["max_slugs_per_ats"] = cfg.get("max_slugs_per_ats", 100)
    pipeline_cfg["daily_auto_apply_cap"] = cfg.get("daily_auto_apply_cap", 50)

    stages = cfg.get("stages") or list(range(1, 9))

    log.info(f"Pipeline starting — stages={stages}")
    try:
        result = run_pipeline(stages=stages, config=pipeline_cfg, triggered_by="schedule")
        log.info(f"Pipeline finished — status={result.get('_status', 'unknown')}")
    except Exception as e:
        log.error(f"Pipeline error: {e}", exc_info=True)


def next_run_datetime(run_time: str) -> datetime:
    """Return the next datetime when the pipeline should run."""
    h, m = [int(x) for x in run_time.split(":")]
    now = datetime.now()
    candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def run_scheduler(once: bool = False, dry_run: bool = False) -> None:
    """
    Main scheduler loop.

    once=True  → run immediately and exit
    dry_run=True → print config and next run time, then exit
    """
    cfg = load_schedule_config()

    if dry_run:
        log.info(f"Schedule config: {json.dumps(cfg, indent=2)}")
        nxt = next_run_datetime(cfg["run_time"])
        log.info(f"Next scheduled run: {nxt.strftime('%Y-%m-%d %H:%M')}")
        return

    if once:
        log.info("--now flag: running pipeline immediately")
        _run_pipeline_now(cfg)
        return

    if not cfg.get("enabled", True):
        log.info("Scheduler disabled (enabled=false in config). Set enabled=true to activate.")
        return

    try:
        import schedule as sched
    except ImportError:
        log.error("'schedule' package not installed. Run: pip install schedule")
        sys.exit(1)

    run_time = cfg.get("run_time", "07:00")
    log.info(f"Scheduler started — daily at {run_time} local time")
    nxt = next_run_datetime(run_time)
    log.info(f"Next run: {nxt.strftime('%Y-%m-%d %H:%M')}")

    def _job():
        cfg_fresh = load_schedule_config()  # reload in case UI changed config
        if not cfg_fresh.get("enabled", True):
            log.info("Skipping scheduled run — scheduler disabled via config")
            return
        _run_pipeline_now(cfg_fresh)

    sched.every().day.at(run_time).do(_job)

    # Graceful shutdown on SIGTERM (Docker stop)
    shutdown = [False]
    def _sigterm(sig, frame):
        log.info("SIGTERM received — shutting down scheduler")
        shutdown[0] = True
    signal.signal(signal.SIGTERM, _sigterm)

    while not shutdown[0]:
        sched.run_pending()
        time.sleep(30)  # poll every 30s

    log.info("Scheduler stopped")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Job Scout pipeline scheduler")
    parser.add_argument("--now",     action="store_true", help="Run pipeline once immediately")
    parser.add_argument("--dry-run", action="store_true", help="Print config and next run time")
    args = parser.parse_args()
    run_scheduler(once=args.now, dry_run=args.dry_run)
