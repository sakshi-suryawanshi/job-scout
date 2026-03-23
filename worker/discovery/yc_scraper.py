# worker/discovery/yc_scraper.py
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import re
import time


class YCScraper:
    BASE_URL = "https://www.ycombinator.com/companies"
    
    def __init__(self):
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0"
            },
            timeout=30.0,
            follow_redirects=True
        )
    
    def fetch_companies(self, batch: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        Fetch companies from YC directory.
        
        Args:
            batch: Specific batch like "W24", "S23", or None for recent
            limit: Max companies to fetch (YC pages have ~100 each)
        """
        companies = []
        page = 1
        
        while len(companies) < limit:
            url = self._build_url(batch, page)
            print(f"Fetching: {url}")
            
            try:
                response = self.client.get(url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                page_companies = self._parse_page(soup)
                
                if not page_companies:
                    break  # No more results
                
                companies.extend(page_companies)
                print(f"Found {len(page_companies)} companies on page {page}")
                
                # Be nice to YC servers
                time.sleep(1)
                page += 1
                
            except Exception as e:
                print(f"Error fetching page {page}: {e}")
                break
        
        return companies[:limit]
    
    def _build_url(self, batch: Optional[str], page: int) -> str:
        """Build paginated URL."""
        url = self.BASE_URL
        
        params = []
        if batch:
            params.append(f"batch={batch}")
        if page > 1:
            params.append(f"page={page}")
        
        if params:
            url += "?" + "&".join(params)
        
        return url
    
    def _parse_page(self, soup: BeautifulSoup) -> List[Dict]:
        """Parse company cards from HTML."""
        companies = []
        
        # YC uses different selectors - try multiple patterns
        selectors = [
            'a[href^="/companies/"]',  # New format
            '.company-card',             # Old format
            '[data-testid="company-card"]',
            '.flex-row a'                # Generic fallback
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            print(f"Trying selector '{selector}': found {len(elements)}")
            
            if elements:
                for elem in elements:
                    company = self._parse_company_element(elem, soup)
                    if company and company.get('name'):
                        companies.append(company)
                
                if companies:
                    break  # Found working selector
        
        # Deduplicate by name
        seen = set()
        unique = []
        for c in companies:
            name = c.get('name', '').lower()
            if name and name not in seen:
                seen.add(name)
                unique.append(c)
        
        return unique
    
    def _parse_company_element(self, elem, soup) -> Optional[Dict]:
        """Extract company data from HTML element."""
        try:
            # Try to find name
            name = None
            for selector in ['h3', 'h4', '.company-name', '[data-testid="company-name"]', 'span']:
                name_elem = elem.select_one(selector)
                if name_elem:
                    name = name_elem.get_text(strip=True)
                    if name and len(name) > 1:
                        break
            
            if not name:
                # Try from link text
                name = elem.get_text(strip=True)
            
            # Clean name
            name = re.sub(r'\s+', ' ', name).strip()
            if not name or len(name) < 2:
                return None
            
            # Get URL
            href = elem.get('href', '')
            if href.startswith('/'):
                yc_url = f"https://www.ycombinator.com{href}"
            elif 'ycombinator.com/companies/' in href:
                yc_url = href
            else:
                yc_url = None
            
            # Extract slug from URL
            slug = None
            if yc_url:
                match = re.search(r'/companies/([^/]+)', yc_url)
                if match:
                    slug = match.group(1)
            
            # Try to find description
            description = None
            parent = elem.parent
            for _ in range(3):  # Look up 3 levels
                if parent:
                    desc_elem = parent.select_one('.description, p, [data-testid="description"]')
                    if desc_elem:
                        description = desc_elem.get_text(strip=True)
                        break
                    parent = parent.parent
            
            # Try to find website
            website = None
            if yc_url:
                # We'll need to fetch detail page for website
                pass
            
            return {
                "name": name,
                "slug": slug,
                "yc_url": yc_url,
                "description": description,
                "batch": None,  # Will fill from detail page or context
                "status": "active",  # Assume active if in directory
            }
            
        except Exception as e:
            print(f"Error parsing element: {e}")
            return None
    
    def enrich_company(self, company: Dict) -> Dict:
        """Fetch detail page to get website, batch, etc."""
        if not company.get('yc_url'):
            return company
        
        try:
            response = self.client.get(company['yc_url'])
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract website
            website = None
            for selector in ['a[href^="http"]', '.website', '[data-testid="website"]']:
                link = soup.select_one(selector)
                if link:
                    href = link.get('href', '')
                    if href and 'ycombinator.com' not in href:
                        website = href
                        break
            
            # Extract batch from URL or page
            batch = None
            batch_elem = soup.select_one('.batch, [data-testid="batch"]')
            if batch_elem:
                batch = batch_elem.get_text(strip=True)
            elif company.get('slug'):
                # Try to infer from slug pattern
                match = re.search(r'-([WS]\d{2})$', company['slug'])
                if match:
                    batch = match.group(1)
            
            # Extract headcount if available
            headcount = None
            text = soup.get_text()
            match = re.search(r'(\d+)\s*employees', text, re.I)
            if match:
                headcount = int(match.group(1))
            
            company.update({
                "website": website,
                "batch": batch,
                "headcount": headcount,
            })
            
        except Exception as e:
            print(f"Error enriching {company.get('name')}: {e}")
        
        return company
    
    def to_db_format(self, company: Dict) -> Dict:
        """Convert to database schema."""
        # Guess career URL from website
        career_url = None
        if company.get('website'):
            domain = company['website'].replace('https://', '').replace('http://', '').rstrip('/')
            career_url = f"https://{domain}/careers"
        
        # Determine funding stage from batch
        funding_stage = None
        batch = company.get('batch', '')
        if batch:
            # Recent batches are likely seed/series A
            year = 2000 + int(batch[1:]) if len(batch) >= 2 and batch[1:].isdigit() else 2024
            if year >= 2023:
                funding_stage = "seed"
            elif year >= 2021:
                funding_stage = "series_a"
        
        return {
            "name": company.get('name'),
            "career_url": career_url,
            "website": company.get('website'),
            "ats_type": "unknown",
            "funding_stage": funding_stage,
            "headcount": company.get('headcount'),
            "source": "yc_directory",
            "is_active": True,
            "notes": f"YC Batch: {batch}" if batch else None,
            "priority_score": 10 if funding_stage in ['seed', 'pre-seed'] else 5,
        }


def fetch_yc_companies(batch: Optional[str] = None, limit: int = 100, enrich: bool = True) -> List[Dict]:
    """Convenience function to fetch and format YC companies."""
    scraper = YCScraper()
    
    print(f"Fetching YC companies (batch={batch}, limit={limit})...")
    raw = scraper.fetch_companies(batch=batch, limit=limit)
    print(f"Found {len(raw)} raw companies")
    
    if enrich:
        print("Enriching company details...")
        enriched = []
        for i, company in enumerate(raw):
            if i % 10 == 0:
                print(f"Enriched {i}/{len(raw)}...")
            enriched.append(scraper.enrich_company(company))
            time.sleep(0.5)  # Be polite
        raw = enriched
    
    # Convert to DB format
    db_companies = [scraper.to_db_format(c) for c in raw]
    
    # Filter valid entries
    valid = [c for c in db_companies if c.get('name') and c.get('career_url')]
    
    print(f"Returning {len(valid)} valid companies")
    return valid


if __name__ == "__main__":
    # Test
    companies = fetch_yc_companies(batch="W24", limit=20)
    for c in companies[:5]:
        print(f"- {c['name']} ({c.get('career_url')})")