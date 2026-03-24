# worker/discovery/yc_scraper_v2.py
import httpx
import json
import re
from typing import List, Dict, Optional
from datetime import datetime


class YCScraperV2:
    """Fetch YC companies from GitHub repo and JSON sources"""
    
    # Public datasets
    SOURCES = [
        "https://raw.githubusercontent.com/lennysan/yc-companies/main/yc_companies.json",
        "https://api.ycombinator.com/v0.1/companies",  # Unofficial but works
    ]
    
    def __init__(self):
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            },
            timeout=30.0,
            follow_redirects=True
        )
    
    def fetch_from_github(self) -> List[Dict]:
        """Fetch from curated GitHub datasets"""
        companies = []
        
        # Primary source: yclist.com API (unofficial but reliable)
        try:
            url = "https://yclist.com/api/companies"
            response = self.client.get(url)
            response.raise_for_status()
            data = response.json()
            
            for item in data:
                company = {
                    "name": item.get("name"),
                    "website": item.get("url"),
                    "batch": item.get("batch"),
                    "status": item.get("status"),
                    "description": item.get("description"),
                }
                companies.append(company)
            
            print(f"✅ Fetched {len(companies)} from yclist.com")
            
        except Exception as e:
            print(f"⚠️ yclist failed: {e}")
        
        # Fallback: Direct YC API (if available)
        if not companies:
            companies = self._fetch_from_yc_api()
        
        return companies
    
    def _fetch_from_yc_api(self) -> List[Dict]:
        """Try alternative sources"""
        companies = []
        
        # Scrape the directory page with proper headers (some pages still work)
        try:
            url = "https://www.ycombinator.com/companies"
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Cache-Control": "max-age=0",
            }
            
            response = self.client.get(url, headers=headers)
            print(f"YC status: {response.status_code}")
            
            # Extract JSON data from page if present
            text = response.text
            
            # Look for JSON data in script tags
            json_pattern = r'window\.__INITIAL_STATE__\s*=\s*({.+?});'
            match = re.search(json_pattern, text, re.DOTALL)
            
            if match:
                data = json.loads(match.group(1))
                # Parse the JSON structure
                print("Found initial state data")
                # ... parse according to structure
            
            # Fallback: extract from HTML with regex
            company_pattern = r'"name":"([^"]+)","slug":"([^"]+)","batch":"([^"]*)"'
            matches = re.findall(company_pattern, text)
            
            for name, slug, batch in matches:
                companies.append({
                    "name": name,
                    "slug": slug,
                    "batch": batch,
                    "website": f"https://www.ycombinator.com/companies/{slug}",
                })
            
        except Exception as e:
            print(f"⚠️ YC API failed: {e}")
        
        return companies
    
    def fetch_by_batch(self, batch: str) -> List[Dict]:
        """Fetch specific batch from known lists"""
        all_companies = self.fetch_from_github()
        
        # Filter by batch
        filtered = [c for c in all_companies if c.get("batch") == batch]
        
        print(f"Filtered {len(filtered)} companies from batch {batch}")
        return filtered
    
    def to_db_format(self, company: Dict) -> Dict:
        """Convert to database schema"""
        # Build career URL from website
        career_url = None
        website = company.get("website") or company.get("url")
        
        if website:
            # Clean domain
            domain = website.replace("https://", "").replace("http://", "").rstrip("/")
            if "." in domain:
                career_url = f"https://{domain}/careers"
        
        # Determine funding stage from batch
        funding_stage = None
        batch = company.get("batch", "")
        
        if batch:
            # Extract year from batch (e.g., W24 -> 2024)
            try:
                year = 2000 + int(batch[1:]) if len(batch) >= 2 else 2024
                if year >= 2024:
                    funding_stage = "seed"
                elif year >= 2022:
                    funding_stage = "series_a"
                else:
                    funding_stage = "series_b"
            except:
                funding_stage = "seed"
        
        return {
            "name": company.get("name"),
            "career_url": career_url,
            "website": website,
            "ats_type": "unknown",
            "funding_stage": funding_stage,
            "source": "yc_directory",
            "is_active": True,
            "notes": f"YC Batch: {batch}, Status: {company.get('status', 'active')}" if batch else None,
            "priority_score": 10 if funding_stage in ["seed", "pre-seed"] else 5,
        }


def fetch_yc_companies_v2(batch: Optional[str] = None, limit: int = 100) -> List[Dict]:
    """Convenience function"""
    scraper = YCScraperV2()
    
    if batch:
        raw = scraper.fetch_by_batch(batch)
    else:
        raw = scraper.fetch_from_github()
    
    # Convert to DB format
    db_companies = [scraper.to_db_format(c) for c in raw]
    
    # Filter valid
    valid = [c for c in db_companies if c.get("name") and c.get("career_url")]
    
    print(f"✅ Returning {len(valid)} valid companies (requested limit: {limit})")
    return valid[:limit]