#!/usr/bin/env python3
"""
scripts/seed_demo.py
Populate the DB with realistic fake data for demo deployments.
Creates 50 companies + 200 jobs so the demo URL works without real API keys.

Usage:
  python scripts/seed_demo.py
  python scripts/seed_demo.py --clear   # delete existing demo data first
"""

import os
import sys
import argparse
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from db import get_db


_COMPANIES = [
    ("Acme Cloud",      "greenhouse", "yc_directory",  "seed",     12,  ["worldwide"]),
    ("ByteForge",       "ashby",      "serper",         "series_a", 45,  ["worldwide"]),
    ("Syntax Inc",      "lever",      "job_board",      "seed",     8,   ["worldwide"]),
    ("NeuralWave",      "greenhouse", "yc_directory",  "pre-seed", 5,   ["worldwide"]),
    ("DistroCore",      "ashby",      "serper",         "seed",     20,  ["worldwide"]),
    ("PulseDB",         "lever",      "remoteintech_github", "series_a", 60, ["worldwide"]),
    ("Zephyr API",      "greenhouse", "yc_directory",  "seed",     15,  ["worldwide"]),
    ("StackPilot",      "ashby",      "serper",         "seed",     7,   ["europe"]),
    ("Cloudrift",       "lever",      "job_board",      "series_b", 120, ["worldwide"]),
    ("Indexar",         "greenhouse", "yc_directory",  "pre-seed", 4,   ["worldwide"]),
    ("Meshify",         "ashby",      "serper",         "seed",     18,  ["worldwide"]),
    ("FluxOps",         "lever",      "job_board",      "series_a", 55,  ["worldwide"]),
    ("Parcel AI",       "greenhouse", "yc_directory",  "seed",     10,  ["worldwide"]),
    ("Sigma Labs",      "ashby",      "serper",         "series_a", 30,  ["worldwide"]),
    ("NodeChain",       "lever",      "remoteintech_github", "bootstrapped", 3, ["worldwide"]),
    ("VectorDB",        "greenhouse", "yc_directory",  "seed",     22,  ["worldwide"]),
    ("SpanOps",         "ashby",      "serper",         "seed",     9,   ["europe"]),
    ("Logstride",       "lever",      "job_board",      "series_a", 70,  ["worldwide"]),
    ("Prismatica",      "greenhouse", "yc_directory",  "pre-seed", 6,   ["worldwide"]),
    ("Relay Networks",  "ashby",      "serper",         "seed",     25,  ["worldwide"]),
    ("Hextron",         "lever",      "job_board",      "series_b", 150, ["worldwide"]),
    ("OpenRoute",       "greenhouse", "yc_directory",  "seed",     11,  ["worldwide"]),
    ("Kestrel AI",      "ashby",      "serper",         "series_a", 35,  ["worldwide"]),
    ("Dataflow Co",     "lever",      "remoteintech_github", "series_a", 80, ["worldwide"]),
    ("Patchwork",       "greenhouse", "yc_directory",  "seed",     14,  ["worldwide"]),
    ("TurboDB",         "ashby",      "serper",         "seed",     6,   ["europe"]),
    ("Cellar IO",       "lever",      "job_board",      "series_a", 50,  ["worldwide"]),
    ("Irongate",        "greenhouse", "yc_directory",  "pre-seed", 3,   ["worldwide"]),
    ("Arcflow",         "ashby",      "serper",         "seed",     19,  ["worldwide"]),
    ("Tessellate",      "lever",      "job_board",      "series_b", 200, ["worldwide"]),
    ("Nexbridge",       "greenhouse", "yc_directory",  "seed",     13,  ["worldwide"]),
    ("Pulsar Labs",     "ashby",      "serper",         "series_a", 42,  ["worldwide"]),
    ("Driftwood",       "lever",      "remoteintech_github", "bootstrapped", 2, ["worldwide"]),
    ("Quantum Path",    "greenhouse", "yc_directory",  "seed",     17,  ["worldwide"]),
    ("Strata Cloud",    "ashby",      "serper",         "seed",     8,   ["europe"]),
    ("Ignite API",      "lever",      "job_board",      "series_a", 65,  ["worldwide"]),
    ("Meridian AI",     "greenhouse", "yc_directory",  "pre-seed", 5,   ["worldwide"]),
    ("Codestream",      "ashby",      "serper",         "seed",     23,  ["worldwide"]),
    ("Vantage DB",      "lever",      "job_board",      "series_b", 180, ["worldwide"]),
    ("Lumio",           "greenhouse", "yc_directory",  "seed",     10,  ["worldwide"]),
    ("Faultless",       "ashby",      "serper",         "series_a", 38,  ["worldwide"]),
    ("GatewayX",        "lever",      "remoteintech_github", "series_a", 90, ["worldwide"]),
    ("Mosaic IO",       "greenhouse", "yc_directory",  "seed",     16,  ["worldwide"]),
    ("Creston",         "ashby",      "serper",         "seed",     7,   ["europe"]),
    ("Helix Run",       "lever",      "job_board",      "series_a", 55,  ["worldwide"]),
    ("Voidbridge",      "greenhouse", "yc_directory",  "pre-seed", 4,   ["worldwide"]),
    ("Solstice AI",     "ashby",      "serper",         "seed",     21,  ["worldwide"]),
    ("Thornfield",      "lever",      "job_board",      "series_b", 160, ["worldwide"]),
    ("Canopy Dev",      "greenhouse", "yc_directory",  "seed",     12,  ["worldwide"]),
    ("Praxis Labs",     "ashby",      "serper",         "series_a", 33,  ["worldwide"]),
]

