# worker/discovery/run_discovery.py
import sys
import os

# Add project root package path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from yc_scraper import fetch_yc_companies
from ph_scraper import fetch_ph_companies
from db import get_db


def run_yc_discovery(batch: str = None, limit: int = 50):
    """Fetch YC companies and save to DB."""
    db = get_db()
    
    print(f"\n{'='*50}")
    print(f"YC DISCOVERY: batch={batch}, limit={limit}")
    print(f"{'='*50}\n")
    
    companies = fetch_yc_companies(batch=batch, limit=limit, enrich=True)
    
    if not companies:
        print("No companies found!")
        return 0
    
    # Check for duplicates (by name)
    existing = db.get_companies(active_only=False, limit=10000)
    existing_names = {c['name'].lower() for c in existing}
    
    new_companies = []
    for c in companies:
        if c['name'].lower() not in existing_names:
            new_companies.append(c)
        else:
            print(f"Skipping duplicate: {c['name']}")
    
    if new_companies:
        inserted = db.add_companies_bulk(new_companies)
        print(f"\n✅ Inserted {inserted} new YC companies")
        return inserted
    else:
        print("\nℹ️ No new companies to add")
        return 0


def run_ph_discovery(topic: str = None, pages: int = 3):
    """Fetch Product Hunt companies and save to DB."""
    db = get_db()
    
    print(f"\n{'='*50}")
    print(f"PH DISCOVERY: topic={topic}, pages={pages}")
    print(f"{'='*50}\n")
    
    companies = fetch_ph_companies(topic=topic, pages=pages, enrich=True)
    
    if not companies:
        print("No companies found!")
        return 0
    
    # Check for duplicates
    existing = db.get_companies(active_only=False, limit=10000)
    existing_names = {c['name'].lower() for c in existing}
    
    new_companies = []
    for c in companies:
        if c['name'].lower() not in existing_names:
            new_companies.append(c)
        else:
            print(f"Skipping duplicate: {c['name']}")
    
    if new_companies:
        inserted = db.add_companies_bulk(new_companies)
        print(f"\n✅ Inserted {inserted} new PH companies")
        return inserted
    else:
        print("\nℹ️ No new companies to add")
        return 0


def run_full_discovery():
    """Run all discovery sources."""
    total = 0
    
    # YC recent batches
    total += run_yc_discovery(batch="W24", limit=100)
    total += run_yc_discovery(batch="S23", limit=100)
    total += run_yc_discovery(batch="W23", limit=100)
    
    # Product Hunt
    total += run_ph_discovery(topic="developer-tools", pages=3)
    total += run_ph_discovery(topic="saas", pages=3)
    total += run_ph_discovery(pages=5)  # Recent
    
    print(f"\n{'='*50}")
    print(f"DISCOVERY COMPLETE: {total} total companies added")
    print(f"{'='*50}")
    
    return total


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Discover companies from YC and Product Hunt")
    parser.add_argument("--source", choices=["yc", "ph", "all"], default="all")
    parser.add_argument("--batch", help="YC batch (e.g., W24, S23)")
    parser.add_argument("--topic", help="PH topic (e.g., developer-tools, saas)")
    parser.add_argument("--limit", type=int, default=50, help="Max companies to fetch")
    
    args = parser.parse_args()
    
    if args.source == "yc":
        run_yc_discovery(batch=args.batch, limit=args.limit)
    elif args.source == "ph":
        run_ph_discovery(topic=args.topic, pages=3)
    else:
        run_full_discovery()