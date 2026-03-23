# worker/discovery/ph_scraper.py
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import re
import time


class ProductHuntScraper:
    BASE_URL = "https://www.producthunt.com"
    
    # Topics that indicate B2B/SaaS companies likely to hire developers
    RELEVANT_TOPICS = [
        "developer-tools",
        "saas",
        "b2b",
        "artificial-intelligence",
        "productivity",
        "api",
        "automation",
        "open-source",
        "fintech",
        "healthcare",
    ]
    
    def __init__(self):
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=30.0,
            follow_redirects=True,
        )
    
    def fetch_from_topic(self, topic: str, pages: int = 3) -> List[Dict]:
        """Fetch products from a specific topic."""
        companies = []
        
        for page in range(1, pages + 1):
            url = f"{self.BASE_URL}/topics/{topic}?page={page}"
            print(f"Fetching: {url}")
            
            try:
                response = self.client.get(url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                products = self._parse_products(soup)
                
                print(f"Found {len(products)} products on page {page}")
                companies.extend(products)
                
                time.sleep(1.5)  # Be nice to PH
                
            except Exception as e:
                print(f"Error fetching {url}: {e}")
                continue
        
        return companies
    
    def fetch_recent(self, pages: int = 5) -> List[Dict]:
        """Fetch recent popular products."""
        companies = []
        
        for page in range(1, pages + 1):
            url = f"{self.BASE_URL}/all?page={page}"
            print(f"Fetching: {url}")
            
            try:
                response = self.client.get(url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                products = self._parse_products(soup)
                
                print(f"Found {len(products)} products on page {page}")
                companies.extend(products)
                
                time.sleep(1.5)
                
            except Exception as e:
                print(f"Error: {e}")
                continue
        
        return companies
    
    def _parse_products(self, soup: BeautifulSoup) -> List[Dict]:
        """Parse product cards from HTML."""
        products = []
        
        # PH uses various selectors
        selectors = [
            '[data-testid="product-item"]',
            '.styles_item__D1_wC',
            '[data-test^="post-"]',
            'a[href^="/products/"]',
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            print(f"Selector '{selector}': {len(elements)} matches")
            
            for elem in elements:
                product = self._parse_product_element(elem)
                if product and product.get('name'):
                    products.append(product)
            
            if len(products) > 5:
                break  # Found working selector
        
        # Deduplicate
        seen = set()
        unique = []
        for p in products:
            name = p.get('name', '').lower()
            if name and name not in seen:
                seen.add(name)
                unique.append(p)
        
        return unique
    
    def _parse_product_element(self, elem) -> Optional[Dict]:
        """Extract product data from element."""
        try:
            # Get name
            name = None
            for selector in ['h2', 'h3', '.styles_title__', '[data-testid="product-name"]', 'a']:
                name_elem = elem.select_one(selector)
                if name_elem:
                    name = name_elem.get_text(strip=True)
                    if name and len(name) > 1 and not name.startswith('http'):
                        break
            
            if not name:
                return None
            
            # Clean name
            name = re.sub(r'\s+', ' ', name).strip()
            
            # Get product URL
            href = elem.get('href', '')
            if not href:
                link = elem.select_one('a[href^="/products/"]')
                if link:
                    href = link.get('href', '')
            
            if href.startswith('/'):
                product_url = f"{self.BASE_URL}{href}"
            elif 'producthunt.com/products/' in href:
                product_url = href
            else:
                product_url = None
            
            # Extract slug
            slug = None
            if product_url:
                match = re.search(r'/products/([^/?]+)', product_url)
                if match:
                    slug = match.group(1)
            
            # Get tagline/description
            tagline = None
            for selector in ['p', '.styles_tagline__', '[data-testid="tagline"]', '.text-gray-600']:
                tag_elem = elem.select_one(selector)
                if tag_elem:
                    tagline = tag_elem.get_text(strip=True)
                    if tagline and len(tagline) > 5:
                        break
            
            # Get votes/counts as popularity signal
            votes = 0
            vote_elem = elem.select_one('[data-testid="vote-button"], .styles_voteCount__')
            if vote_elem:
                text = vote_elem.get_text(strip=True)
                match = re.search(r'(\d+)', text.replace('K', '000').replace('.', ''))
                if match:
                    votes = int(match.group(1))
            
            return {
                "name": name,
                "slug": slug,
                "product_url": product_url,
                "tagline": tagline,
                "votes": votes,
                "topic": None,  # Will be set by caller
            }
            
        except Exception as e:
            print(f"Error parsing product: {e}")
            return None
    
    def enrich_product(self, product: Dict) -> Dict:
        """Fetch product detail page for website link."""
        if not product.get('product_url'):
            return product
        
        try:
            response = self.client.get(product['product_url'])
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find website link
            website = None
            for selector in [
                'a[href^="http"]:not([href*="producthunt.com"])',
                '[data-testid="website-link"]',
                'a:contains("Visit")',
                '.styles_website__'
            ]:
                link = soup.select_one(selector)
                if link:
                    href = link.get('href', '')
                    if href and 'producthunt.com' not in href:
                        website = href
                        break
            
            # If not found, look for text patterns
            if not website:
                text = soup.get_text()
                patterns = [
                    r'Visit\s+([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
                    r'Website:\s*(https?://\S+)',
                ]
                for pattern in patterns:
                    match = re.search(pattern, text)
                    if match:
                        website = match.group(1)
                        if not website.startswith('http'):
                            website = f"https://{website}"
                        break
            
            # Get maker info (team size signal)
            makers = []
            maker_elems = soup.select('[data-testid="maker"], .styles_maker__')
            for m in maker_elems:
                name = m.get_text(strip=True)
                if name:
                    makers.append(name)
            
            product.update({
                "website": website,
                "makers_count": len(makers),
                "makers": makers[:5],  # Top 5
            })
            
        except Exception as e:
            print(f"Error enriching {product.get('name')}: {e}")
        
        return product
    
    def to_db_format(self, product: Dict) -> Dict:
        """Convert to database schema."""
        # Guess career URL
        career_url = None
        if product.get('website'):
            domain = product['website'].replace('https://', '').replace('http://', '').rstrip('/')
            career_url = f"https://{domain}/careers"
        
        # Priority based on votes (popularity = likely hiring)
        votes = product.get('votes', 0)
        priority = 5
        if votes > 500:
            priority = 15
        elif votes > 100:
            priority = 10
        
        # Estimate headcount from makers
        headcount = None
        makers = product.get('makers_count', 0)
        if makers > 0:
            headcount = makers * 3  # Rough estimate: 3x makers
        
        return {
            "name": product.get('name'),
            "career_url": career_url,
            "website": product.get('website'),
            "ats_type": "unknown",
            "headcount": headcount,
            "source": "product_hunt",
            "is_active": True,
            "notes": f"PH: {product.get('tagline', '')[:100]}" if product.get('tagline') else None,
            "priority_score": priority,
        }


def fetch_ph_companies(topic: Optional[str] = None, pages: int = 3, enrich: bool = True) -> List[Dict]:
    """Convenience function to fetch Product Hunt companies."""
    scraper = ProductHuntScraper()
    
    if topic:
        print(f"Fetching PH companies from topic: {topic}")
        raw = scraper.fetch_from_topic(topic, pages=pages)
    else:
        print("Fetching recent PH products...")
        raw = scraper.fetch_recent(pages=pages)
    
    print(f"Found {len(raw)} raw products")
    
    if enrich:
        print("Enriching product details...")
        enriched = []
        for i, product in enumerate(raw):
            if i % 5 == 0:
                print(f"Enriched {i}/{len(raw)}...")
            enriched.append(scraper.enrich_product(product))
            time.sleep(0.5)
        raw = enriched
    
    # Convert to DB format
    db_companies = [scraper.to_db_format(p) for p in raw]
    
    # Filter valid
    valid = [c for c in db_companies if c.get('name') and c.get('career_url')]
    
    print(f"Returning {len(valid)} valid companies")
    return valid


if __name__ == "__main__":
    # Test
    companies = fetch_ph_companies(topic="developer-tools", pages=2)
    for c in companies[:5]:
        print(f"- {c['name']} ({c.get('career_url')}) - Priority: {c.get('priority_score')}")