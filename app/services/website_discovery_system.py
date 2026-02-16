#!/usr/bin/env python3
"""
Website Discovery and MCQ Collection System
Handles two cases:
1. New website discovery - collect and store all top/side URLs
2. Interactive MCQ scraping with customizable batch sizes
"""

import sys
sys.path.insert(0, '.')

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from app.database import get_session
from app.models.top_bar import TopBar
from app.models.side_bar import SideBar
from app.models.websites import Websites
from sqlmodel import select, text
import time
from typing import List, Dict, Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebsiteDiscoverySystem:
    """Handles website discovery and MCQ collection workflow"""
    
    def __init__(self):
        self.session = next(get_session())
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    def analyze_website(self, base_url: str) -> Dict:
        """
        Case 1: Analyze a website and collect all navigation URLs
        """
        print(f"🔍 ANALYZING WEBSITE: {base_url}")
        
        # Check if website already exists
        domain = urlparse(base_url).netloc
        existing_website = self.session.exec(
            select(Websites).where(Websites.base_url == base_url)
        ).first()
        
        if existing_website:
            print(f"✅ Website already exists in database: {existing_website.website_name}")
            return self._get_existing_urls(existing_website.id)
        
        # Discover new website
        print(f"🆕 NEW WEBSITE DISCOVERED - Starting URL collection...")
        return self._discover_new_website(base_url)
    
    def _discover_new_website(self, base_url: str) -> Dict:
        """Discover and store URLs from a new website"""
        try:
            # Get the main page
            response = requests.get(base_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract domain info
            domain = urlparse(base_url).netloc
            website_name = self._extract_website_name(soup, domain)
            
            # Create website record
            website = Websites(
                website_name=website_name,
                base_url=base_url,
                website_type=self._detect_website_type(domain),
                description=f"Auto-discovered website: {website_name}",
                is_active=True
            )
            self.session.add(website)
            self.session.commit()
            self.session.refresh(website)
            
            print(f"✅ Created website record: {website_name}")
            
            # Collect navigation URLs
            top_urls = self._collect_top_navigation(soup, base_url, website.id)
            side_urls = self._collect_side_navigation(soup, base_url, website.id)
            
            return {
                'website_id': website.id,
                'website_name': website_name,
                'top_urls': top_urls,
                'side_urls': side_urls,
                'total_urls': len(top_urls) + len(side_urls)
            }
            
        except Exception as e:
            logger.error(f"❌ Error discovering website: {e}")
            return {'error': str(e)}
    
    def _collect_top_navigation(self, soup: BeautifulSoup, base_url: str, website_id: int) -> List[Dict]:
        """Collect top navigation/menu URLs"""
        print("📋 Collecting TOP NAVIGATION URLs...")
        
        top_urls = []
        
        # Common selectors for top navigation
        nav_selectors = [
            'nav a', 'header a', '.navbar a', '.nav a', 
            '.menu a', '.top-menu a', '.main-nav a',
            'ul.nav a', '.navigation a'
        ]
        
        for selector in nav_selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                if href and self._is_valid_url(href, base_url):
                    full_url = urljoin(base_url, href)
                    title = link.get_text(strip=True) or link.get('title', '')
                    
                    if title and len(title) > 2:  # Filter out empty or very short titles
                        top_urls.append({
                            'url': full_url,
                            'title': title[:200],  # Limit title length
                            'website_id': website_id
                        })
        
        # Remove duplicates
        seen_urls = set()
        unique_top_urls = []
        for url_data in top_urls:
            if url_data['url'] not in seen_urls:
                seen_urls.add(url_data['url'])
                unique_top_urls.append(url_data)
        
        # Save to database
        for url_data in unique_top_urls:
            top_bar = TopBar(
                url=url_data['url'],
                title=url_data['title'],
                website_id=url_data['website_id']
            )
            self.session.add(top_bar)
        
        self.session.commit()
        print(f"✅ Collected {len(unique_top_urls)} top navigation URLs")
        return unique_top_urls
    
    def _collect_side_navigation(self, soup: BeautifulSoup, base_url: str, website_id: int) -> List[Dict]:
        """Collect sidebar/category URLs"""
        print("📋 Collecting SIDE NAVIGATION URLs...")
        
        side_urls = []
        
        # Common selectors for sidebar navigation
        sidebar_selectors = [
            '.sidebar a', '.side-menu a', '.categories a',
            '.category a', '.widget a', 'aside a',
            '.side-nav a', '.secondary-nav a'
        ]
        
        for selector in sidebar_selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                if href and self._is_valid_url(href, base_url):
                    full_url = urljoin(base_url, href)
                    section_title = link.get_text(strip=True) or link.get('title', '')
                    
                    if section_title and len(section_title) > 2:
                        side_urls.append({
                            'url': full_url,
                            'section_title': section_title[:200],
                            'website_id': website_id
                        })
        
        # Remove duplicates
        seen_urls = set()
        unique_side_urls = []
        for url_data in side_urls:
            if url_data['url'] not in seen_urls:
                seen_urls.add(url_data['url'])
                unique_side_urls.append(url_data)
        
        # Save to database
        for url_data in unique_side_urls:
            side_bar = SideBar(
                url=url_data['url'],
                section_title=url_data['section_title'],
                website_id=url_data['website_id']
            )
            self.session.add(side_bar)
        
        self.session.commit()
        print(f"✅ Collected {len(unique_side_urls)} side navigation URLs")
        return unique_side_urls
    
    def _get_existing_urls(self, website_id: int) -> Dict:
        """Get URLs from existing website"""
        top_urls = self.session.exec(
            select(TopBar).where(TopBar.website_id == website_id)
        ).all()
        
        side_urls = self.session.exec(
            select(SideBar).where(SideBar.website_id == website_id)
        ).all()
        
        website = self.session.exec(
            select(Websites).where(Websites.id == website_id)
        ).first()
        
        return {
            'website_id': website_id,
            'website_name': website.website_name if website else 'Unknown',
            'top_urls': [{'url': u.url, 'title': u.title} for u in top_urls],
            'side_urls': [{'url': u.url, 'section_title': u.section_title} for u in side_urls],
            'total_urls': len(top_urls) + len(side_urls)
        }
    
    def _detect_website_type(self, domain: str) -> str:
        """Detect website type from domain"""
        domain_lower = domain.lower()
        if 'testpoint' in domain_lower:
            return 'testpoint'
        elif 'pakmcqs' in domain_lower:
            return 'pakmcqs'
        elif 'mcqs' in domain_lower:
            return 'mcqs'
        else:
            return 'other'
    
    def show_collection_options(self, website_data: Dict) -> None:
        """
        Case 2: Show interactive options for MCQ collection
        """
        print(f"\n🎯 MCQ COLLECTION OPTIONS")
        print(f"📊 Website: {website_data.get('website_name', 'Unknown')}")
        print(f"📋 Total URLs available: {website_data['total_urls']}")
        print(f"   📄 Top navigation: {len(website_data['top_urls'])}")
        print(f"   📂 Side navigation: {len(website_data['side_urls'])}")
        
        print("\n🚀 COLLECTION OPTIONS:")
        print("1. 📄 Scrape from TOP navigation URLs (papers, tests)")
        print("2. 📂 Scrape from SIDE navigation URLs (categories)")
        print("3. 🎯 Scrape specific URL")
        print("4. 📊 Show all available URLs")
        print("5. ⚡ Quick scrape (5 URLs)")
        print("6. 🔄 Batch scrape (custom amount)")
        print("7. 🌟 Smart scrape (auto-detect best URLs)")
        
        choice = input("\n👉 Select option (1-7): ").strip()
        self._handle_collection_choice(choice, website_data)
    
    def _handle_collection_choice(self, choice: str, website_data: Dict) -> None:
        """Handle user's collection choice"""
        
        if choice == "1":
            self._scrape_top_urls(website_data)
        elif choice == "2":
            self._scrape_side_urls(website_data)
        elif choice == "3":
            self._scrape_specific_url()
        elif choice == "4":
            self._show_all_urls(website_data)
        elif choice == "5":
            self._quick_scrape(website_data)
        elif choice == "6":
            self._batch_scrape(website_data)
        elif choice == "7":
            self._smart_scrape(website_data)
        else:
            print("❌ Invalid choice. Please select 1-7.")
    
    def _quick_scrape(self, website_data: Dict) -> None:
        """Quick scrape - 5 best URLs"""
        print("\n⚡ QUICK SCRAPE - Top 5 URLs")
        
        # Combine and score URLs
        all_urls = []
        
        # Add top URLs with scoring
        for url_data in website_data['top_urls']:
            score = self._score_url_for_mcqs(url_data['title'], url_data['url'])
            all_urls.append({
                'url': url_data['url'],
                'title': url_data['title'],
                'type': 'top',
                'score': score
            })
        
        # Add side URLs with scoring
        for url_data in website_data['side_urls']:
            score = self._score_url_for_mcqs(url_data['section_title'], url_data['url'])
            all_urls.append({
                'url': url_data['url'],
                'title': url_data['section_title'],
                'type': 'side',
                'score': score
            })
        
        # Sort by score and take top 5
        all_urls.sort(key=lambda x: x['score'], reverse=True)
        top_5 = all_urls[:5]
        
        if not top_5:
            print("❌ No URLs available for quick scrape")
            return
        
        print(f"🎯 Selected 5 best URLs:")
        for i, url_data in enumerate(top_5, 1):
            print(f"   {i}. [{url_data['score']:.1f}] {url_data['title'][:50]}...")
        
        self._execute_scraping(top_5)
    
    def _batch_scrape(self, website_data: Dict) -> None:
        """Batch scrape with custom amount"""
        print("\n🔄 BATCH SCRAPE")
        
        all_urls = website_data['top_urls'] + website_data['side_urls']
        
        if not all_urls:
            print("❌ No URLs available")
            return
        
        count = self._get_scrape_count(len(all_urls))
        self._execute_scraping(all_urls[:count])
    
    def _scrape_specific_url(self) -> None:
        """Scrape a specific URL"""
        url = input("\n👉 Enter URL to scrape: ").strip()
        
        if not url:
            print("❌ No URL provided")
            return
        
        urls_to_scrape = [{'url': url, 'title': 'Custom URL'}]
        self._execute_scraping(urls_to_scrape)
    
    def _show_all_urls(self, website_data: Dict) -> None:
        """Show all available URLs"""
        print(f"\n📊 ALL URLS FOR: {website_data['website_name']}")
        
        print(f"\n📄 TOP NAVIGATION URLs ({len(website_data['top_urls'])}):")
        for i, url_data in enumerate(website_data['top_urls'], 1):
            print(f"   {i}. {url_data['title'][:60]}...")
            print(f"      🔗 {url_data['url']}")
        
        print(f"\n📂 SIDE NAVIGATION URLs ({len(website_data['side_urls'])}):")
        for i, url_data in enumerate(website_data['side_urls'], 1):
            print(f"   {i}. {url_data['section_title'][:60]}...")
            print(f"      🔗 {url_data['url']}")
        
        print(f"\n📋 Total: {website_data['total_urls']} URLs available")
    
    def _scrape_top_urls(self, website_data: Dict) -> None:
        """Scrape from top navigation URLs"""
        urls = website_data['top_urls']
        if not urls:
            print("❌ No top navigation URLs available")
            return
        
        print(f"\n📄 TOP NAVIGATION URLs ({len(urls)} available):")
        for i, url_data in enumerate(urls[:10], 1):  # Show first 10
            print(f"  {i}. {url_data['title'][:60]}...")
        
        if len(urls) > 10:
            print(f"  ... and {len(urls) - 10} more")
        
        count = self._get_scrape_count(len(urls))
        self._execute_scraping(urls[:count])
    
    def _scrape_side_urls(self, website_data: Dict) -> None:
        """Scrape from side navigation URLs"""
        urls = website_data['side_urls']
        if not urls:
            print("❌ No side navigation URLs available")
            return
        
        print(f"\n📂 SIDE NAVIGATION URLs ({len(urls)} available):")
        for i, url_data in enumerate(urls[:10], 1):
            print(f"  {i}. {url_data['section_title'][:60]}...")
        
        if len(urls) > 10:
            print(f"  ... and {len(urls) - 10} more")
        
        count = self._get_scrape_count(len(urls))
        self._execute_scraping(urls[:count])
    
    def _get_scrape_count(self, max_available: int) -> int:
        """Get number of URLs to scrape from user"""
        while True:
            try:
                response = input(f"\n👉 How many URLs to scrape? (1-{max_available}, default=5): ").strip()
                
                if not response:
                    return min(5, max_available)
                
                count = int(response)
                if 1 <= count <= max_available:
                    return count
                else:
                    print(f"❌ Please enter a number between 1 and {max_available}")
            except ValueError:
                print("❌ Please enter a valid number")
    
    def _execute_scraping(self, urls_to_scrape: List[Dict]) -> None:
        """Execute MCQ scraping for selected URLs"""
        print(f"\n🚀 STARTING MCQ COLLECTION for {len(urls_to_scrape)} URLs...")
        
        for i, url_data in enumerate(urls_to_scrape, 1):
            url = url_data['url']
            title = url_data.get('title') or url_data.get('section_title', 'Unknown')
            
            print(f"\n📖 [{i}/{len(urls_to_scrape)}] Scraping: {title[:50]}...")
            print(f"🔗 URL: {url}")
            
            # Import and run collector
            try:
                import subprocess
                import sys
                
                cmd = [
                    sys.executable, "-m", 
                    "app.services.scrapper.paper_mcqs_collector_v1",
                    url
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, cwd='.')
                
                if result.returncode == 0:
                    print("✅ SUCCESS")
                    # Extract MCQ count from output if possible
                    if "MCQs" in result.stdout:
                        print(f"📊 {result.stdout.split('MCQs')[0].split()[-1]} MCQs collected")
                else:
                    print(f"❌ FAILED: {result.stderr[:100]}...")
                
            except Exception as e:
                print(f"❌ ERROR: {e}")
            
            # Brief pause between requests
            time.sleep(1)
        
        print(f"\n🎉 COMPLETED! Processed {len(urls_to_scrape)} URLs")
    
    def _smart_scrape(self, website_data: Dict) -> None:
        """Smart scraping - automatically detect best URLs"""
        print("\n🌟 SMART SCRAPE - Auto-detecting best URLs for MCQ collection...")
        
        # Combine and score URLs
        all_urls = []
        
        # Add top URLs with scoring
        for url_data in website_data['top_urls']:
            score = self._score_url_for_mcqs(url_data['title'], url_data['url'])
            all_urls.append({
                'url': url_data['url'],
                'title': url_data['title'],
                'type': 'top',
                'score': score
            })
        
        # Add side URLs with scoring
        for url_data in website_data['side_urls']:
            score = self._score_url_for_mcqs(url_data['section_title'], url_data['url'])
            all_urls.append({
                'url': url_data['url'],
                'title': url_data['section_title'],
                'type': 'side',
                'score': score
            })
        
        # Sort by score (highest first)
        all_urls.sort(key=lambda x: x['score'], reverse=True)
        
        # Show top candidates
        top_candidates = all_urls[:10]
        print(f"\n🎯 TOP MCQ CANDIDATES (scored by relevance):")
        for i, url_data in enumerate(top_candidates, 1):
            print(f"  {i}. [{url_data['score']:.1f}] {url_data['title'][:60]}...")
            print(f"     🔗 {url_data['url'][:80]}...")
        
        count = self._get_scrape_count(len(top_candidates))
        self._execute_scraping(top_candidates[:count])
    
    def _score_url_for_mcqs(self, title: str, url: str) -> float:
        """Score URL for MCQ relevance"""
        score = 0.0
        title_lower = title.lower()
        url_lower = url.lower()
        
        # High value keywords
        if any(word in title_lower for word in ['mcq', 'mcqs', 'test', 'quiz', 'paper', 'exam']):
            score += 3.0
        
        # Medium value keywords  
        if any(word in title_lower for word in ['past', 'previous', 'sample', 'practice']):
            score += 2.0
        
        # URL patterns
        if any(pattern in url_lower for pattern in ['mcq', 'test', 'paper', 'quiz']):
            score += 2.0
        
        # Avoid low-value pages
        if any(word in title_lower for word in ['home', 'about', 'contact', 'privacy']):
            score -= 1.0
        
        return score
    
    def _is_valid_url(self, href: str, base_url: str) -> bool:
        """Check if URL is valid for collection"""
        if not href:
            return False
        
        # Skip javascript, mailto, tel links
        if href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
            return False
        
        # Skip external domains (keep only same domain)
        if href.startswith('http') and urlparse(base_url).netloc not in href:
            return False
        
        return True
    
    def _extract_website_name(self, soup: BeautifulSoup, domain: str) -> str:
        """Extract website name from page"""
        # Try to get from title tag
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
            if title and len(title) > 5:
                return title[:100]
        
        # Try to get from h1
        h1_tag = soup.find('h1')
        if h1_tag:
            h1_text = h1_tag.get_text(strip=True)
            if h1_text and len(h1_text) > 3:
                return h1_text[:100]
        
        # Fallback to domain
        return domain.replace('www.', '').replace('.com', '').title()

def main():
    """Main interface for website discovery system"""
    if len(sys.argv) < 2:
        print("❌ Usage: python website_discovery_system.py <website_url>")
        print("📖 Example: python website_discovery_system.py https://testpointpk.com")
        return
    
    website_url = sys.argv[1]
    
    # Initialize system
    discovery = WebsiteDiscoverySystem()
    
    # Case 1: Analyze website and collect URLs
    website_data = discovery.analyze_website(website_url)
    
    if 'error' in website_data:
        print(f"❌ Error: {website_data['error']}")
        return
    
    # Case 2: Show collection options
    discovery.show_collection_options(website_data)

if __name__ == "__main__":
    main()
