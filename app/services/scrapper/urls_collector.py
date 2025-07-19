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
    
    def extract_data(self) -> Dict[str, Any]:
        """
        Extract data from the fetched page using both top and side services.
        """
        # Use the services to extract data directly (they handle fetching internally)
        top_data = self.top_service.extract_urls(self.url)
        side_data = self.side_service.extract_sidebar_urls(self.url)

        return {
            'top_data': top_data,
            'side_data': side_data
        }
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
            
            # Display top data summary
            top_data = result['data']['top_data']
            print(f"\nTOP URLS - Success: {top_data.get('success', False)}")
            print(f"Total URLs: {top_data.get('total_urls', 0)}")
            
            # Display side data summary  
            side_data = result['data']['side_data']
            print(f"\nSIDE URLS - Success: {side_data.get('success', False)}")
            print(f"Total Sections: {side_data.get('total_sections', 0)}")
            print(f"Total URLs: {side_data.get('total_urls', 0)}")
            
            # Show section breakdown for side data
            if side_data.get('success') and 'sections' in side_data:
                print("\nSection Breakdown:")
                for section in side_data['sections']:
                    print(f"  - {section['section_title']}: {len(section['urls'])} URLs")
                    
        else:
            print(f"Error occurred: {result['error']}")