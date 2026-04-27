# job_scout/discovery/orchestrator.py
# Moved from worker/discovery/run_discovery.py — imports updated.
"""Discovery orchestration: run all discovery sources."""

import sys
import os

from job_scout.discovery.yc import fetch_yc_companies
from job_scout.discovery.alternative import fetch_alternative_sources
from job_scout.discovery.serper_dorking import SerperDorker, create_signal_from_result, DORK_QUERIES
from db import get_db


def _dedup_and_insert(db, companies, source_label):
    if not companies:
        print(f"No companies from {source_label}")
        return 0
    existing = db.get_companies(active_only=False, limit=10000)
    existing_names = {c["name"].lower() for c in existing}
    new_companies = [c for c in companies if c["name"].lower() not in existing_names]
    if new_companies:
        inserted = db.add_companies_bulk(new_companies)
        print(f"\n✅ Inserted {inserted} new companies from {source_label}")
        return inserted
    print(f"\nℹ️ No new companies from {source_label}")
    return 0


def run_yc_discovery(batch: str = None, limit: int = 50):
    db = get_db()
    print(f"\n{'='*50}\nYC DISCOVERY: batch={batch}, limit={limit}\n{'='*50}\n")
    companies = fetch_yc_companies(batch=batch, limit=limit)
    return _dedup_and_insert(db, companies, f"YC ({batch})")


def run_alternative_discovery():
    db = get_db()
    print(f"\n{'='*50}\nALTERNATIVE DISCOVERY\n{'='*50}\n")
    companies = fetch_alternative_sources()
    return _dedup_and_insert(db, companies, "alternative sources")


def run_serper_discovery(categories=None, max_queries_per_category=None,
                         results_per_query=10, save_signals=True):
    db = get_db()
    print(f"\n{'='*50}\nSERPER.DEV DORKING DISCOVERY\nCategories: {categories or 'all'}\n{'='*50}\n")
    dorker = SerperDorker()
    companies = dorker.run_discovery(categories=categories,
                                     max_queries_per_category=max_queries_per_category,
                                     results_per_query=results_per_query)
    inserted = _dedup_and_insert(db, companies, "Serper.dev dorking")
    signals_saved = 0
    if save_signals:
        signal_categories = {"distress", "funding", "hidden", "regional", "hackernews", "indiehackers"}
        for company in companies:
            cat = company.get("notes", "")
            for sig_cat in signal_categories:
                if sig_cat in cat.lower():
                    signal = create_signal_from_result(company, sig_cat)
                    if db.add_signal(signal):
                        signals_saved += 1
                    break
    print(f"\nSerper queries used: {dorker.queries_used}")
    print(f"Signals saved: {signals_saved}")
    return inserted, signals_saved, dorker.queries_used


def run_full_discovery():
    total = 0
    total += run_yc_discovery(batch="W24", limit=100)
    total += run_yc_discovery(batch="S23", limit=100)
    total += run_yc_discovery(batch="W23", limit=100)
    total += run_alternative_discovery()
    try:
        inserted, _signals, _queries = run_serper_discovery(max_queries_per_category=2, results_per_query=10)
        total += inserted
    except ValueError as e:
        print(f"\n⚠️ Serper.dev skipped: {e}")
    print(f"\n{'='*50}\nDISCOVERY COMPLETE: {total} total companies added\n{'='*50}")
    return total


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["yc", "alt", "serper", "all"], default="all")
    parser.add_argument("--batch", default="W24")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--serper-categories", nargs="*", choices=list(DORK_QUERIES.keys()))
    parser.add_argument("--max-queries", type=int, default=None)
    args = parser.parse_args()

    if args.source == "yc":
        run_yc_discovery(batch=args.batch, limit=args.limit)
    elif args.source == "alt":
        run_alternative_discovery()
    elif args.source == "serper":
        run_serper_discovery(categories=args.serper_categories, max_queries_per_category=args.max_queries)
    else:
        run_full_discovery()
