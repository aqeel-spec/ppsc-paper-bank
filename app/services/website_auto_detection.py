from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
import re
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_engine
from app.models.websites import Websites, WebsitesCreate
from app.models.website import Website, WebsiteCreate
from app.services.scrapper.top_urls import WebsiteTopService


class WebsiteAutoDetectionService:
    """
    Intelligent service that automatically detects website configurations
    and capabilities without hardcoded settings.
    """
    
    def __init__(self):
        self.url_service = WebsiteTopService()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def detect_website_type(self, base_url: str) -> Dict[str, Any]:
        """
        Automatically detect the type and characteristics of a website.
        
        Args:
            base_url: Base URL of the website to analyze
            
        Returns:
            Dictionary with detected website information
        """
        try:
            print(f"🔍 Analyzing website: {base_url}")
            
            response = self.session.get(base_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract basic information
            parsed_url = urlparse(base_url)
            domain = parsed_url.netloc.lower()
            
            detection_result = {
                'base_url': base_url,
                'domain': domain,
                'website_name': self._extract_website_name(soup, domain),
                'website_type': self._detect_website_type_from_content(soup, domain),
                'description': self._generate_description(soup, domain),
                'capabilities': self._detect_capabilities(soup, base_url),
                'navigation_structure': self._analyze_navigation_structure(soup, base_url),
                'content_patterns': self._detect_content_patterns(soup),
                'processing_flags': self._determine_processing_flags(soup, base_url),
                'confidence_score': 0.0,
                'detection_timestamp': datetime.now().isoformat()
            }
            
            # Calculate confidence score
            detection_result['confidence_score'] = self._calculate_confidence_score(detection_result)
            
            print(f"   ✅ Website Type: {detection_result['website_type']}")
            print(f"   ✅ Capabilities: {len(detection_result['capabilities'])} detected")
            print(f"   ✅ Confidence: {detection_result['confidence_score']:.1%}")
            
            return {
                'success': True,
                'detection_result': detection_result
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'base_url': base_url
            }
    
    def _extract_website_name(self, soup: BeautifulSoup, domain: str) -> str:
        """Extract website name from various sources."""
        # Try title tag
        title = soup.find('title')
        if title:
            title_text = title.get_text().strip()
            # Remove common suffixes
            for suffix in [' - Home', ' | Home', ' - Official Site', ' - Official Website']:
                if title_text.endswith(suffix):
                    title_text = title_text[:-len(suffix)]
            if title_text and len(title_text) < 100:
                return title_text
        
        # Try site name meta tag
        site_name = soup.find('meta', {'property': 'og:site_name'})
        if site_name and site_name.get('content'):
            return site_name['content'].strip()
        
        # Try logo alt text
        logo = soup.find('img', {'alt': re.compile(r'logo', re.I)})
        if logo and logo.get('alt'):
            return logo['alt'].strip()
        
        # Fallback to domain name
        return domain.replace('www.', '').replace('.com', '').replace('.pk', '').title()
    
    def _detect_website_type_from_content(self, soup: BeautifulSoup, domain: str) -> str:
        """Detect website type based on content analysis."""
        text_content = soup.get_text().lower()
        
        # Define patterns for different website types
        patterns = {
            'MCQ_PLATFORM': ['mcq', 'multiple choice', 'quiz', 'test preparation', 'practice questions'],
            'EDUCATIONAL': ['education', 'learning', 'study', 'course', 'lesson', 'tutorial'],
            'EXAM_PREP': ['exam', 'preparation', 'ppsc', 'fpsc', 'nts', 'competitive', 'past papers'],
            'NEWS_PORTAL': ['news', 'latest', 'breaking', 'headlines', 'article', 'journalist'],
            'GOVERNMENT': ['government', 'official', 'ministry', 'department', 'public service'],
            'BLOG': ['blog', 'post', 'article', 'author', 'published', 'comment'],
            'E_COMMERCE': ['shop', 'buy', 'cart', 'product', 'price', 'order'],
            'FORUM': ['forum', 'discussion', 'thread', 'reply', 'member', 'post']
        }
        
        scores = {}
        for website_type, keywords in patterns.items():
            score = sum(1 for keyword in keywords if keyword in text_content)
            scores[website_type] = score
        
        # Get the type with highest score
        if scores:
            detected_type = max(scores, key=scores.get)
            if scores[detected_type] > 0:
                return detected_type
        
        # Domain-based fallback
        if any(keyword in domain for keyword in ['mcq', 'test', 'quiz', 'exam']):
            return 'MCQ_PLATFORM'
        elif any(keyword in domain for keyword in ['edu', 'learn', 'study']):
            return 'EDUCATIONAL'
        
        return 'GENERAL_WEBSITE'
    
    def _generate_description(self, soup: BeautifulSoup, domain: str) -> str:
        """Generate a description for the website."""
        # Try meta description
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            desc = meta_desc['content'].strip()
            if len(desc) > 20 and len(desc) < 300:
                return desc
        
        # Try og:description
        og_desc = soup.find('meta', {'property': 'og:description'})
        if og_desc and og_desc.get('content'):
            desc = og_desc['content'].strip()
            if len(desc) > 20 and len(desc) < 300:
                return desc
        
        # Try to find a prominent paragraph
        paragraphs = soup.find_all('p')
        for p in paragraphs[:5]:  # Check first 5 paragraphs
            text = p.get_text().strip()
            if len(text) > 50 and len(text) < 300:
                return text
        
        return f"Website providing educational and informational content from {domain}"
    
    def _detect_capabilities(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """Detect website capabilities like navigation, content types, etc."""
        capabilities = []
        
        # Navigation capability
        nav_elements = soup.find_all(['nav', 'ul', 'ol'], class_=re.compile(r'nav|menu', re.I))
        if nav_elements:
            nav_links = []
            for nav in nav_elements[:3]:  # Check first 3 navigation elements
                links = nav.find_all('a', href=True)
                nav_links.extend([{
                    'text': a.get_text().strip(),
                    'href': urljoin(base_url, a['href'])
                } for a in links[:10]])  # Limit to 10 links per nav
            
            if nav_links:
                capabilities.append({
                    'type': 'NAVIGATION',
                    'description': 'Website has navigation menus',
                    'data': nav_links[:20],  # Limit total nav links
                    'confidence': 0.9
                })
        
        # Content listing capability
        content_lists = soup.find_all(['table', 'ul', 'ol', 'div'], 
                                     class_=re.compile(r'list|table|grid|content', re.I))
        if content_lists:
            capabilities.append({
                'type': 'CONTENT_LISTING',
                'description': 'Website has structured content listings',
                'data': {'elements_found': len(content_lists)},
                'confidence': 0.7
            })
        
        # Form capability (search, contact, etc.)
        forms = soup.find_all('form')
        if forms:
            capabilities.append({
                'type': 'FORMS',
                'description': 'Website has interactive forms',
                'data': {'forms_count': len(forms)},
                'confidence': 0.8
            })
        
        # Pagination capability
        pagination = soup.find_all(['a', 'button'], 
                                  string=re.compile(r'next|previous|page|\d+', re.I))
        if pagination:
            capabilities.append({
                'type': 'PAGINATION',
                'description': 'Website supports pagination',
                'data': {'pagination_elements': len(pagination)},
                'confidence': 0.6
            })
        
        return capabilities
    
    def _analyze_navigation_structure(self, soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
        """Analyze the navigation structure of the website."""
        structure = {
            'top_navigation': [],
            'side_navigation': [],
            'footer_navigation': [],
            'breadcrumbs': [],
            'total_links': 0
        }
        
        # Top navigation
        top_nav = soup.find(['nav', 'header', 'div'], class_=re.compile(r'top|header|main.*nav', re.I))
        if top_nav:
            links = top_nav.find_all('a', href=True)
            structure['top_navigation'] = [{
                'text': a.get_text().strip(),
                'url': urljoin(base_url, a['href'])
            } for a in links[:15]]
        
        # Side navigation
        side_nav = soup.find(['aside', 'div'], class_=re.compile(r'side|sidebar', re.I))
        if side_nav:
            links = side_nav.find_all('a', href=True)
            structure['side_navigation'] = [{
                'text': a.get_text().strip(),
                'url': urljoin(base_url, a['href'])
            } for a in links[:10]]
        
        # Footer navigation
        footer = soup.find('footer')
        if footer:
            links = footer.find_all('a', href=True)
            structure['footer_navigation'] = [{
                'text': a.get_text().strip(),
                'url': urljoin(base_url, a['href'])
            } for a in links[:10]]
        
        # Breadcrumbs
        breadcrumb = soup.find(['nav', 'ol', 'ul'], class_=re.compile(r'breadcrumb', re.I))
        if breadcrumb:
            links = breadcrumb.find_all('a', href=True)
            structure['breadcrumbs'] = [{
                'text': a.get_text().strip(),
                'url': urljoin(base_url, a['href'])
            } for a in links]
        
        structure['total_links'] = (len(structure['top_navigation']) + 
                                  len(structure['side_navigation']) + 
                                  len(structure['footer_navigation']))
        
        return structure
    
    def _detect_content_patterns(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Detect content patterns on the website."""
        patterns = {
            'has_articles': bool(soup.find_all(['article', 'div'], class_=re.compile(r'article|post', re.I))),
            'has_tables': bool(soup.find_all('table')),
            'has_lists': bool(soup.find_all(['ul', 'ol'])),
            'has_images': bool(soup.find_all('img')),
            'has_videos': bool(soup.find_all(['video', 'iframe'])),
            'has_forms': bool(soup.find_all('form')),
            'text_heavy': len(soup.get_text()) > 5000,
            'interactive_elements': len(soup.find_all(['button', 'input', 'select'])),
        }
        
        return patterns
    
    def _determine_processing_flags(self, soup: BeautifulSoup, base_url: str) -> Dict[str, bool]:
        """Determine which processing flags should be enabled."""
        flags = {
            'is_top_bar': False,
            'is_paper_exit': False,
            'is_side_bar': False
        }
        
        # Check for top bar navigation
        nav_structure = self._analyze_navigation_structure(soup, base_url)
        if nav_structure['top_navigation'] or nav_structure['total_links'] > 5:
            flags['is_top_bar'] = True
        
        # Check for paper/document content
        text_content = soup.get_text().lower()
        paper_keywords = ['paper', 'document', 'pdf', 'download', 'exam', 'test']
        if any(keyword in text_content for keyword in paper_keywords):
            flags['is_paper_exit'] = True
        
        # Check for sidebar content
        if nav_structure['side_navigation']:
            flags['is_side_bar'] = True
        
        return flags
    
    def _calculate_confidence_score(self, detection_result: Dict[str, Any]) -> float:
        """Calculate confidence score for the detection."""
        score = 0.0
        
        # Base score for successful detection
        score += 0.3
        
        # Bonus for having a clear website type
        if detection_result['website_type'] != 'GENERAL_WEBSITE':
            score += 0.2
        
        # Bonus for detected capabilities
        score += min(len(detection_result['capabilities']) * 0.1, 0.3)
        
        # Bonus for navigation structure
        nav_links = detection_result['navigation_structure']['total_links']
        if nav_links > 0:
            score += min(nav_links / 20, 0.2)
        
        return min(score, 1.0)
    
    def discover_processable_urls(self, base_url: str, max_depth: int = 2) -> Dict[str, Any]:
        """
        Enhanced URL discovery with intelligent content extraction.
        
        Args:
            base_url: Base URL to start discovery from
            max_depth: Maximum depth to crawl
            
        Returns:
            Dictionary with discovered URLs and their characteristics
        """
        try:
            print(f"🔎 Discovering processable URLs from: {base_url}")
            
            discovered_urls = []
            processed_urls = set()
            urls_to_process = [(base_url, 0)]  # (url, depth)
            
            while urls_to_process and len(discovered_urls) < 100:  # Increased limit
                current_url, depth = urls_to_process.pop(0)
                
                if current_url in processed_urls or depth > max_depth:
                    continue
                
                processed_urls.add(current_url)
                
                try:
                    response = self.session.get(current_url, timeout=15)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Analyze this URL
                    url_analysis = self._analyze_url_content(current_url, soup)
                    if url_analysis['is_processable']:
                        discovered_urls.append(url_analysis)
                        print(f"   ✅ Found processable URL: {url_analysis['title']}")
                    
                    # Enhanced URL discovery for different website structures
                    new_urls = self._extract_intelligent_urls(soup, current_url, base_url, depth)
                    
                    # Add new URLs to processing queue
                    for new_url in new_urls:
                        if new_url not in processed_urls:
                            urls_to_process.append((new_url, depth + 1))
                
                except Exception as e:
                    print(f"   ⚠️  Error processing {current_url}: {str(e)}")
                    continue
            
            print(f"   ✅ Discovered {len(discovered_urls)} processable URLs")
            
            return {
                'success': True,
                'discovered_urls': discovered_urls,
                'total_discovered': len(discovered_urls),
                'base_url': base_url
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'base_url': base_url
            }
    
    def _extract_intelligent_urls(self, soup: BeautifulSoup, current_url: str, base_url: str, depth: int) -> List[str]:
        """Extract URLs intelligently based on website structure."""
        urls = []
        base_domain = urlparse(base_url).netloc
        
        # 1. Extract from table structure (like the provided HTML)
        table_links = soup.find_all('table')
        for table in table_links:
            table_urls = table.find_all('a', href=True)
            for link in table_urls[:30]:  # Limit per table
                href = link.get('href')
                if href:
                    full_url = urljoin(current_url, href)
                    if urlparse(full_url).netloc == base_domain:
                        urls.append(full_url)
        
        # 2. Extract from navigation menus
        nav_selectors = ['nav', '[class*="nav"]', '[class*="menu"]', 
                        '[class*="dropdown"]', '.navbar', '.nav-menu']
        for selector in nav_selectors:
            nav_elements = soup.select(selector)
            for nav in nav_elements:
                nav_links = nav.find_all('a', href=True)
                for link in nav_links[:15]:  # Limit per nav
                    href = link.get('href')
                    if href:
                        full_url = urljoin(current_url, href)
                        if urlparse(full_url).netloc == base_domain:
                            urls.append(full_url)
        
        # 3. Extract from content areas
        content_selectors = ['#content', '.content', '.main-content', 
                           '[class*="post"]', '[class*="article"]']
        for selector in content_selectors:
            content_elements = soup.select(selector)
            for content in content_elements:
                content_links = content.find_all('a', href=True)
                for link in content_links[:20]:  # Limit per content area
                    href = link.get('href')
                    if href:
                        full_url = urljoin(current_url, href)
                        if urlparse(full_url).netloc == base_domain:
                            urls.append(full_url)
        
        # 4. Extract from pagination
        pagination_selectors = ['.pagination a', '.page-link', 
                               '[class*="page"]', '.next', '.prev']
        for selector in pagination_selectors:
            page_links = soup.select(selector)
            for link in page_links[:10]:  # Limit pagination
                href = link.get('href')
                if href:
                    full_url = urljoin(current_url, href)
                    if urlparse(full_url).netloc == base_domain:
                        urls.append(full_url)
        
        # 5. Extract from sidebar
        sidebar_selectors = ['#sidebar', '.sidebar', '.side-nav',
                           '[class*="widget"]', '.cat-widget']
        for selector in sidebar_selectors:
            sidebar_elements = soup.select(selector)
            for sidebar in sidebar_elements:
                sidebar_links = sidebar.find_all('a', href=True)
                for link in sidebar_links[:15]:  # Limit per sidebar
                    href = link.get('href')
                    if href:
                        full_url = urljoin(current_url, href)
                        if urlparse(full_url).netloc == base_domain:
                            urls.append(full_url)
        
        # 6. Smart category and section detection
        category_keywords = ['mcq', 'paper', 'test', 'exam', 'past', 'question', 
                           'category', 'subject', 'chapter', 'topic']
        all_links = soup.find_all('a', href=True)
        for link in all_links:
            href = link.get('href', '')
            text = link.get_text().lower().strip()
            
            # Check if link text or URL contains relevant keywords
            if any(keyword in text or keyword in href.lower() for keyword in category_keywords):
                full_url = urljoin(current_url, href)
                if urlparse(full_url).netloc == base_domain:
                    urls.append(full_url)
        
        # Remove duplicates and return limited set
        unique_urls = list(set(urls))
        return unique_urls[:50]  # Limit total URLs per page
    
    def _analyze_url_content(self, url: str, soup: BeautifulSoup) -> Dict[str, Any]:
        """Enhanced analysis of URL content for better detection."""
        text_content = soup.get_text().lower()
        
        # Determine if this URL is worth processing
        is_processable = False
        content_type = 'UNKNOWN'
        confidence = 0.0
        
        # Enhanced keyword matching with weighted scoring
        keyword_groups = {
            'MCQ': {
                'keywords': ['mcq', 'multiple choice', 'quiz', 'question', 'answer', 'option', 'choose correct'],
                'weight': 1.0
            },
            'EXAM_CONTENT': {
                'keywords': ['exam', 'test', 'paper', 'past paper', 'preparation', 'ppsc', 'fpsc', 'nts', 
                           'syllabus', 'past papers', 'assistant', 'competitive exam'],
                'weight': 1.2
            },
            'EDUCATIONAL': {
                'keywords': ['lesson', 'chapter', 'study', 'learn', 'tutorial', 'course', 'subject',
                           'islamic studies', 'pak study', 'general knowledge', 'english', 'computer'],
                'weight': 0.8
            },
            'PDF_CONTENT': {
                'keywords': ['pdf', 'download', 'book', 'material', 'notes', 'guide'],
                'weight': 0.9
            }
        }
        
        # URL-based scoring
        url_lower = url.lower()
        url_keywords = ['mcq', 'test', 'exam', 'paper', 'past', 'question', 'quiz', 'preparation']
        url_score = sum(1 for keyword in url_keywords if keyword in url_lower) * 0.3
        
        # Calculate scores for each content type
        type_scores = {}
        for content_type_name, group in keyword_groups.items():
            keywords = group['keywords']
            weight = group['weight']
            
            # Count keyword occurrences
            keyword_count = sum(1 for keyword in keywords if keyword in text_content)
            
            # Calculate score
            base_score = keyword_count / len(keywords)
            weighted_score = base_score * weight + url_score
            
            type_scores[content_type_name] = weighted_score
        
        # Determine best content type
        if type_scores:
            best_type = max(type_scores, key=type_scores.get)
            max_score = type_scores[best_type]
            
            if max_score > 0.3:  # Lowered threshold for better detection
                is_processable = True
                content_type = best_type
                confidence = min(max_score, 1.0)
        
        # Extract enhanced title
        title = self._extract_enhanced_title(soup, url)
        
        # Enhanced structure detection
        structure_score = self._calculate_structure_score(soup)
        
        # Content length bonus
        content_length_score = min(len(text_content) / 5000, 0.3)  # Bonus for substantial content
        
        # Final confidence calculation
        if is_processable:
            confidence = min(confidence + structure_score + content_length_score, 1.0)
        elif structure_score > 0.4 and len(text_content) > 1000:
            # Catch potentially valuable content even without keywords
            is_processable = True
            content_type = 'STRUCTURED_CONTENT'
            confidence = structure_score + content_length_score
        
        return {
            'url': url,
            'title': title,
            'is_processable': is_processable,
            'content_type': content_type,
            'confidence': confidence,
            'content_length': len(text_content),
            'has_structure': structure_score > 0.2,
            'estimated_value': confidence * (1 if is_processable else 0),
            'type_scores': type_scores,
            'structure_score': structure_score
        }
    
    def _extract_enhanced_title(self, soup: BeautifulSoup, url: str) -> str:
        """Extract the most relevant title from the page."""
        # Try different title sources in order of preference
        title_sources = [
            soup.find('h1'),
            soup.find('title'),
            soup.find('h2'),
            soup.find('h3'),
            soup.find(['div', 'span'], class_=re.compile(r'title|heading', re.I))
        ]
        
        for source in title_sources:
            if source:
                title = source.get_text().strip()
                if title and len(title) > 10 and len(title) < 200:
                    # Clean up title
                    title = re.sub(r'\s+', ' ', title)
                    return title
        
        # Fallback to URL-based title
        return url.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
    
    def _calculate_structure_score(self, soup: BeautifulSoup) -> float:
        """Calculate how well-structured the content is."""
        score = 0.0
        
        # Check for various structural elements
        structure_elements = {
            'table': 0.3,
            'ol': 0.2,
            'ul': 0.2,
            'dl': 0.1,
            'form': 0.1,
            'article': 0.2,
            'section': 0.1
        }
        
        for element, value in structure_elements.items():
            count = len(soup.find_all(element))
            if count > 0:
                score += min(count * value, value * 3)  # Cap the bonus
        
        # Check for content organization
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        if len(headings) > 2:
            score += 0.1
        
        # Check for navigation elements
        nav_elements = soup.find_all(['nav']) + soup.find_all(class_=re.compile(r'nav|menu', re.I))
        if nav_elements:
            score += 0.1
        
        return min(score, 1.0)
    
    def discover_with_pagination(self, base_url: str, max_pages: int = 5) -> Dict[str, Any]:
        """
        Discover URLs with intelligent pagination handling.
        
        Args:
            base_url: Base URL to start discovery from
            max_pages: Maximum number of pages to process
            
        Returns:
            Dictionary with discovered URLs from multiple pages
        """
        try:
            print(f"🔎 Discovering URLs with pagination from: {base_url}")
            
            all_discovered_urls = []
            processed_pages = set()
            pages_to_process = [base_url]
            page_count = 0
            
            while pages_to_process and page_count < max_pages:
                current_page = pages_to_process.pop(0)
                
                if current_page in processed_pages:
                    continue
                
                processed_pages.add(current_page)
                page_count += 1
                
                print(f"   📄 Processing page {page_count}: {current_page}")
                
                try:
                    response = self.session.get(current_page, timeout=15)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extract URLs from current page
                    page_urls = self._extract_page_urls(soup, current_page, base_url)
                    
                    # Analyze each URL
                    for url_info in page_urls:
                        url_analysis = self._analyze_url_content(url_info['url'], soup)
                        if url_analysis['is_processable']:
                            all_discovered_urls.append(url_analysis)
                            print(f"      ✅ Found: {url_analysis['title'][:60]}...")
                    
                    # Find next page URLs
                    next_pages = self._find_pagination_urls(soup, current_page, base_url)
                    for next_page in next_pages:
                        if next_page not in processed_pages:
                            pages_to_process.append(next_page)
                
                except Exception as e:
                    print(f"   ⚠️  Error processing page {current_page}: {str(e)}")
                    continue
            
            print(f"   ✅ Total discovered: {len(all_discovered_urls)} URLs from {page_count} pages")
            
            return {
                'success': True,
                'discovered_urls': all_discovered_urls,
                'total_discovered': len(all_discovered_urls),
                'pages_processed': page_count,
                'base_url': base_url
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'base_url': base_url
            }
    
    def _extract_page_urls(self, soup: BeautifulSoup, current_url: str, base_url: str) -> List[Dict[str, str]]:
        """Extract URLs from the current page content."""
        urls = []
        base_domain = urlparse(base_url).netloc
        
        # Extract from tables (like the provided HTML structure)
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                links = row.find_all('a', href=True)
                for link in links:
                    href = link.get('href')
                    title = link.get_text().strip()
                    if href and title:
                        full_url = urljoin(current_url, href)
                        if urlparse(full_url).netloc == base_domain:
                            urls.append({
                                'url': full_url,
                                'title': title,
                                'source': 'table'
                            })
        
        # Extract from content divs
        content_areas = soup.find_all(['div', 'section'], class_=re.compile(r'content|main|post|article', re.I))
        for content in content_areas:
            links = content.find_all('a', href=True)
            for link in links[:20]:  # Limit per content area
                href = link.get('href')
                title = link.get_text().strip()
                if href and title and len(title) > 5:
                    full_url = urljoin(current_url, href)
                    if urlparse(full_url).netloc == base_domain:
                        urls.append({
                            'url': full_url,
                            'title': title,
                            'source': 'content'
                        })
        
        return urls
    
    def _find_pagination_urls(self, soup: BeautifulSoup, current_url: str, base_url: str) -> List[str]:
        """Find pagination URLs for next pages."""
        pagination_urls = []
        base_domain = urlparse(base_url).netloc
        
        # Look for pagination elements
        pagination_selectors = [
            '.pagination a',
            '.page-item a',
            '.page-link',
            'a[rel="next"]',
            '.next',
            '.show-more',
            '.load-more'
        ]
        
        for selector in pagination_selectors:
            elements = soup.select(selector)
            for element in elements:
                href = element.get('href')
                text = element.get_text().strip().lower()
                
                # Look for next page indicators
                if href and any(keyword in text for keyword in ['next', 'more', '>', '→', 'show more']):
                    full_url = urljoin(current_url, href)
                    if urlparse(full_url).netloc == base_domain:
                        pagination_urls.append(full_url)
                
                # Look for numbered pages
                elif href and text.isdigit():
                    full_url = urljoin(current_url, href)
                    if urlparse(full_url).netloc == base_domain:
                        pagination_urls.append(full_url)
        
        # Look for page parameter in current URL and increment
        if '?page=' in current_url or '&page=' in current_url:
            try:
                import urllib.parse as urlparse_lib
                parsed_url = urlparse_lib.urlparse(current_url)
                query_params = urlparse_lib.parse_qs(parsed_url.query)
                
                if 'page' in query_params:
                    current_page = int(query_params['page'][0])
                    next_page = current_page + 1
                    
                    # Build next page URL
                    query_params['page'] = [str(next_page)]
                    new_query = urlparse_lib.urlencode(query_params, doseq=True)
                    next_url = urlparse_lib.urlunparse((
                        parsed_url.scheme, parsed_url.netloc, parsed_url.path,
                        parsed_url.params, new_query, parsed_url.fragment
                    ))
                    pagination_urls.append(next_url)
            except:
                pass
        
        return list(set(pagination_urls))[:3]  # Limit to 3 next pages
    
    def create_dynamic_website_config(self, base_url: str) -> Dict[str, Any]:
        """
        Create a dynamic website configuration by analyzing the website.
        
        Args:
            base_url: Base URL of the website to analyze
            
        Returns:
            Complete website configuration
        """
        try:
            print(f"\n🤖 Creating Dynamic Configuration for: {base_url}")
            print("=" * 60)
            
            # Step 1: Detect website characteristics
            detection_result = self.detect_website_type(base_url)
            if not detection_result['success']:
                return detection_result
            
            website_info = detection_result['detection_result']
            
            # Step 2: Discover processable URLs
            discovery_result = self.discover_processable_urls(base_url, max_depth=2)
            processable_urls = discovery_result.get('discovered_urls', []) if discovery_result['success'] else []
            
            # Step 3: Create configuration
            config = {
                'website_name': website_info['website_name'],
                'base_url': base_url,
                'website_type': website_info['website_type'],
                'description': website_info['description'],
                'is_active': True,
                'processing_flags': website_info['processing_flags'],
                'capabilities': website_info['capabilities'],
                'navigation_structure': website_info['navigation_structure'],
                'processable_urls': [url['url'] for url in processable_urls if url['confidence'] > 0.3],
                'high_value_urls': [url['url'] for url in processable_urls if url['confidence'] > 0.7],
                'url_analysis': processable_urls,
                'confidence_score': website_info['confidence_score'],
                'auto_generated': True,
                'generation_timestamp': datetime.now().isoformat(),
                'recommended_settings': self._generate_recommended_settings(website_info, processable_urls)
            }
            
            print(f"✅ Dynamic Configuration Created!")
            print(f"   Website: {config['website_name']}")
            print(f"   Type: {config['website_type']}")
            print(f"   Processable URLs: {len(config['processable_urls'])}")
            print(f"   High Value URLs: {len(config['high_value_urls'])}")
            print(f"   Confidence: {config['confidence_score']:.1%}")
            
            return {
                'success': True,
                'config': config
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'base_url': base_url
            }
    
    def _generate_recommended_settings(self, website_info: Dict[str, Any], processable_urls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate recommended processing settings."""
        settings = {
            'max_urls_per_session': min(len(processable_urls), 20),
            'recommended_delay': 1.0 if len(processable_urls) > 10 else 0.5,
            'priority_urls': [url for url in processable_urls if url['confidence'] > 0.8],
            'processing_order': 'confidence_desc',  # Process high-confidence URLs first
            'retry_failed_urls': True,
            'enable_caching': True,
            'max_concurrent_requests': 1  # Be respectful to servers
        }
        
        return settings


# Convenience functions
def auto_detect_and_configure_website(base_url: str) -> Dict[str, Any]:
    """Automatically detect and configure a website."""
    service = WebsiteAutoDetectionService()
    return service.create_dynamic_website_config(base_url)

def batch_auto_detect_websites(urls: List[str]) -> Dict[str, Any]:
    """Auto-detect multiple websites in batch."""
    service = WebsiteAutoDetectionService()
    results = []
    
    for url in urls:
        print(f"\n{'='*60}")
        result = service.create_dynamic_website_config(url)
        results.append(result)
    
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    return {
        'total_processed': len(urls),
        'successful': len(successful),
        'failed': len(failed),
        'results': results,
        'summary': {
            'success_rate': len(successful) / len(urls) if urls else 0,
            'configurations_created': len(successful)
        }
    }

if __name__ == "__main__":
    # Test the service
    test_urls = [
        "https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf"
        #"https://pakmcqs.com",
        #"https://testpoint.pk"
    ]
    
    print("🤖 Testing Auto-Detection Service")
    print("=" * 50)
    
    for url in test_urls:
        result = auto_detect_and_configure_website(url)
        if result['success']:
            config = result['config']
            print(f"\n✅ {config['website_name']}: {len(config['processable_urls'])} URLs found")
        else:
            print(f"\n❌ Failed to configure {url}: {result['error']}")
