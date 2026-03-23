# test_db_helpers.py
from db import get_db

def test_helpers():
    db = get_db()
    
    # Test company CRUD
    print("Testing company CRUD...")
    
    company = {
        "name": "Wassha Inc",
        "career_url": "https://wassha.com/careers",
        "ats_type": "custom",
        "regions": ["africa", "asia"],
        "source": "manual",
        "notes": "Japanese company in Africa, hidden gem"
    }
    
    created = db.add_company(company)
    print(f"✅ Created: {created['id']}")
    
    # Test job
    print("Testing job add...")
    job = {
        "company_id": created['id'],
        "title": "Senior Backend Engineer",
        "location": "Remote (Africa/Asia)",
        "is_remote": True,
        "remote_type": "region_specific",
        "apply_url": "https://wassha.com/apply/123",
        "source_board": "company_site",
        "match_score": 85
    }
    
    job_created = db.add_job(job)
    print(f"✅ Job created: {job_created['id'] if job_created else 'duplicate skipped'}")
    
    # Test duplicate prevention
    job2 = db.add_job(job)
    print(f"✅ Duplicate handled: {job2 is None}")
    
    # Test query
    jobs = db.get_jobs()
    print(f"✅ Found {len(jobs)} jobs")
    
    # Cleanup
    db.delete_company(created['id'])
    print("✅ Cleanup done")

if __name__ == "__main__":
    test_helpers()