_TITLES = [
    "Backend Engineer", "Senior Backend Engineer", "Full Stack Engineer",
    "Software Engineer", "Platform Engineer", "Infrastructure Engineer",
    "Python Developer", "Go Developer", "Site Reliability Engineer",
    "API Engineer", "Data Engineer", "DevOps Engineer",
    "Cloud Engineer", "Systems Engineer", "Staff Engineer",
]

_BOARDS = [
    "greenhouse", "lever", "ashby", "remoteok", "remotive",
    "himalayas", "jobicy", "hackernews", "cord", "wellfound",
]

_DESCRIPTIONS = [
    "We're building the future of developer tooling. Small team, big impact. Python, Go, PostgreSQL.",
    "Seed-funded startup urgently hiring backend engineers. Remote-first, async culture. Python + FastAPI.",
    "Series A startup backed by top VCs. Looking for passionate engineers who want to move fast.",
    "We raised $4M seed round and are expanding the team. Remote worldwide. Equity + competitive salary.",
    "Small team (10 people) building B2B SaaS. Need a Python engineer ASAP. Great culture, zero bureaucracy.",
    "YC-backed company hiring founding engineers. Work directly with the founders. Python/Go/Kubernetes.",
    "We're a 5-person team growing fast. Looking for a backend engineer who can own entire features.",
    "Climate tech startup building renewable energy infrastructure. Remote-first. Python, Django, PostgreSQL.",
    "Developer tools company. We use Go and Rust. Small team, fast iteration, no enterprise politics.",
    "B2B SaaS for the healthcare industry. Fully remote team across 12 countries. Python + TypeScript.",
]


def _fingerprint(title: str, company: str) -> str:
    import re
    def _n(t): return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t.lower())).strip()
    raw = f"{_n(company)}::{_n(title)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def generate_companies() -> List[Dict]:
    companies = []
    for name, ats, source, funding, headcount, regions in _COMPANIES:
        slug = name.lower().replace(" ", "-")
        ats_url = {
            "greenhouse": f"https://boards.greenhouse.io/{slug}",
            "lever":      f"https://jobs.lever.co/{slug}",
            "ashby":      f"https://jobs.ashbyhq.com/{slug}",
        }.get(ats, f"https://{slug}.com/careers")
        companies.append({
            "name":           name,
            "website":        f"https://{slug}.io",
            "career_url":     ats_url,
            "ats_type":       ats,
            "source":         source,
            "is_active":      True,
            "priority_score": 8 if funding in ("seed", "pre-seed") else 6,
            "funding_stage":  funding,
            "headcount":      headcount,
            "regions":        regions,
            "is_remote_first": True,
            "notes":          f"Demo seed data — {funding} startup",
        })
    return companies


