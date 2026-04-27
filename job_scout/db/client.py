# job_scout/db/client.py
# V2 thin wrapper — re-exports from root db.py for now.
# Repositories in job_scout/db/repositories/ use this client.
"""DB client: re-export root db.py until full repository layer is wired."""

from db import Database, get_db  # noqa: F401

__all__ = ["Database", "get_db"]
