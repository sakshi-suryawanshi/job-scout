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
        """Find a company by name (case-insensitive)."""
        try:
            result = self._request("GET", "companies", params={
                "name": f"ilike.{name}",
                "limit": 1
            })
            return result[0] if result else None
        except:
            return None

    def find_or_create_company(self, name: str, defaults: Dict = None) -> Optional[str]:
        """Find company by name or create it. Returns company ID."""
        existing = self.get_company_by_name(name)
        if existing:
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

    def add_jobs_bulk(self, jobs: List[Dict]) -> int:
        """Bulk insert jobs, falling back to individual on conflict."""
        if not jobs:
            return 0
        inserted = 0
        for job in jobs:
            if self.add_job(job):
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
        
        # 7-day filter
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        params["discovered_date"] = f"gte.{cutoff}"
        
        params["limit"] = filters.get("limit", 100)
        params["order"] = "discovered_at.desc"
        
        try:
            # Join with companies for name
            select = "*,companies(name,website)"
            return self._request("GET", "jobs", params={**params, "select": select}) or []
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