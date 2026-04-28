#!/usr/bin/env python3
# scripts/migrate.py
"""
Run pending Supabase SQL migrations in order.

Usage:
  python scripts/migrate.py                   # apply all pending
  python scripts/migrate.py --dry-run         # print SQLs without running
  python scripts/migrate.py --list            # show applied / pending status

Migrations live in: job_scout/db/migrations/*.sql
They are applied in lexicographic order (001_, 002_, …).
Applied migrations are tracked in a local JSON ledger at data/migrations.json
to avoid re-running them.
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_MIGRATIONS_DIR = Path(__file__).parent.parent / "job_scout" / "db" / "migrations"
_LEDGER_PATH = Path(__file__).parent.parent / "data" / "migrations.json"


def _load_ledger() -> dict:
    try:
        with open(_LEDGER_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"applied": []}


def _save_ledger(ledger: dict):
    _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LEDGER_PATH, "w") as f:
        json.dump(ledger, f, indent=2)


def _get_migration_files() -> list[Path]:
    return sorted(_MIGRATIONS_DIR.glob("*.sql"))


def list_migrations(ledger: dict):
    applied = set(ledger.get("applied", []))
    files = _get_migration_files()
    if not files:
        print("No migration files found in", _MIGRATIONS_DIR)
        return
    for f in files:
        status = "✅ applied" if f.name in applied else "⏳ pending"
        print(f"  {status}  {f.name}")


def apply_migrations(dry_run: bool = False):
    try:
        from db import get_db
        db = get_db()
    except Exception as e:
        print(f"DB connection failed: {e}")
        sys.exit(1)

    ledger = _load_ledger()
    applied = set(ledger.get("applied", []))
    files = _get_migration_files()
    pending = [f for f in files if f.name not in applied]

    if not pending:
        print("Nothing to migrate — all migrations already applied.")
        return

    print(f"Found {len(pending)} pending migration(s):\n")
    for f in pending:
        sql = f.read_text()
        print(f"── {f.name} ──")
        print(sql[:200].strip(), "…" if len(sql) > 200 else "")
        print()

        if dry_run:
            print("  [dry-run] would apply this migration\n")
            continue

        try:
            # Supabase PostgREST doesn't support raw SQL via REST.
            # Execute via the rpc endpoint if available, or print instructions.
            print(f"  Applying {f.name}…")
            # Attempt via db._request for projects that expose a sql RPC:
            try:
                db._request("POST", "rpc/exec_sql", json={"sql": sql})
                print(f"  ✅ Applied {f.name}")
            except Exception:
                # Fallback: print the SQL and ask user to run it manually
                print(f"  ⚠️  Could not apply via RPC. Run manually in Supabase SQL editor:")
                print(f"  https://supabase.com/dashboard/project/_/sql")
                print()
                print(sql)
                ans = input("Mark as applied anyway? [y/N] ")
                if ans.strip().lower() != "y":
                    print("Stopping.")
                    _save_ledger(ledger)
                    sys.exit(1)

            ledger["applied"].append(f.name)
            _save_ledger(ledger)

        except Exception as e:
            print(f"  ❌ Failed: {e}")
            _save_ledger(ledger)
            sys.exit(1)

    if not dry_run:
        print("All pending migrations applied.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply Supabase SQL migrations")
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without executing")
    parser.add_argument("--list", action="store_true", help="List applied and pending migrations")
    args = parser.parse_args()

    ledger = _load_ledger()

    if args.list:
        list_migrations(ledger)
    else:
        apply_migrations(dry_run=args.dry_run)
