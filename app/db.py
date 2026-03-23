# app/db.py
import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Try loading .env for local dev
try:
    load_dotenv()
except:
    pass

class Database:
    def __init__(self, url=None, key=None):
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
        
        # Lazy import to avoid issues
        from supabase import create_client, Client
        self.client: Client = create_client(self.url, self.key)
    
    # ========== COMPANIES ==========
    
    def add_company(self, company: Dict[str, Any]) -> Optional[Dict]:
        """Add single company."""
        try:
            result = self.client.table("companies").insert(company).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error adding company: {e}")
            return None
    
    def add_companies_bulk(self, companies: List[Dict]) -> int:
        """Bulk insert companies."""
        if not companies:
            return 0
        
        try:
            batch_size = 500
            inserted = 0
            
            for i in range(0, len(companies), batch_size):
                batch = companies[i:i + batch_size]
                result = self.client.table("companies").insert(batch).execute()
                inserted += len(result.data) if result.data else 0
            
            return inserted
        except Exception as e:
            print(f"Error bulk inserting: {e}")
            return 0
    
    def get_companies(self, active_only: bool = True, limit: int = 1000) -> List[Dict]:
        """Get companies."""
        query = self.client.table("companies").select("*")
        
        if active_only:
            query = query.eq("is_active", True)
        
        result = query.limit(limit).execute()
        return result.data or []
    
    def get_company_by_id(self, company_id: str) -> Optional[Dict]:
        """Get single company by UUID."""
        try:
            result = self.client.table("companies").select("*").eq("id", company_id).single().execute()
            return result.data
        except:
            return None
    
    def update_company(self, company_id: str, updates: Dict) -> bool:
        """Update company fields."""
        try:
            updates["updated_at"] = datetime.now().isoformat()
            self.client.table("companies").update(updates).eq("id", company_id).execute()
            return True
        except Exception as e:
            print(f"Error updating company: {e}")
            return False
    
    def delete_company(self, company_id: str) -> bool:
        """Delete company."""
        try:
            self.client.table("companies").delete().eq("id", company_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting company: {e}")
            return False
    
    # ========== JOBS ==========
    
    def add_job(self, job: Dict[str, Any]) -> Optional[Dict]:
        """Add job."""
        try:
            result = self.client.table("jobs").insert(job).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            if "duplicate" in str(e).lower():
                print(f"⚠️ Duplicate job skipped")
            else:
                print(f"Error adding job: {e}")
            return None
    
    def get_jobs(self, 
                 is_new: Optional[bool] = None,
                 is_recommended: Optional[bool] = None,
                 company_id: Optional[str] = None,
                 min_score: Optional[int] = None,
                 seen_within_days: int = 7,
                 limit: int = 100) -> List[Dict]:
        """Get jobs with filters."""
        query = self.client.table("jobs").select("*, companies(name, website)")
        
        if is_new is not None:
            query = query.eq("is_new", is_new)
        if is_recommended is not None:
            query = query.eq("is_recommended", is_recommended)
        if company_id:
            query = query.eq("company_id", company_id)
        if min_score:
            query = query.gte("match_score", min_score)
        
        # Exclude jobs seen in last N days
        cutoff_date = (datetime.now() - timedelta(days=seen_within_days)).strftime('%Y-%m-%d')
        query = query.gte("discovered_date", cutoff_date)
        
        result = query.order("discovered_at", desc=True).limit(limit).execute()
        return result.data or []
    
    def mark_job_action(self, job_id: str, action: str) -> bool:
        """Mark job as saved/applied/rejected/ignored."""
        valid_actions = ['saved', 'applied', 'rejected', 'ignored']
        if action not in valid_actions:
            return False
        
        try:
            self.client.table("jobs").update({
                "user_action": action,
                "is_new": False
            }).eq("id", job_id).execute()
            return True
        except Exception as e:
            print(f"Error marking job: {e}")
            return False
    
    # ========== SIGNALS ==========
    
    def add_signal(self, signal: Dict[str, Any]) -> Optional[Dict]:
        """Add raw signal."""
        try:
            result = self.client.table("signals").insert(signal).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error adding signal: {e}")
            return None
    
    def get_unprocessed_signals(self, limit: int = 100) -> List[Dict]:
        """Get signals awaiting processing."""
        result = (self.client.table("signals")
                  .select("*")
                  .eq("processed", False)
                  .order("confidence_score", desc=True)
                  .limit(limit)
                  .execute())
        return result.data or []
    
    def mark_signal_processed(self, signal_id: str, company_id: Optional[str] = None) -> bool:
        """Mark signal as processed."""
        try:
            updates = {"processed": True}
            if company_id:
                updates["company_id"] = company_id
            
            self.client.table("signals").update(updates).eq("id", signal_id).execute()
            return True
        except Exception as e:
            print(f"Error marking signal: {e}")
            return False
    
    # ========== SCRAPE QUEUE ==========
    
    def queue_company(self, company_id: str, priority: int = 5) -> bool:
        """Add company to scrape queue."""
        try:
            self.client.table("scrape_queue").insert({
                "company_id": company_id,
                "priority": priority,
                "status": "pending"
            }).execute()
            return True
        except Exception as e:
            print(f"Error queueing company: {e}")
            return False
    
    def get_pending_scrapes(self, limit: int = 10) -> List[Dict]:
        """Get pending scrape jobs."""
        result = (self.client.table("scrape_queue")
                  .select("*, companies(name, career_url, ats_type)")
                  .eq("status", "pending")
                  .order("priority", desc=True)
                  .order("scheduled_at")
                  .limit(limit)
                  .execute())
        return result.data or []
    
    def update_scrape_status(self, queue_id: str, status: str, error: str = None):
        """Update scrape job status."""
        updates = {
            "status": status,
            "completed_at": datetime.now().isoformat() if status in ['parsed', 'failed'] else None
        }
        if status == "scraping":
            updates["started_at"] = datetime.now().isoformat()
        if error:
            updates["error_message"] = error
        
        self.client.table("scrape_queue").update(updates).eq("id", queue_id).execute()

# Singleton instance
_db_instance = None

def get_db() -> Database:
    """Get or create database singleton."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance