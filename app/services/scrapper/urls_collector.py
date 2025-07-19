from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import requests
from bs4 import BeautifulSoup
from sqlmodel import Session, create_engine, select
from .top_urls import WebsiteTopService
from .side_urls import WebsiteSideService
from ...models.website import Website, WebsiteCreate
from ...models.websites import Websites, WebsitesCreate
from ...models.top_bar import TopBar, TopBarCreate
from ...models.side_bar import SideBar, SideBarCreate
from ...database import get_session

@dataclass
class UrlsCollector:
    """
    A dataclass-based web scraper that extracts various tags like title, meta, images, links, tables, and more.
    Also handles database insertion for websites and website tables.
    """
    url: str
    
    session: requests.Session = field(default_factory=requests.Session)
    headers: Dict[str, str] = field(default_factory=lambda: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    top_service: WebsiteTopService = field(init=False)
    side_service: WebsiteSideService = field(init=False)
    db_session: Optional[Session] = field(init=False, default=None)
    
    def __post_init__(self):
        """Initialize services with the URL after object creation."""
        self.top_service = WebsiteTopService(urls=[self.url])
        self.side_service = WebsiteSideService(urls=[self.url])
        self.db_session = next(get_session())  # Get the actual session from the generator
    
    def _detect_website_type(self, url: str) -> str:
        """Detect the website type based on the URL."""
        if 'pakmcqs.com' in url:
            return 'pakmcqs'
        elif 'testpointpk.com' in url:
            return 'testpoint'
        else:
            return 'unknown'
    
    def _get_website_name(self, url: str) -> str:
        """Extract website name from URL."""
        if 'pakmcqs.com' in url:
            return 'PakMcqs'
        elif 'testpointpk.com' in url:
            return 'TestPoint'
        else:
            return 'Unknown'
    
    def _get_base_url(self, url: str) -> str:
        """Extract base URL from full URL."""
        if 'pakmcqs.com' in url:
            return 'https://pakmcqs.com'
        elif 'testpointpk.com' in url:
            return 'https://testpointpk.com'
        else:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
    
    def _ensure_website_exists(self, url: str) -> int:
        """
        Ensure the website exists in the websites table and return its ID.
        """
        website_type = self._detect_website_type(url)
        website_name = self._get_website_name(url)
        base_url = self._get_base_url(url)
        
        # Check if website already exists
        stmt = select(Websites).where(Websites.base_url == base_url)
        existing_website = self.db_session.exec(stmt).first()
        
        if existing_website:
            return existing_website.id
        
        # Create new website record
        new_website = Websites(
            website_name=website_name,
            base_url=base_url,
            website_type=website_type,
            description=f"Auto-generated entry for {website_name}",
            is_active=True
        )
        
        self.db_session.add(new_website)
        self.db_session.commit()
        self.db_session.refresh(new_website)
        
        return new_website.id
    
    def _merge_all_urls(self, top_data: Dict[str, Any], side_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Merge all URLs from top and sidebar data with is_scraped field.
        """
        merged_urls = []
        
        # Process top URLs
        if top_data.get('success') and 'urls' in top_data:
            for url_item in top_data['urls']:
                merged_urls.append({
                    'title': url_item.get('title', 'Unknown'),
                    'url': url_item.get('url', ''),
                    'source': 'top_bar',
                    'section': 'main_content',
                    'is_scraped': False
                })
        
        # Process sidebar URLs
        if side_data.get('success') and 'sections' in side_data:
            for section in side_data['sections']:
                section_title = section.get('section_title', 'Unknown Section')
                for url_item in section.get('urls', []):
                    merged_urls.append({
                        'title': url_item.get('title', 'Unknown'),
                        'url': url_item.get('url', ''),
                        'source': 'sidebar',
                        'section': section_title,
                        'is_scraped': False
                    })
        
        return merged_urls
    
    def _save_top_bar_data(self, top_data: Dict[str, Any], website_id: int) -> Dict[str, Any]:
        """
        Save top bar data to the top_bar table (one record per URL).
        Skip URLs that already exist in the database.
        """
        try:
            if not top_data.get('success') or not top_data.get('urls'):
                return {'success': False, 'message': 'No top bar data to save'}
            
            saved_records = []
            skipped_records = []
            
            # Create one record for each URL
            for url_item in top_data['urls']:
                url_value = url_item.get('url', '')
                name_value = url_item.get('title', 'Unknown')
                
                if not url_value:  # Skip empty URLs
                    continue
                
                # Check if URL already exists in top_bar table
                existing_stmt = select(TopBar).where(TopBar.url == url_value)
                existing_record = self.db_session.exec(existing_stmt).first()
                
                if existing_record:
                    skipped_records.append({
                        'url': url_value,
                        'name': name_value,
                        'reason': 'already exists skipping',
                        'existing_id': existing_record.id
                    })
                    continue
                
                # Create individual top bar record
                top_bar_record = TopBar(
                    title="Top Bar URL",  # Generic title for top bar items
                    name=name_value,
                    url=url_value,
                    website_id=website_id
                )
                
                self.db_session.add(top_bar_record)
                self.db_session.commit()
                self.db_session.refresh(top_bar_record)
                
                saved_records.append({
                    'id': top_bar_record.id,
                    'name': name_value,
                    'url': url_value
                })
            
            return {
                'success': True,
                'total_records': len(saved_records),
                'total_skipped': len(skipped_records),
                'records': saved_records,
                'skipped': skipped_records
            }
            
        except Exception as e:
            self.db_session.rollback()
            return {
                'success': False,
                'error': f"Top bar insertion failed: {str(e)}"
            }
    
    def _save_side_bar_data(self, side_data: Dict[str, Any], website_id: int) -> Dict[str, Any]:
        """
        Save side bar data to the side_bar table (one record per URL).
        Skip URLs that already exist in the database.
        """
        try:
            if not side_data.get('success') or not side_data.get('sections'):
                return {'success': False, 'message': 'No sidebar data to save'}
            
            saved_records = []
            skipped_records = []
            section_summary = []
            
            for section in side_data['sections']:
                section_title = section.get('section_title', 'Unknown Section')
                section_urls = section.get('urls', [])
                
                if not section_urls:
                    continue
                
                section_records = []
                section_skipped = []
                
                # Create one record for each URL in the section
                for url_item in section_urls:
                    url_value = url_item.get('url', '')
                    name_value = url_item.get('title', 'Unknown')
                    
                    if not url_value:  # Skip empty URLs
                        continue
                    
                    # Check if URL already exists in side_bar table
                    existing_stmt = select(SideBar).where(SideBar.url == url_value)
                    existing_record = self.db_session.exec(existing_stmt).first()
                    
                    if existing_record:
                        skip_info = {
                            'url': url_value,
                            'name': name_value,
                            'section_title': section_title,
                            'reason': 'already exists skipping',
                            'existing_id': existing_record.id
                        }
                        skipped_records.append(skip_info)
                        section_skipped.append(skip_info)
                        continue
                    
                    # Create individual side bar record
                    side_bar_record = SideBar(
                        section_title=section_title,
                        name=name_value,
                        url=url_value,
                        website_id=website_id,
                        is_already_exists=False
                    )
                    
                    self.db_session.add(side_bar_record)
                    self.db_session.commit()
                    self.db_session.refresh(side_bar_record)
                    
                    record_info = {
                        'id': side_bar_record.id,
                        'section_title': section_title,
                        'name': name_value,
                        'url': url_value
                    }
                    
                    saved_records.append(record_info)
                    section_records.append(record_info)
                
                section_summary.append({
                    'section_title': section_title,
                    'records_count': len(section_records),
                    'skipped_count': len(section_skipped),
                    'records': section_records,
                    'skipped': section_skipped
                })
            
            return {
                'success': True,
                'total_records': len(saved_records),
                'total_skipped': len(skipped_records),
                'sections_count': len(section_summary),
                'sections': section_summary,
                'all_records': saved_records,
                'all_skipped': skipped_records
            }
            
        except Exception as e:
            self.db_session.rollback()
            return {
                'success': False,
                'error': f"Sidebar insertion failed: {str(e)}"
            }
    
    def _save_to_database(self, merged_urls: List[Dict[str, Any]], top_data: Dict[str, Any], side_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save merged URLs and metadata to database including top_bar and side_bar tables.
        Skip creating Website record if current_page_url already exists.
        """
        try:
            # Ensure website exists and get its ID
            website_id = self._ensure_website_exists(self.url)
            
            # Check if Website record with this current_page_url already exists
            existing_website_stmt = select(Website).where(Website.current_page_url == self.url)
            existing_website_record = self.db_session.exec(existing_website_stmt).first()
            
            if existing_website_record:
                # Website record already exists, skip creating new one
                website_record = existing_website_record
                website_creation_status = "skipped - already exists"
                print(f"📄 Website record already exists for URL: {self.url}")
            else:
                # Save the complete JSON objects (not just URL strings)
                paper_urls = merged_urls  # Save the complete objects with metadata
                
                # Create new website record
                website_record = Website(
                    is_top_bar=top_data.get('success', False),
                    is_side_bar=side_data.get('success', False),
                    is_paper_exit=False,  # Will be updated later
                    website_name=website_id,
                    paper_urls=paper_urls,  # Save complete JSON objects
                    pages_count=len(paper_urls),
                    current_page_url=self.url
                )
                
                self.db_session.add(website_record)
                self.db_session.commit()
                self.db_session.refresh(website_record)
                website_creation_status = "created"
                print(f"✅ New website record created for URL: {self.url}")
            
            # Save to top_bar table (individual records)
            top_bar_result = self._save_top_bar_data(top_data, website_id)
            
            # Save to side_bar table (individual records)
            side_bar_result = self._save_side_bar_data(side_data, website_id)
            
            return {
                'success': True,
                'website_id': website_id,
                'web_id': website_record.web_id,
                'website_creation_status': website_creation_status,
                'total_urls_saved': len(merged_urls),
                'merged_urls_details': merged_urls,
                'top_bar_result': top_bar_result,
                'side_bar_result': side_bar_result
            }
            
        except Exception as e:
            self.db_session.rollback()
            return {
                'success': False,
                'error': f"Database insertion failed: {str(e)}"
            }
    
    def fetch_page(self) -> BeautifulSoup:
        """
        Fetch the HTML content of the page once and return parsed BeautifulSoup object.
        """
        response = self.session.get(self.url, headers=self.headers)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    
    def check_data_availability(self, soup: BeautifulSoup) -> Dict[str, bool]:
        """
        Check if both top-bar and sidebar data exist before processing.
        """
        # Check for top data (tables or main content)
        has_top_data = bool(soup.find_all('table') or soup.find_all('div', class_='entry-content'))
        
        # Check for sidebar data (widgets or navigation)
        has_sidebar_data = bool(
            soup.find_all('div', class_='widget') or 
            soup.find_all('aside') or
            soup.find('div', {'id': 'sidebar'}) or
            soup.find_all('nav')
        )
        
        return {
            'has_top_data': has_top_data,
            'has_sidebar_data': has_sidebar_data
        }
    
    def extract_data(self) -> Dict[str, Any]:
        """
        Extract data from the fetched page using both top and side services.
        Fetch webpage only once and check data availability before processing.
        Also handles database insertion.
        """
        # Fetch the page once
        soup = self.fetch_page()
        
        # Check if data exists before processing
        availability = self.check_data_availability(soup)
        
        result = {
            'data_availability': availability,
            'top_data': {'success': False, 'message': 'No top data available'},
            'side_data': {'success': False, 'message': 'No sidebar data available'},
            'database_result': {'success': False, 'message': 'No data to save'}
        }
        
        # Only process top data if it exists
        if availability['has_top_data']:
            try:
                # Always use the soup-based method for optimization
                result['top_data'] = self.top_service._extract_urls_from_soup(soup, self.url)
            except Exception as e:
                result['top_data'] = {'success': False, 'error': f'Top data extraction failed: {str(e)}'}
        
        # Only process sidebar data if it exists
        if availability['has_sidebar_data']:
            try:
                # Always use the soup-based method for optimization
                result['side_data'] = self.side_service._extract_sidebar_urls_from_soup(soup, self.url)
            except Exception as e:
                result['side_data'] = {'success': False, 'error': f'Sidebar data extraction failed: {str(e)}'}

        # If we have any successful data extraction, merge and save to database
        if result['top_data'].get('success') or result['side_data'].get('success'):
            merged_urls = self._merge_all_urls(result['top_data'], result['side_data'])
            result['merged_urls'] = merged_urls
            result['database_result'] = self._save_to_database(merged_urls, result['top_data'], result['side_data'])

        return result
    def run(self) -> Dict[str, Any]:
        """ Run the scraper and return the extracted data.
        """
        try:
            data = self.extract_data()
            return {
                'success': True,
                'data': data
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            # Close database session if it exists
            if hasattr(self, 'db_session') and self.db_session:
                self.db_session.close()
            
if __name__ == "__main__":
    # Test URLs for both supported websites
    test_urls = [
        'https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf',
        'https://pakmcqs.com/category/pakistan-current-affairs-mcqs'
    ]
    
    for url in test_urls:
        print(f"\n{'='*50}")
        print(f"Testing URL: {url}")
        print(f"{'='*50}")
        
        scraper = UrlsCollector(url=url)
        result = scraper.run()
        
        if result['success']:
            print("Data extracted successfully!")
            
            # Display data availability check
            availability = result['data']['data_availability']
            print(f"\nDATA AVAILABILITY CHECK:")
            print(f"Has Top Data: {availability['has_top_data']}")
            print(f"Has Sidebar Data: {availability['has_sidebar_data']}")
            
            # Display top data summary
            top_data = result['data']['top_data']
            print(f"\nTOP URLS - Success: {top_data.get('success', False)}")
            if top_data.get('success'):
                print(f"Total URLs: {top_data.get('total_urls', 0)}")
            else:
                print(f"Message/Error: {top_data.get('message', top_data.get('error', 'Unknown'))}")
            
            # Display side data summary  
            side_data = result['data']['side_data']
            print(f"\nSIDE URLS - Success: {side_data.get('success', False)}")
            if side_data.get('success'):
                print(f"Total Sections: {side_data.get('total_sections', 0)}")
                print(f"Total URLs: {side_data.get('total_urls', 0)}")
                
                # Show section breakdown for side data
                if 'sections' in side_data:
                    print("\nSection Breakdown:")
                    for section in side_data['sections']:
                        print(f"  - {section['section_title']}: {len(section['urls'])} URLs")
            else:
                print(f"Message/Error: {side_data.get('message', side_data.get('error', 'Unknown'))}")
            
            # Display database results
            db_result = result['data'].get('database_result', {})
            print(f"\nDATABASE INSERTION - Success: {db_result.get('success', False)}")
            if db_result.get('success'):
                print(f"Website ID: {db_result.get('website_id')}")
                print(f"Web Record ID: {db_result.get('web_id')}")
                print(f"Website Record: {db_result.get('website_creation_status', 'unknown')}")
                print(f"Total URLs Saved: {db_result.get('total_urls_saved', 0)}")
                
                # Display top_bar results
                top_bar_result = db_result.get('top_bar_result', {})
                print(f"\nTOP BAR TABLE - Success: {top_bar_result.get('success', False)}")
                if top_bar_result.get('success'):
                    print(f"  Total Records Created: {top_bar_result.get('total_records', 0)}")
                    print(f"  Total Records Skipped: {top_bar_result.get('total_skipped', 0)}")
                    
                    # Show created records
                    records = top_bar_result.get('records', [])
                    for i, record in enumerate(records[:3]):  # Show first 3 records
                        print(f"    Record {i+1}: ID={record.get('id')}, Name='{record.get('name', '')[:30]}...'")
                    if len(records) > 3:
                        print(f"    ... and {len(records) - 3} more records")
                    
                    # Show skipped records
                    skipped = top_bar_result.get('skipped', [])
                    if skipped:
                        print(f"  Skipped Records:")
                        for i, skip in enumerate(skipped[:3]):  # Show first 3 skipped
                            print(f"    Skipped {i+1}: '{skip.get('name', '')[:25]}...' - {skip.get('reason')}")
                        if len(skipped) > 3:
                            print(f"    ... and {len(skipped) - 3} more skipped")
                else:
                    print(f"  Message/Error: {top_bar_result.get('message', top_bar_result.get('error', 'Unknown'))}")
                
                # Display side_bar results
                side_bar_result = db_result.get('side_bar_result', {})
                print(f"\nSIDE BAR TABLE - Success: {side_bar_result.get('success', False)}")
                if side_bar_result.get('success'):
                    print(f"  Total Records Created: {side_bar_result.get('total_records', 0)}")
                    print(f"  Total Records Skipped: {side_bar_result.get('total_skipped', 0)}")
                    print(f"  Sections Processed: {side_bar_result.get('sections_count', 0)}")
                    
                    sections = side_bar_result.get('sections', [])
                    for section in sections:
                        section_title = section.get('section_title', 'Unknown')
                        records_count = section.get('records_count', 0)
                        skipped_count = section.get('skipped_count', 0)
                        print(f"    Section: {section_title} -> {records_count} created, {skipped_count} skipped")
                        
                        # Show first record from each section
                        section_records = section.get('records', [])
                        if section_records:
                            first_record = section_records[0]
                            print(f"      Sample: ID={first_record.get('id')}, Name='{first_record.get('name', '')[:25]}...'")
                        
                        # Show first skipped record from each section
                        section_skipped = section.get('skipped', [])
                        if section_skipped:
                            first_skipped = section_skipped[0]
                            print(f"      Skipped: '{first_skipped.get('name', '')[:25]}...' - {first_skipped.get('reason')}")
                else:
                    print(f"  Message/Error: {side_bar_result.get('message', side_bar_result.get('error', 'Unknown'))}")
                
                # Show merged URLs summary
                merged_urls = result['data'].get('merged_urls', [])
                print(f"\nMERGED URLS SUMMARY:")
                print(f"Total Merged URLs: {len(merged_urls)}")
                top_count = len([u for u in merged_urls if u['source'] == 'top_bar'])
                sidebar_count = len([u for u in merged_urls if u['source'] == 'sidebar'])
                print(f"  - From Top Bar: {top_count}")
                print(f"  - From Sidebar: {sidebar_count}")
                
                # Show unique sections
                sections = set(u['section'] for u in merged_urls)
                print(f"  - Unique Sections: {len(sections)}")
                for section in sorted(sections):
                    count = len([u for u in merged_urls if u['section'] == section])
                    print(f"    * {section}: {count} URLs")
            else:
                print(f"Database Error: {db_result.get('error', db_result.get('message', 'Unknown'))}")
                    
        else:
            print(f"Error occurred: {result['error']}")