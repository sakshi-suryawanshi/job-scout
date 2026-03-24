# worker/discovery/run_discovery.py
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from yc_scraper import fetch_yc_companies_v2
from alternative_scrapers import fetch_alternative_sources
from serper_dorking import SerperDorker, create_signal_from_result, DORK_QUERIES
from db import get_db


def _dedup_and_insert(db, companies, source_label):
    """Check duplicates and bulk insert. Returns count inserted."""
    if not companies:
        print(f"No companies from {source_label}")
        return 0

    existing = db.get_companies(active_only=False, limit=10000)
    existing_names = {c['name'].lower() for c in existing}

    new_companies = [c for c in companies if c['name'].lower() not in existing_names]

    if new_companies:
        inserted = db.add_companies_bulk(new_companies)
        print(f"\n✅ Inserted {inserted} new companies from {source_label}")
        return inserted
    else:
        print(f"\nℹ️ No new companies from {source_label}")
        return 0


def run_yc_discovery(batch: str = None, limit: int = 50):
    """Fetch YC companies"""
    db = get_db()

    print(f"\n{'='*50}")
    print(f"YC DISCOVERY: batch={batch}, limit={limit}")
    print(f"{'='*50}\n")

    companies = fetch_yc_companies_v2(batch=batch, limit=limit)
    return _dedup_and_insert(db, companies, f"YC ({batch})")


def run_alternative_discovery():
    """Fetch from alternative sources"""
    db = get_db()

    print(f"\n{'='*50}")
    print(f"ALTERNATIVE DISCOVERY")
    print(f"{'='*50}\n")

    companies = fetch_alternative_sources()
    return _dedup_and_insert(db, companies, "alternative sources")


def run_serper_discovery(
    categories=None,
    max_queries_per_category=None,
    results_per_query=10,
    save_signals=True,
):
    """
    Run Serper.dev Google dorking discovery.

    Args:
        categories: List of dork categories to run (None = all)
        max_queries_per_category: Limit queries per category (budget control)
        results_per_query: Number of results per search
        save_signals: Whether to also save signals to the signals table

    Returns:
        (companies_inserted, signals_saved, queries_used)
    """
    db = get_db()

    print(f"\n{'='*50}")
    print(f"SERPER.DEV DORKING DISCOVERY")
    print(f"Categories: {categories or 'all'}")
    print(f"{'='*50}\n")

    dorker = SerperDorker()
    companies = dorker.run_discovery(
        categories=categories,
        max_queries_per_category=max_queries_per_category,
        results_per_query=results_per_query,
    )

    inserted = _dedup_and_insert(db, companies, "Serper.dev dorking")

    # Save signals for distress/funding/hidden categories
    signals_saved = 0
    if save_signals:
        signal_categories = {"distress", "funding", "hidden", "regional", "hackernews", "indiehackers"}
        for company in companies:
            cat = company.get("notes", "")
            # Extract category from notes
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
    """Run all discovery sources"""
    total = 0

    # YC batches
    total += run_yc_discovery(batch="W24", limit=100)
    total += run_yc_discovery(batch="S23", limit=100)
    total += run_yc_discovery(batch="W23", limit=100)

    # Alternative sources
    total += run_alternative_discovery()

    # Serper.dev dorking (budget-conscious: 2 queries per category)
    try:
        inserted, _signals, _queries = run_serper_discovery(
            max_queries_per_category=2,
            results_per_query=10,
        )
        total += inserted
    except ValueError as e:
        print(f"\n⚠️ Serper.dev skipped: {e}")

    print(f"\n{'='*50}")
    print(f"DISCOVERY COMPLETE: {total} total companies added")
    print(f"{'='*50}")

    return total


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["yc", "alt", "serper", "all"], default="all")
    parser.add_argument("--batch", default="W24")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--serper-categories",
        nargs="*",
        choices=list(DORK_QUERIES.keys()),
        help="Serper dork categories to run",
    )
    parser.add_argument(
        "--max-queries", type=int, default=None,
        help="Max queries per category (budget control)",
    )

    args = parser.parse_args()

    if args.source == "yc":
        run_yc_discovery(batch=args.batch, limit=args.limit)
    elif args.source == "alt":
        run_alternative_discovery()
    elif args.source == "serper":
        run_serper_discovery(
            categories=args.serper_categories,
            max_queries_per_category=args.max_queries,
        )
    else:
        run_full_discovery()