from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

@dataclass
class WebsiteSideService:
    """Dataclass-based service to collect URLs from sidebar widgets (TestPoint, PakMcqs, etc.)"""
    
    urls: List[str]  # Accept a list of URLs as input
    session: requests.Session = field(default_factory=requests.Session)
    
    def __post_init__(self):
        """Initialize session headers."""
        self.session.headers = {}

    def extract_sidebar_urls(self, page_url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Extract URLs from sidebar widgets and detect website type.
        
        Args:
            page_url: The URL of the page to scrape
            headers: Optional dynamic headers for the request.
            
        Returns:
            Dictionary containing sidebar sections with their URLs.
        """
        try:
            if headers:
                self.session.headers.update(headers)  # Update session headers if passed
            
            response = self.session.get(page_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            sidebar_sections = self._extract_sidebar_urls_based_on_site(soup, page_url)
            
            total_urls = sum(len(section.get('urls', [])) for section in sidebar_sections)
            
            return {
                'success': True,
                'sections': sidebar_sections,
                'total_sections': len(sidebar_sections),
                'total_urls': total_urls,
                'source_url': page_url,
                'website_type': 'pakmcqs' if 'pakmcqs.com' in page_url else 'testpoint'
            }
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Request failed: {str(e)}",
                'sections': [],
                'total_sections': 0,
                'total_urls': 0,
                'website_type': 'unknown'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Parsing failed: {str(e)}",
                'sections': [],
                'total_sections': 0,
                'total_urls': 0,
                'website_type': 'unknown'
            }

    def _extract_sidebar_urls_based_on_site(self, soup: BeautifulSoup, page_url: str) -> List[Dict[str, Any]]:
        """Determine which method to use based on the website type."""
        if 'pakmcqs.com' in page_url:
            return self._extract_sidebar_urls_pakmcqs(soup)
        return self._extract_sidebar_urls_testpoint(soup)

    def _extract_sidebar_urls_testpoint(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract URLs from TestPoint website's sidebar widgets."""
        sidebar_sections = []
        sidebar = soup.find('div', {'id': 'sidebar'}) or soup.find('div', class_='col-md-4')
        
        if not sidebar:
            return sidebar_sections
        
        widgets = sidebar.find_all('div', class_='widget')
        
        for widget in widgets:
            # Get widget title
            widget_title = "Unknown Section"
            title_element = widget.find('div', class_='widget-title')
            if title_element:
                h4_element = title_element.find('h4')
                if h4_element:
                    widget_title = h4_element.get_text(strip=True)
            
            # Extract URLs from category widget or list widget
            widget_urls = []
            cat_widget = widget.find('div', class_='cat-widget')
            if cat_widget:
                widget_urls.extend(self._extract_urls_from_list(cat_widget, 'https://testpointpk.com'))
            else:
                ul_elements = widget.find_all('ul')
                for ul in ul_elements:
                    widget_urls.extend(self._extract_urls_from_list(ul, 'https://testpointpk.com'))
            
            # Only add section if it has URLs
            if widget_urls:
                sidebar_sections.append({
                    'section_title': widget_title,
                    'urls': widget_urls
                })
        
        return sidebar_sections
    
    def _extract_sidebar_urls_pakmcqs(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract URLs from PakMcqs website's sidebar widgets."""
        sidebar_sections = []
        
        # PakMcqs widgets are found directly, no need for specific container
        widgets = soup.find_all('div', class_='widget')
        
        for widget in widgets:
            # Get widget title
            widget_title = "Unknown Section"
            title_element = widget.find('div', class_='widget-title')
            if title_element:
                h5_element = title_element.find('h5', class_='heading')
                if h5_element:
                    widget_title = h5_element.get_text(strip=True)
            
            widget_urls = []
            
            # Skip search widgets - they don't have useful URLs
            if 'widget_wgs_widget' in widget.get('class', []):
                continue
            
            # Extract URLs from navigation menu widgets
            if 'widget_nav_menu' in widget.get('class', []):
                menu_container = widget.find('div', class_=lambda x: x and 'menu-' in x)
                if menu_container:
                    ul_element = menu_container.find('ul', class_='menu')
                    if ul_element:
                        widget_urls.extend(self._extract_urls_from_list(ul_element, 'https://pakmcqs.com'))
            
            # Also check for any ul elements with class 'menu' directly
            ul_menus = widget.find_all('ul', class_='menu')
            for ul in ul_menus:
                widget_urls.extend(self._extract_urls_from_list(ul, 'https://pakmcqs.com'))
            
            # Only add section if it has URLs
            if widget_urls:
                sidebar_sections.append({
                    'section_title': widget_title,
                    'urls': widget_urls
                })
        
        return sidebar_sections
    
    def _extract_urls_from_list(self, container, base_url: str) -> List[Dict[str, str]]:
        """Helper method to extract URLs from ul/li structure."""
        urls = []
        li_elements = container.find_all('li')
        
        for li in li_elements:
            link_element = li.find('a')
            if link_element and link_element.get('href'):
                url = link_element.get('href')
                title = link_element.get_text(strip=True)
                title = re.sub(r'\s+', ' ', title).strip()
                
                if url.startswith('/'):
                    url = urljoin(base_url, url)
                
                if not url or url.startswith('#') or url.startswith('javascript:'):
                    continue
                
                if not any(existing['url'] == url for existing in urls):
                    urls.append({'url': url, 'title': title})
        
        return urls

    def collect_sidebar_urls(self, headers: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """
        Collect sidebar URLs from the provided list of URLs.
        
        Args:
            headers: Optional dynamic headers for each request.
            
        Returns:
            List of dictionaries containing sidebar sections with URLs.
        """
        all_results = []
        
        for page_url in self.urls:
            result = self.extract_sidebar_urls(page_url, headers)
            all_results.append(result)
        
        return all_results


# Example usage
def collect_sidebar_urls_from_multiple_sources() -> List[Dict[str, Any]]:
    """Collect sidebar URLs from multiple sources by passing a list of base URLs."""
    urls = [
        "https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf",
        "https://pakmcqs.com/category/pakistan-current-affairs-mcqs"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Authorization': 'Bearer YOUR_TOKEN'  # Example dynamic header
    }
    
    collector = WebsiteSideService(urls=urls)
    return collector.collect_sidebar_urls(headers=headers)

if __name__ == "__main__":
    results = collect_sidebar_urls_from_multiple_sources()
    
    print("*" * 70)
    print("Sidebar extraction results:")
    print("*" * 70)
    
    for result in results:
        print(f"\nWebsite: {result.get('website_type')} - {result.get('source_url')}")
        print(f"Success: {result.get('success')}")
        
        if result.get('success'):
            print(f"Total Sections: {result.get('total_sections')}")
            print(f"Total URLs: {result.get('total_urls')}")
            
            sections = result.get('sections', [])
            for section in sections:
                print(f"\n  Section: {section.get('section_title')}")
                print(f"  URLs ({len(section.get('urls', []))}):")
                
                for url_data in section.get('urls', []):
                    print(f"    - {url_data['title']}")
                    print(f"      {url_data['url']}")
        else:
            print(f"Error: {result.get('error')}")
    
    print(f"\n{'='*70}")
    print("JSON STRUCTURE EXAMPLE:")
    print(f"{'='*70}")
    from pprint import pprint
    if results and results[0].get('success'):
        pprint(results[0])
    
    total_all_urls = 0
    for result in results:
        if result.get('success'):
            total_all_urls += result.get('total_urls', 0)
    
    print(f"\nGrand Total URLs found across all sites: {total_all_urls}")
