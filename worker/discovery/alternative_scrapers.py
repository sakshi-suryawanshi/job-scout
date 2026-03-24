# worker/discovery/alternative_scrapers.py
import httpx
from typing import List, Dict
import feedparser
import json


class AlternativeScrapers:
    """Alternative sources for startup discovery"""
    
    def __init__(self):
        self.client = httpx.Client(timeout=30.0, follow_redirects=True)
    
    def fetch_wellfound(self, pages: int = 3) -> List[Dict]:
        """Fetch from Wellfound (formerly AngelList) - has RSS/API"""
        companies = []
        
        try:
            # Wellfound has public job listings
            url = "https://wellfound.com/api/jobs"
            # This requires auth, but we can use the public feed
            
            # Alternative: Use their public company list
            feed_url = "https://wellfound.com/startups/rss"
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries[:50]:
                companies.append({
                    "name": entry.get("title", "").split(" - ")[0],
                    "website": entry.get("link"),
                    "description": entry.get("summary", "")[:200],
                    "source_feed": "wellfound",
                })
            
        except Exception as e:
            print(f"Wellfound error: {e}")
        
        return companies
    
    def fetch_remoteok(self) -> List[Dict]:
        """Fetch companies from RemoteOK (has API)"""
        companies = []
        
        try:
            url = "https://remoteok.com/api"
            response = self.client.get(url)
            data = response.json()
            
            for job in data:
                company_name = job.get("company")
                if company_name:
                    companies.append({
                        "name": company_name,
                        "website": job.get("url", "").split("/jobs")[0] if "/jobs" in job.get("url", "") else None,
                        "is_hiring": True,
                        "source_feed": "remoteok",
                    })
            
        except Exception as e:
            print(f"RemoteOK error: {e}")
        
        return companies
    
    def fetch_we_work_remotely(self) -> List[Dict]:
        """Fetch from We Work Remotely"""
        companies = []
        
        try:
            import xml.etree.ElementTree as ET
            
            url = "https://weworkremotely.com/remote-jobs.rss"
            response = self.client.get(url)
            root = ET.fromstring(response.content)
            
            # Parse RSS
            for item in root.findall(".//item"):
                title = item.find("title")
                if title is not None:
                    # Title format: "Company: Job Title"
                    text = title.text
                    if ":" in text:
                        company_name = text.split(":")[0].strip()
                        companies.append({
                            "name": company_name,
                            "is_hiring": True,
                            "source_feed": "weworkremotely",
                        })
            
        except Exception as e:
            print(f"WWR error: {e}")
        
        return companies
    
    def to_db_format(self, company: Dict) -> Dict:
        """Convert to DB schema"""
        website = company.get("website")
        career_url = None
        
        if website:
            domain = website.replace("https://", "").replace("http://", "").rstrip("/")
            career_url = f"https://{domain}/careers"
        
        return {
            "name": company.get("name"),
            "career_url": career_url,
            "website": website,
            "ats_type": "unknown",
            "source": company.get("source_feed", "job_board"),
            "is_active": True,
            "notes": f"Hiring remote: {company.get('is_hiring')}" if company.get("is_hiring") else None,
            "priority_score": 8 if company.get("is_hiring") else 5,
        }


def fetch_alternative_sources() -> List[Dict]:
    """Fetch from all alternative sources"""
    scraper = AlternativeScrapers()
    
    all_companies = []
    
    print("Fetching from alternative sources...")
    
    sources = [
        ("Wellfound", scraper.fetch_wellfound),
        ("RemoteOK", scraper.fetch_remoteok),
        ("WeWorkRemotely", scraper.fetch_we_work_remotely),
    ]
    
    for name, func in sources:
        try:
            print(f"  → {name}...")
            companies = func()
            print(f"    Found {len(companies)}")
            all_companies.extend(companies)
        except Exception as e:
            print(f"    Failed: {e}")
    
    # Convert to DB format
    db_companies = [scraper.to_db_format(c) for c in all_companies]
    
    # Deduplicate by name
    seen = set()
    unique = []
    for c in db_companies:
        name = c["name"].lower()
        if name and name not in seen:
            seen.add(name)
            unique.append(c)
    
    print(f"✅ Total unique companies: {len(unique)}")
    return unique