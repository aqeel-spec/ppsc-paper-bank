from dataclasses import dataclass, field
from typing import Dict, List, Any
import requests
from bs4 import BeautifulSoup
from .top_urls import WebsiteTopService
from .side_urls import WebsiteSideService

@dataclass
class UrlsCollector:
    """
    A dataclass-based web scraper that extracts various tags like title, meta, images, links, tables, and more.
    """
    url: str
    
    session: requests.Session = field(default_factory=requests.Session)
    headers: Dict[str, str] = field(default_factory=lambda: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    top_service: WebsiteTopService = field(init=False)
    side_service: WebsiteSideService = field(init=False)
    
    def __post_init__(self):
        """Initialize services with the URL after object creation."""
        self.top_service = WebsiteTopService(urls=[self.url])
        self.side_service = WebsiteSideService(urls=[self.url])
    
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
        """
        # Fetch the page once
        soup = self.fetch_page()
        
        # Check if data exists before processing
        availability = self.check_data_availability(soup)
        
        result = {
            'data_availability': availability,
            'top_data': {'success': False, 'message': 'No top data available'},
            'side_data': {'success': False, 'message': 'No sidebar data available'}
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
                    
        else:
            print(f"Error occurred: {result['error']}")