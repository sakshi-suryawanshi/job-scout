# job_scout/pipeline/daily_run.py
"""
Daily pipeline orchestrator — stitches all 8 stages together.

Usage:
  python -m job_scout.pipeline.daily_run               # run all stages
  python -m job_scout.pipeline.daily_run --stages 2,5  # run specific stages only

Config via environment:
  PIPELINE_STAGES        — comma-separated stage numbers to run (default: all)
  PIPELINE_MAX_JOBS      — max jobs to score per run (default: 500)
  PIPELINE_ATS_SLUGS     — max companies per ATS (default: 100)
  DIGEST_EMAIL           — recipient for daily email digest
  GEMINI_API_KEY         — enables AI scoring
  SERPER_API_KEY         — enables daily dorking discovery
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _parse_stage_list(env_val: str) -> Optional[List[int]]:
    if not env_val:
        return None
    try:
        return [int(s.strip()) for s in env_val.split(",")]
    except ValueError:
        return None


def build_config() -> Dict:
    """Build pipeline config from env vars + sensible defaults."""
    return {
        # Discovery
        "yc_enabled":                   True,
        "yc_batches":                   ["W24", "S24", "W23"],
        "yc_limit":                     100,
        "remoteintech_enabled":         True,
        "alternative_enabled":          True,
        "serper_enabled":               bool(os.getenv("SERPER_API_KEY")),
        "serper_categories":            [
            "linkedin_daily", "indeed_daily",
            "distress_signals", "funding_signals", "yc_latest",
        ],
        "serper_max_queries_per_category": int(os.getenv("SERPER_MAX_Q", "3")),

        # Scraping
        "ats_enabled":                  True,
        "ats_types":                    ["greenhouse", "lever", "ashby"],
        "max_slugs_per_ats":            int(os.getenv("PIPELINE_ATS_SLUGS", "100")),
        "boards_enabled":               True,
        "boards":                       None,  # None → boards_config.json defaults

        # Scoring
        "use_ai":                       bool(os.getenv("GEMINI_API_KEY")),
        "max_jobs":                     int(os.getenv("PIPELINE_MAX_JOBS", "500")),
        "days":                         90,

        # Auto-apply
        "daily_auto_apply_cap":         50,

        # Digest
        "digest_email":                 os.getenv("DIGEST_EMAIL", ""),
    }


def run_pipeline(
    db=None,
    stages: Optional[List[int]] = None,
    config: Optional[Dict] = None,
    triggered_by: str = "schedule",
) -> Dict:
    """
    Execute the full 8-stage pipeline (or a subset).

    Args:
        db:          Database instance. If None, uses get_db().
        stages:      List of stage numbers to run (1-8). None = run all.
        config:      Pipeline config dict. None = build from env.
        triggered_by: 'schedule' | 'manual'

    Returns:
        run_stats dict with per-stage results and the pipeline_run id.
    """
    if db is None:
        from db import get_db
        db = get_db()

    if config is None:
        config = build_config()

    if stages is None:
        env_stages = _parse_stage_list(os.getenv("PIPELINE_STAGES", ""))
        stages = env_stages or [1, 2, 3, 4, 5, 6, 7, 8]

    # Create pipeline run record
    from job_scout.db.repositories.pipeline_runs import create_run, complete_run, add_stage_result
    run_record = create_run(triggered_by=triggered_by)
    run_id = run_record["id"] if run_record else None

    print(f"\n{'='*60}")
    print(f"JOB SCOUT PIPELINE — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Stages: {stages}  |  Run ID: {run_id}")
    print(f"{'='*60}\n")

    from job_scout.pipeline.stages import (
        stage_discover, stage_scrape, stage_enrich, stage_classify,
        stage_score, stage_auto_apply, stage_follow_ups, stage_digest,
    )

    stage_map = {
        1: ("discover",    stage_discover),
        2: ("scrape",      stage_scrape),
        3: ("enrich",      stage_enrich),
        4: ("classify",    stage_classify),
        5: ("score",       stage_score),
        6: ("auto_apply",  stage_auto_apply),
        7: ("follow_ups",  stage_follow_ups),
    }

    run_stats: Dict = {}
    pipeline_status = "success"

    for stage_num in sorted(stages):
        if stage_num == 8:
            continue  # Digest runs last, after all other stages
        if stage_num not in stage_map:
            print(f"Unknown stage {stage_num} — skipping")
            continue

        name, fn = stage_map[stage_num]
        print(f"\n── Stage {stage_num}: {name.upper()} ──")
        try:
            result = fn(db, config)
            run_stats[name] = result
            if run_id:
                add_stage_result(run_id, name, "success", result)
        except Exception as e:
            print(f"Stage {stage_num} ({name}) FAILED: {e}")
            import traceback
            traceback.print_exc()
            run_stats[name] = {"error": str(e)}
            pipeline_status = "partial"
            if run_id:
                add_stage_result(run_id, name, "failed", None, str(e))

    # Stage 8: Digest (always last)
    if 8 in stages:
        print("\n── Stage 8: DIGEST ──")
        try:
            digest_result = stage_digest(db, run_stats, config)
            run_stats["digest"] = digest_result
            if run_id:
                add_stage_result(run_id, "digest", "success", {
                    "sent": digest_result["sent"],
                    "recipients": digest_result["recipients"],
                })
        except Exception as e:
            print(f"Stage 8 (digest) FAILED: {e}")
            run_stats["digest"] = {"error": str(e)}
            pipeline_status = "partial"

    # Finalize run record
    digest_html = run_stats.get("digest", {}).get("digest_html", "")
    if run_id:
        complete_run(
            run_id,
            status=pipeline_status,
            stats={k: v for k, v in run_stats.items() if k != "digest"},
            digest_html=digest_html,
        )

    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETE — status: {pipeline_status}")
    for stage, stats in run_stats.items():
        if stage != "digest":
            print(f"  {stage}: {stats}")
    print(f"{'='*60}\n")

    run_stats["_run_id"] = run_id
    run_stats["_status"] = pipeline_status
    return run_stats


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Job Scout daily pipeline")
    parser.add_argument(
        "--stages",
        type=str,
        default="",
        help="Comma-separated stage numbers (1-8). Default: all.",
    )
    parser.add_argument(
        "--triggered-by",
        type=str,
        default="manual",
        choices=["manual", "schedule", "api"],
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print config and exit without running.",
    )
    args = parser.parse_args()

    cfg = build_config()

    if args.dry_run:
        print("Pipeline config:")
        print(json.dumps(cfg, indent=2, default=str))
        sys.exit(0)

    stage_list = _parse_stage_list(args.stages)
    run_pipeline(stages=stage_list, config=cfg, triggered_by=args.triggered_by)
