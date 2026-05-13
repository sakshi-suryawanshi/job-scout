# db.py - Using PostgREST directly
import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

class Database:
    def __init__(self, url=None, key=None):
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
        
        # Extract project ref from URL
        # https://xxxx.supabase.co -> xxxx
        self.project_ref = self.url.replace("https://", "").replace(".supabase.co", "")
        self.rest_url = f"{self.url}/rest/v1"
        
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        
        self.client = httpx.Client(headers=self.headers, timeout=30.0)
    
    def _request(self, method: str, path: str, **kwargs) -> Any:
        """Make request to PostgREST"""
        url = f"{self.rest_url}/{path}"
        response = self.client.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    def _count(self, table: str, params: dict = None) -> int:
        """Return exact row count for a table via PostgREST Content-Range header.
        Sends limit=0 so no rows are transferred — only the count header.
        """
        try:
            resp = self.client.get(
                f"{self.rest_url}/{table}",
                params={**(params or {}), "limit": 0},
                headers={**self.headers, "Prefer": "count=exact"},
            )
            content_range = resp.headers.get("Content-Range", "")
            if "/" in content_range:
                total = content_range.split("/")[-1]
                if total.lstrip("-").isdigit():
                    return int(total)
        except Exception:
            pass
        return 0

    def count_companies(self, active_only: bool = True) -> int:
        """Lightweight company count — no rows fetched."""
        params = {"is_active": "eq.true"} if active_only else {}
        return self._count("companies", params)

    def count_jobs(self, days: int = 0) -> int:
        """Lightweight job count — no rows fetched."""
        from datetime import date, timedelta
        params = {}
        if days > 0:
            cutoff = (date.today() - timedelta(days=days)).isoformat()
            params["discovered_at"] = f"gte.{cutoff}"   # column defined in migration 001 / indexed in 010
        return self._count("jobs", params)

    def count_scored_jobs(self) -> int:
        """Lightweight count of jobs with a non-zero match_score."""
        return self._count("jobs", {"match_score": "gt.0"})

    def count_recommended_jobs(self, min_score: int = 70) -> int:
        """Lightweight count of jobs scoring at or above min_score."""
        return self._count("jobs", {"match_score": f"gte.{min_score}"})
    
    def add_company(self, company: Dict[str, Any]) -> Optional[Dict]:
        try:
            result = self._request("POST", "companies", json=company)
            return result[0] if isinstance(result, list) else result
        except Exception as e:
            if "23505" in str(e):  # Unique violation
                print(f"⚠️ Duplicate company: {company.get('name')}")
            else:
                print(f"Error adding company: {e}")
            return None
    
    def add_companies_bulk(self, companies: List[Dict]) -> int:
        if not companies:
            return 0
        
        # PostgREST bulk insert
        try:
            result = self._request("POST", "companies", json=companies)
            return len(result) if isinstance(result, list) else 0
        except Exception as e:
            print(f"Error bulk inserting: {e}")
            # Fall back to individual inserts
            inserted = 0
            for c in companies:
                if self.add_company(c):
                    inserted += 1
            return inserted
    
    def get_companies(self, active_only: bool = True, limit: int = 1000) -> List[Dict]:
        params = {"limit": limit}
        if active_only:
            params["is_active"] = "eq.true"
        
        try:
            return self._request("GET", "companies", params=params) or []
        except Exception as e:
            print(f"Error getting companies: {e}")
            return []
    
    def get_company_by_id(self, company_id: str) -> Optional[Dict]:
        try:
            result = self._request("GET", f"companies?id=eq.{company_id}&limit=1")
            return result[0] if result else None
        except:
            return None
    
    def update_company(self, company_id: str, updates: Dict) -> bool:
        try:
            updates["updated_at"] = datetime.now().isoformat()
            self._request("PATCH", f"companies?id=eq.{company_id}", json=updates)
            return True
        except Exception as e:
            print(f"Error updating: {e}")
            return False
    
    def delete_company(self, company_id: str) -> bool:
        try:
            self._request("DELETE", f"companies?id=eq.{company_id}")
            return True
        except Exception as e:
            print(f"Error deleting: {e}")
            return False
    
    def get_company_by_name(self, name: str) -> Optional[Dict]:
        """Find a company by name (case-insensitive exact match)."""
        try:
            result = self._request("GET", "companies", params={
                "name": f"ilike.{name}",
                "limit": 1
            })
            return result[0] if result else None
        except:
            return None

    def find_or_create_company(self, name: str, defaults: Dict = None) -> Optional[str]:
        """Find company by name or create it. Returns company ID.

        Dedup logic — two-step lookup:
          1. Exact case-insensitive match  ("Stripe" == "stripe")
          2. Normalized match — strips legal suffixes + YC batch tags
             ("Stripe Inc" == "Stripe", "Linear (YC S20)" == "Linear")

        This prevents the same company appearing twice because one source
        adds "Stripe" and another adds "Stripe Inc".
        """
        from datetime import date as _date
        from job_scout.enrichment.dedup import normalize_company_name

        # Step 1: exact match
        existing = self.get_company_by_name(name)

        # Step 2: normalized match — only if exact fails
        if not existing:
            norm_input = normalize_company_name(name)
            if norm_input:
                # Fetch candidates whose name starts with the first word of norm_input
                first_word = norm_input.split()[0] if norm_input.split() else norm_input
                try:
                    candidates = self._request("GET", "companies", params={
                        "name": f"ilike.{first_word}%",
                        "limit": 50,
                    }) or []
                    for c in candidates:
                        if normalize_company_name(c.get("name", "")) == norm_input:
                            existing = c
                            break
                except Exception:
                    pass

        if existing:
            # Bump last_seen_at so auto-discovery cadence is visible
            try:
                self._request("PATCH", f"companies?id=eq.{existing['id']}",
                              json={"last_seen_at": _date.today().isoformat()})
            except Exception:
                pass  # Non-fatal — last_seen_at is informational
            return existing["id"]

        company = {
            "name": name,
            "source": "job_scraper",
            "is_active": True,
            "priority_score": 7,
            **(defaults or {}),
        }
        result = self.add_company(company)
        if result:
            return result["id"]
        # Might have been created by another request
        existing = self.get_company_by_name(name)
        return existing["id"] if existing else None

    # Jobs methods
    def add_job(self, job: Dict[str, Any]) -> Optional[Dict]:
        try:
            result = self._request("POST", "jobs", json=job)
            return result[0] if isinstance(result, list) else result
        except Exception as e:
            err = str(e).lower()
            if "duplicate" in err or "23505" in err or "409" in err or "conflict" in err:
                pass  # Expected — 7-day dedup on apply_url
            else:
                print(f"Error adding job: {e}")
            return None

    def get_job_by_fingerprint(self, fingerprint: str) -> Optional[Dict]:
        """Find a job by its dedup fingerprint."""
        try:
            result = self._request("GET", "jobs", params={
                "fingerprint": f"eq.{fingerprint}",
                "limit": 1,
            })
            return result[0] if result else None
        except Exception:
            return None

    def upsert_job(self, job: Dict[str, Any], exclude_keywords: list = None) -> Optional[Dict]:
        """
        Insert a job, deduplicating by fingerprint.
        If a job with the same fingerprint exists, merge source_boards.
        Returns the job dict if newly inserted, None if duplicate/merged.

        exclude_keywords: optional list of title keywords to reject at the DB boundary,
        regardless of which scraper called this. Last line of defence.
        """
        if exclude_keywords:
            title_lower = (job.get("title") or "").lower()
            if any(kw.lower() in title_lower for kw in exclude_keywords):
                return None

        fingerprint = job.get("fingerprint")
        if fingerprint:
            existing = self.get_job_by_fingerprint(fingerprint)
            if existing:
                # apply_url tiebreaker: if two listings for the same role have DIFFERENT
                # apply_urls and were posted more than 14 days apart, treat as a re-post
                # (the role was re-listed) and let it through as a new entry.
                # Normalize URLs first (strip query/fragment/trailing slash) so trivial
                # variants of the same URL don't trigger spurious reposts.
                from job_scout.enrichment.dedup import _normalize_apply_url
                new_url   = _normalize_apply_url(job.get("apply_url") or "")
                exist_url = _normalize_apply_url(existing.get("apply_url") or "")
                if new_url and exist_url and new_url != exist_url:
                    from datetime import datetime, timedelta
                    _cutoff = datetime.now() - timedelta(days=14)
                    _disc = str(existing.get("discovered_at") or existing.get("discovered_date") or "")[:10]
                    try:
                        _age = datetime.fromisoformat(_disc) if _disc else _cutoff
                    except ValueError:
                        _age = _cutoff
                    if _age < _cutoff:
                        # Re-post: different URL, older than 14 days → treat as new listing
                        job["fingerprint"] = fingerprint + "_repost"
                        return self.add_job(job)

                # Merge source_boards
                new_source = job.get("source_board", "")
                existing_boards = existing.get("source_boards", "") or ""
                boards_list = [b.strip() for b in existing_boards.split(",") if b.strip()]
                if new_source and new_source not in boards_list:
                    boards_list.append(new_source)
                    try:
                        self._request("PATCH", f"jobs?id=eq.{existing['id']}", json={
                            "source_boards": ",".join(boards_list),
                        })
                    except Exception:
                        pass
                return None  # Not a new insert

        # Set source_boards from source_board on first insert
        if "source_board" in job and not job.get("source_boards"):
            job["source_boards"] = job["source_board"]

        return self.add_job(job)

    def add_jobs_bulk(self, jobs: List[Dict]) -> int:
        """Bulk insert jobs using upsert so multi-board signals are tracked."""
        if not jobs:
            return 0
        inserted = 0
        for job in jobs:
            if self.upsert_job(job):
                inserted += 1
        return inserted
    
    def get_jobs(self, **filters) -> List[Dict]:
        params = {}
        
        if filters.get("is_new") is not None:
            params["is_new"] = f"eq.{str(filters['is_new']).lower()}"
        if filters.get("is_recommended") is not None:
            params["is_recommended"] = f"eq.{str(filters['is_recommended']).lower()}"
        if filters.get("company_id"):
            params["company_id"] = f"eq.{filters['company_id']}"
        if filters.get("min_score"):
            params["match_score"] = f"gte.{filters['min_score']}"
        
        # Default: only jobs discovered in last 90 days (jobs older than that are almost always filled).
        # Pass days=0 to disable the filter and return all-time jobs.
        from datetime import datetime, timedelta
        days = filters.get("days", 90)
        if days and days > 0:
            cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            params["discovered_date"] = f"gte.{cutoff}"

        params["limit"] = filters.get("limit", 500)
        params["order"] = "discovered_at.desc"
        
        try:
            # Join with companies — include ats_type so the rules engine and
            # auto-apply orchestrator can route to the right Playwright filler.
            select = "*,companies(name,website,ats_type)"
            rows = self._request("GET", "jobs", params={**params, "select": select}) or []
            # Flatten companies.ats_type onto the job for code that reads job["ats_type"].
            for r in rows:
                co = r.get("companies") or {}
                if isinstance(co, dict) and co.get("ats_type") and not r.get("ats_type"):
                    r["ats_type"] = co["ats_type"]
            return rows
        except Exception as e:
            print(f"Error getting jobs: {e}")
            return []
    
    def mark_job_action(self, job_id: str, action: str) -> bool:
        try:
            self._request("PATCH", f"jobs?id=eq.{job_id}", json={
                "user_action": action,
                "is_new": False
            })
            return True
        except Exception as e:
            print(f"Error marking job: {e}")
            return False

    def mark_job_applied(self, job_id: str, notes: str = None) -> bool:
        """Mark a job as applied with timestamp and auto-set follow-up date."""
        updates = {
            "user_action": "applied",
            "is_new": False,
            "applied_date": datetime.now().isoformat(),
            "follow_up_date": (datetime.now() + timedelta(days=5)).isoformat(),
        }
        if notes:
            updates["application_notes"] = notes
        try:
            self._request("PATCH", f"jobs?id=eq.{job_id}", json=updates)
            return True
        except Exception as e:
            print(f"Error marking applied: {e}")
            return False

    def get_apply_queue(self, limit: int = 500) -> List[Dict]:
        """Get top jobs to apply to — includes unseen and saved jobs, sorted by score."""
        try:
            # PostgREST: user_action is null OR saved
            return self._request("GET", "jobs", params={
                "user_action": "in.(null,saved)",
                "order": "match_score.desc",
                "limit": limit,
                "select": "*,companies(name,website,ats_type)",
            }) or []
        except Exception as e:
            print(f"Error getting apply queue: {e}")
            return []

    def get_follow_ups_due(self) -> List[Dict]:
        """Get applied jobs where follow-up is due."""
        cutoff = datetime.now().isoformat()
        try:
            return self._request("GET", "jobs", params={
                "user_action": "eq.applied",
                "follow_up_date": f"lte.{cutoff}",
                "order": "follow_up_date.asc",
                "select": "*,companies(name,website,ats_type)",
            }) or []
        except Exception as e:
            print(f"Error getting follow-ups: {e}")
            return []

    def snooze_follow_up(self, job_id: str, days: int = 3) -> bool:
        """Push follow-up date forward."""
        try:
            self._request("PATCH", f"jobs?id=eq.{job_id}", json={
                "follow_up_date": (datetime.now() + timedelta(days=days)).isoformat(),
            })
            return True
        except Exception:
            return False
    
    # Signals methods
    def add_signal(self, signal: Dict[str, Any]) -> Optional[Dict]:
        try:
            result = self._request("POST", "signals", json=signal)
            return result[0] if isinstance(result, list) else result
        except Exception as e:
            print(f"Error adding signal: {e}")
            return None
    
    def get_unprocessed_signals(self, limit: int = 100) -> List[Dict]:
        try:
            return self._request("GET", "signals", params={
                "processed": "eq.false",
                "limit": limit,
                "order": "confidence_score.desc"
            }) or []
        except Exception as e:
            print(f"Error: {e}")
            return []
    
    def mark_signal_processed(self, signal_id: str, company_id: Optional[str] = None) -> bool:
        try:
            updates = {"processed": True}
            if company_id:
                updates["company_id"] = company_id
            self._request("PATCH", f"signals?id=eq.{signal_id}", json=updates)
            return True
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    # Queue methods
    def queue_company(self, company_id: str, priority: int = 5) -> bool:
        try:
            self._request("POST", "scrape_queue", json={
                "company_id": company_id,
                "priority": priority,
                "status": "pending"
            })
            return True
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    def get_pending_scrapes(self, limit: int = 10) -> List[Dict]:
        try:
            return self._request("GET", "scrape_queue", params={
                "status": "eq.pending",
                "limit": limit,
                "order": "priority.desc,scheduled_at.asc",
                "select": "*,companies(name,career_url,ats_type)"
            }) or []
        except Exception as e:
            print(f"Error: {e}")
            return []
    
    def update_scrape_status(self, queue_id: str, status: str, error: str = None):
        updates = {
            "status": status,
            "completed_at": datetime.now().isoformat() if status in ['parsed', 'failed'] else None
        }
        if status == "scraping":
            updates["started_at"] = datetime.now().isoformat()
        if error:
            updates["error_message"] = error
        
        try:
            self._request("PATCH", f"scrape_queue?id=eq.{queue_id}", json=updates)
        except Exception as e:
            print(f"Error: {e}")

_db_instance = None

def get_db() -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance