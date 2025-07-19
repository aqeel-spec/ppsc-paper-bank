from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, TypeVar, Generic
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

T = TypeVar('T')  # Generic Type for URL

@dataclass
class WebsiteTopService(Generic[T]):
    """Dataclass-based service to collect URLs from various website types (TestPoint, PakMcqs, etc.)"""
    
    urls: List[T]  # Accept a list of URLs as input
    session: requests.Session = field(default_factory=requests.Session)
    
    def __post_init__(self):
        """Update session headers after the dataclass is initialized."""
        # Here, headers are no longer set by default. They are only passed when instantiating the class.
        self.session.headers = {}

    def extract_urls(self, page_url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Extract URLs from tables - automatically detects website type.
        
        Args:
            page_url: The URL of the page to scrape
            headers: Dynamic headers to use for the request (optional)
            
        Returns:
            Dictionary containing list of URLs with their titles
        """
        try:
            if headers:
                self.session.headers.update(headers)  # Update session headers if passed
            
            response = self.session.get(page_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Detect website type and extract URLs accordingly
            if 'pakmcqs.com' in page_url:
                urls = self._extract_table_urls_pakmcqs(soup)
            else:
                # Default to TestPoint structure
                urls = self._extract_table_urls_testpoint(soup)
            
            return {
                'success': True,
                'urls': urls,
                'total_urls': len(urls),
                'source_url': page_url,
                'website_type': 'pakmcqs' if 'pakmcqs.com' in page_url else 'testpoint'
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Request failed: {str(e)}",
                'urls': [],
                'total_urls': 0,
                'website_type': 'unknown'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Parsing failed: {str(e)}",
                'urls': [],
                'total_urls': 0,
                'website_type': 'unknown'
            }

    def _extract_table_urls_testpoint(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract URLs from TestPoint website's table."""
        urls = []
        try:
            table = soup.find('table', class_='section-hide-show')
            if not table:
                table = soup.find('table', class_='table-bordered')
                if not table:
                    table = soup.find('table')
                    if not table:
                        return urls
            tbody = table.find('tbody')
            rows = tbody.find_all('tr') if tbody else table.find_all('tr')
            
            for row in rows:
                tds = row.find_all('td')
                if len(tds) >= 2:
                    link_td = tds[1]
                    link_element = link_td.find('a')
                    
                    if link_element and link_element.get('href'):
                        url = link_element.get('href')
                        title = link_element.get_text(strip=True)
                        if url.startswith('/'):
                            url = urljoin("https://testpointpk.com", url)
                        
                        urls.append({
                            'url': url,
                            'title': title
                        })
        
        except Exception as e:
            print(f"Error extracting TestPoint table URLs: {str(e)}")
        
        return urls
    
    def _extract_table_urls_pakmcqs(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract URLs from PakMcqs website's table."""
        urls = []
        try:
            tables = soup.find_all('table', class_='table')
            for table in tables:
                tbody = table.find('tbody')
                rows = tbody.find_all('tr') if tbody else table.find_all('tr')
                
                for row in rows:
                    if row.find('th'):
                        continue
                    tds = row.find_all('td')
                    for td in tds:
                        links = td.find_all('a')
                        for link_element in links:
                            if link_element.get('href'):
                                url = link_element.get('href')
                                 
                                if url.startswith('/'):
                                    url = urljoin("https://pakmcqs.com", url)
                                
                                if not url or url.startswith('#') or url == 'javascript:void(0)':
                                    continue
                                
                                if not any(existing['url'] == url for existing in urls):
                                    title = link_element.get_text(strip=True)
                                    urls.append({
                                        'url': url,
                                        'title': title
                                    })
        
        except Exception as e:
            print(f"Error extracting PakMcqs table URLs: {str(e)}")
        
        return urls

    def collect_urls(self, headers: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """
        Collect URLs from the provided list of URLs.
        
        Args:
            headers: Optional dynamic headers for each request.
            
        Returns:
            List of dictionaries containing URLs and titles.
        """
        all_results = []
        
        for page_url in self.urls:  # Using the URLs list passed during initialization
            result = self.extract_urls(page_url, headers)
            all_results.append(result)
        
        return all_results


# Example usage
def collect_urls_from_multiple_sources() -> List[Dict[str, Any]]:
    """Collect URLs from multiple sources by passing a list of base URLs."""
    urls = [
        "https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf",
        "https://pakmcqs.com/category/pakistan-current-affairs-mcqs"
    ]
    
    # Dynamic headers can be passed here
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Authorization': 'Bearer YOUR_TOKEN'  # Example of dynamic header
    }
    
    collector = WebsiteTopService(urls=urls)
    return collector.collect_urls(headers=headers)

if __name__ == "__main__":
    results = collect_urls_from_multiple_sources()
    print("*" * 70)
    print("results",results)
    print("*" * 70)
    for result in results:
        print(f"Total URLs: {result.get('total_urls')}")
        for url_data in result.get('urls', []):
            print(f"   URL: {url_data['url']}, Title: {url_data['title']}")





# import requests
# from bs4 import BeautifulSoup
# from typing import List, Dict, Optional, Any
# import re
# from urllib.parse import urljoin


# class WebsiteTopService:
#     """Service to collect URLs and titles from multiple website types (TestPoint, PakMcqs, etc.)"""
    
#     def __init__(self, base_url: str = "https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf"):
#         self.base_url = base_url
#         self.session = requests.Session()
#         # Set headers to mimic a browser
#         self.session.headers.update({
#             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
#         })
    
#     def extract_urls_and_title(self, page_url: str) -> Dict[str, Any]:
#         """
#         Extract URLs from table and title - automatically detects website type
        
#         Args:
#             page_url: The URL of the page to scrape
            
#         Returns:
#             Dictionary containing title and list of URLs with their titles
#         """
#         try:
#             response = self.session.get(page_url, timeout=30)
#             response.raise_for_status()
            
#             soup = BeautifulSoup(response.content, 'html.parser')
            
#             # Detect website type and extract accordingly
#             if 'pakmcqs.com' in page_url:
#                 title = self._extract_title_pakmcqs(soup)
#                 urls = self._extract_table_urls_pakmcqs(soup)
#             else:
#                 # Default to TestPoint structure
#                 title = self._extract_title_testpoint(soup)
#                 urls = self._extract_table_urls_testpoint(soup)
            
#             return {
#                 'success': True,
#                 'title': title,
#                 'urls': urls,
#                 'total_urls': len(urls),
#                 'source_url': page_url,
#                 'website_type': 'pakmcqs' if 'pakmcqs.com' in page_url else 'testpoint'
#             }
            
#         except requests.RequestException as e:
#             return {
#                 'success': False,
#                 'error': f"Request failed: {str(e)}",
#                 'title': None,
#                 'urls': [],
#                 'total_urls': 0,
#                 'website_type': 'unknown'
#             }
#         except Exception as e:
#             return {
#                 'success': False,
#                 'error': f"Parsing failed: {str(e)}",
#                 'title': None,
#                 'urls': [],
#                 'total_urls': 0,
#                 'website_type': 'unknown'
#             }
    
#     def _extract_title_testpoint(self, soup: BeautifulSoup) -> Optional[str]:
#         """Extract title from TestPoint widget-title h4"""
#         try:
#             title_element = soup.find('div', class_='widget-title')
#             if title_element:
#                 h4_element = title_element.find('h4')
#                 if h4_element:
#                     return h4_element.get_text(strip=True)
#             return None
#         except Exception:
#             return None
    
#     def _extract_title_pakmcqs(self, soup: BeautifulSoup) -> Optional[str]:
#         """Extract title from PakMcqs archive-heading or page title"""
#         try:
#             # Try archive heading first
#             title_element = soup.find('h1', class_='archive-heading')
#             if title_element:
#                 span_element = title_element.find('span')
#                 if span_element:
#                     return span_element.get_text(strip=True)
#                 return title_element.get_text(strip=True)
            
#             # Fallback to page title
#             title_element = soup.find('title')
#             if title_element:
#                 title_text = title_element.get_text(strip=True)
#                 # Clean up title by removing "- PakMcqs" or similar suffixes
#                 title_text = re.sub(r'\s*-\s*PakMcqs.*$', '', title_text)
#                 return title_text
            
#             return None
#         except Exception:
#             return None
    
#     def _extract_table_urls_testpoint(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
#         """Extract URLs from TestPoint table structure"""
#         urls = []
#         try:
#             # Find the table with the specific class
#             table = soup.find('table', class_='section-hide-show')
#             if not table:
#                 # Try alternative selectors
#                 table = soup.find('table', class_='table-bordered')
#                 if not table:
#                     table = soup.find('table')
#                     if not table:
#                         return urls
            
#             # Find all rows in the table body
#             tbody = table.find('tbody')
#             if not tbody:
#                 # If no tbody, find rows directly in table
#                 rows = table.find_all('tr')
#             else:
#                 rows = tbody.find_all('tr')
            
#             for row in rows:
#                 # Find the second td (contains the link)
#                 tds = row.find_all('td')
#                 if len(tds) >= 2:
#                     link_td = tds[1]  # Second column
#                     link_element = link_td.find('a')
                    
#                     if link_element and link_element.get('href'):
#                         url = link_element.get('href')
#                         title = link_element.get_text(strip=True)
                        
#                         # Make sure URL is absolute
#                         if url.startswith('/'):
#                             url = urljoin("https://testpointpk.com", url)
                        
#                         urls.append({
#                             'url': url,
#                             'title': title,
#                             'index': len(urls) + 1
#                         })
        
#         except Exception as e:
#             print(f"Error extracting TestPoint table URLs: {str(e)}")
        
#         return urls
    
#     def _extract_table_urls_pakmcqs(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
#         """Extract URLs from PakMcqs table structure"""
#         urls = []
#         try:
#             # Find tables with class "table" - PakMcqs structure
#             tables = soup.find_all('table', class_='table')
            
#             for table in tables:
#                 tbody = table.find('tbody')
#                 if not tbody:
#                     # If no tbody, find rows directly in table
#                     rows = table.find_all('tr')
#                 else:
#                     rows = tbody.find_all('tr')
                
#                 for row in rows:
#                     # Skip header rows
#                     if row.find('th'):
#                         continue
                    
#                     # Find all td elements
#                     tds = row.find_all('td')
                    
#                     # Check each td for links
#                     for td in tds:
#                         links = td.find_all('a')
#                         for link_element in links:
#                             if link_element.get('href'):
#                                 url = link_element.get('href')
#                                 title = link_element.get_text(strip=True)
                                
#                                 # Clean up title by removing emoji and extra formatting
#                                 title = re.sub(r'^❇️\s*', '', title)  # Remove emoji
#                                 title = re.sub(r'\s+', ' ', title).strip()  # Clean whitespace
                                
#                                 # Make sure URL is absolute
#                                 if url.startswith('/'):
#                                     url = urljoin("https://pakmcqs.com", url)
                                
#                                 # Skip if URL is empty or just anchor
#                                 if not url or url.startswith('#') or url == 'javascript:void(0)':
#                                     continue
                                
#                                 # Skip duplicates
#                                 if not any(existing['url'] == url for existing in urls):
#                                     urls.append({
#                                         'url': url,
#                                         'title': title,
#                                         'index': len(urls) + 1
#                                     })
        
#         except Exception as e:
#             print(f"Error extracting PakMcqs table URLs: {str(e)}")
        
#         return urls
    
#     def extract_multiple_pages(self, base_url: str, max_pages: int = 5) -> List[Dict[str, any]]:
#         """
#         Extract URLs from multiple pages with pagination
        
#         Args:
#             base_url: Base URL without page parameter
#             max_pages: Maximum number of pages to scrape
            
#         Returns:
#             List of dictionaries containing data from each page
#         """
#         all_results = []
        
#         for page_num in range(1, max_pages + 1):
#             # Construct URL with page parameter
#             if '?' in base_url:
#                 page_url = f"{base_url}&page={page_num}"
#             else:
#                 page_url = f"{base_url}?page={page_num}"
            
#             print(f"Scraping page {page_num}: {page_url}")
            
#             result = self.extract_urls_and_title(page_url)
#             result['page_number'] = page_num
            
#             all_results.append(result)
            
#             # If no URLs found, might have reached the end
#             if not result.get('urls'):
#                 print(f"No URLs found on page {page_num}, stopping.")
#                 break
        
#         return all_results
    
#     def get_all_unique_urls(self, results: List[Dict[str, any]]) -> List[Dict[str, str]]:
#         """
#         Get all unique URLs from multiple page results
        
#         Args:
#             results: List of results from extract_multiple_pages
            
#         Returns:
#             List of unique URLs with their titles
#         """
#         seen_urls = set()
#         unique_urls = []
        
#         for result in results:
#             if result.get('success') and result.get('urls'):
#                 for url_data in result['urls']:
#                     url = url_data['url']
#                     if url not in seen_urls:
#                         seen_urls.add(url)
#                         unique_urls.append(url_data)
        
#         return unique_urls


# # Example usage and helper functions
# def collect_ppsc_assistant_urls() -> Dict[str, any]:
#     """Collect URLs from PPSC Assistant Past Papers page (TestPoint)"""
#     collector = WebsiteTopService()
#     url = "https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf"
    
#     return collector.extract_urls_and_title(url)


# def collect_pakmcqs_urls(category_url: str = "https://pakmcqs.com/category/pakistan-current-affairs-mcqs") -> Dict[str, any]:
#     """Collect URLs from PakMcqs category page"""
#     collector = WebsiteTopService()
    
#     return collector.extract_urls_and_title(category_url)


# # def collect_urls_from_multiple_pages(base_url: str, max_pages: int = 10) -> Dict[str, any]:
# #     """
# #     Collect URLs from multiple pages of a category
    
# #     Args:
# #         base_url: The base URL of the category page
# #         max_pages: Maximum number of pages to scrape
        
# #     Returns:
# #         Dictionary with summary and all collected URLs
# #     """
# #     collector = WebsiteTopService()
# #     results = collector.extract_multiple_pages(base_url, max_pages)
# #     unique_urls = collector.get_all_unique_urls(results)
    
# #     # Get title from first successful result
# #     title = None
# #     for result in results:
# #         if result.get('success') and result.get('title'):
# #             title = result['title']
# #             break
    
# #     return {
# #         'success': True,
# #         'title': title,
# #         'total_pages_scraped': len([r for r in results if r.get('success')]),
# #         'total_unique_urls': len(unique_urls),
# #         'urls': unique_urls,
# #         'detailed_results': results
# #     }


# if __name__ == "__main__":
#     # Test the service
#     print("Testing URL Collector Service...\n")
    
#     # Test TestPoint website
#     print("1. Testing TestPoint website:")
#     result = collect_ppsc_assistant_urls()
#     print(f"   Title: {result.get('title')}")
#     print(f"   Found {result.get('total_urls')} URLs")
#     print(f"   Website type: {result.get('website_type')}")
    
#     if result.get('urls'):
#         print("   First 3 URLs:")
#         for i, url_data in enumerate(result['urls'][:3]):
#             print(f"   {i+1}. {url_data['title']}")
#             print(f"      URL: {url_data['url']}")
    
#     print("\n" + "="*50 + "\n")
    
#     # Test PakMcqs website
#     print("2. Testing PakMcqs website:")
#     pak_result = collect_pakmcqs_urls()
#     print(f"   Title: {pak_result.get('title')}")
#     print(f"   Found {pak_result.get('total_urls')} URLs")
#     print(f"   Website type: {pak_result.get('website_type')}")
    
#     if pak_result.get('urls'):
#         print("   First 5 URLs:")
#         for i, url_data in enumerate(pak_result['urls'][:5]):
#             print(f"   {i+1}. {url_data['title']}")
#             print(f"      URL: {url_data['url']}")
    
#     # Check for errors
#     if not result.get('success'):
#         print(f"\nTestPoint Error: {result.get('error')}")
    
#     if not pak_result.get('success'):
#         print(f"\nPakMcqs Error: {pak_result.get('error')}")
    
#     print(f"\nTotal URLs found: TestPoint={result.get('total_urls', 0)}, PakMcqs={pak_result.get('total_urls', 0)}")