def generate_jobs(company_ids: List[str]) -> List[Dict]:
    jobs = []
    rng = random.Random(42)
    now = datetime.now()

    user_actions = ["applied"] * 40 + ["saved"] * 20 + ["rejected"] * 10 + [None] * 130

    for i in range(200):
        company_id = company_ids[i % len(company_ids)]
        title = _TITLES[i % len(_TITLES)]
        source = _BOARDS[i % len(_BOARDS)]
        days_ago = rng.randint(0, 30)
        discovered = now - timedelta(days=days_ago)
        score = rng.randint(30, 95)
        desp = rng.randint(0, 80)
        action = user_actions[i]

        job = {
            "company_id":         company_id,
            "title":              title,
            "location":           "Remote — Worldwide",
            "is_remote":          True,
            "is_remote_global":   True,
            "apply_url":          f"https://demo.example.com/jobs/{i+1}",
            "source_board":       source,
            "source_boards":      source,
            "fingerprint":        _fingerprint(title, f"company-{company_id[:8]}"),
            "match_score":        score,
            "match_reason":       "Demo: strong backend match" if score >= 70 else "Demo: partial match",
            "is_new":             action is None,
            "is_recommended":     score >= 70,
            "user_action":        action,
            "desperation_score":  desp,
            "desperation_signals": "Demo seed data",
            "description":        _DESCRIPTIONS[i % len(_DESCRIPTIONS)],
            "discovered_date":    discovered.date().isoformat(),
            "discovered_at":      discovered.isoformat(),
        }
        if action == "applied":
            applied_at = discovered + timedelta(days=rng.randint(1, 3))
            job["applied_date"]  = applied_at.isoformat()
            job["follow_up_date"] = (applied_at + timedelta(days=5)).isoformat()
        jobs.append(job)
    return jobs


def seed(clear: bool = False):
    db = get_db()

    if clear:
        print("Clearing existing demo data...")
        try:
            db._request("DELETE", "jobs?source_board=eq.demo")
            db._request("DELETE", "companies?source=eq.demo_seed")
        except Exception as e:
            print(f"  Clear error (may be fine): {e}")

    print("Seeding 50 companies...")
    companies = generate_companies()
    existing = {c["name"].lower() for c in db.get_companies(active_only=False, limit=10000)}
    new_cos = [c for c in companies if c["name"].lower() not in existing]
    inserted_cos = db.add_companies_bulk(new_cos) if new_cos else 0
    print(f"  Inserted {inserted_cos} new companies ({len(companies) - len(new_cos)} already existed)")

    # Reload to get IDs
    all_cos = db.get_companies(active_only=False, limit=10000)
    demo_names = {c["name"] for c in companies}
    company_ids = [c["id"] for c in all_cos if c["name"] in demo_names]

    if not company_ids:
        print("No company IDs found — aborting job seeding")
        return

    print(f"Seeding 200 jobs across {len(company_ids)} companies...")
    jobs = generate_jobs(company_ids)
    inserted_jobs = 0
    for job in jobs:
        if db.upsert_job(job):
            inserted_jobs += 1
    print(f"  Inserted {inserted_jobs} new jobs ({200 - inserted_jobs} already existed)")

    print(f"\nDemo data ready! {inserted_cos} companies, {inserted_jobs} jobs seeded.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data")
    parser.add_argument("--clear", action="store_true", help="Delete existing demo data first")
    args = parser.parse_args()
    seed(clear=args.clear)
