#!/usr/bin/env python3
"""
Paper MCQ Collector Service (Database Compatible Version)

This version works with the current database structure without option_e field.
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urljoin, urlparse
import logging

import requests
from bs4 import BeautifulSoup
from sqlmodel import select, Session, or_
import json

# Import models
from app.models.website import Website
from app.models.top_bar import TopBar
from app.models.side_bar import SideBar
from app.models.paper import PaperModel, PaperMCQ
from app.models.category import Category, create_slug
from app.models.mcqs_bank import MCQ, AnswerOption
from app.models.scraping_state import ScrapingState, ScrapingStatus
from app.database import get_session

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "PaperMCQ-Collector/1.0"}


def truncate_mcq_content(text: str, max_length: int = 500) -> str:
    """Truncate MCQ content while preserving question integrity"""
    if not text or len(text) <= max_length:
        return text
    
    # For content with "Related MCQs:" - truncate after the main question
    if "Related Mcqs:" in text:
        # Find the first question mark and truncate after it
        question_end = text.find('?')
        if question_end != -1 and question_end < max_length:
            return text[:question_end + 1].strip()
        
        # If no question mark found or it's too far, take content before "Related Mcqs:"
        related_start = text.find("Related Mcqs:")
        if related_start > 0:
            return text[:related_start].strip()
    
    # For options, if it contains "A. B. C. D." pattern, take only the first option
    if " A. " in text and " B. " in text:
        first_option_end = text.find(" B. ")
        if first_option_end > 0 and first_option_end < max_length:
            return text[:first_option_end].strip()
    
    # Standard truncation
    truncated = text[:max_length].rsplit(' ', 1)[0]  # Don't cut in middle of word
    return truncated.strip() + "..." if len(truncated) < len(text) else truncated


class URLValidator:
    """Validates if a URL exists in database tables before scraping"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def validate_url(self, url: str) -> Dict[str, Any]:
        """Check if URL exists in website, top_bar, or side_bar tables"""
        # Check website table
        website_stmt = select(Website).where(Website.current_page_url == url)
        website = self.session.exec(website_stmt).first()
        if website:
            return {
                "valid": True,
                "source": "website",
                "record": website,
                "website_id": website.web_id
            }
        
        # Check top_bar table
        top_bar_stmt = select(TopBar).where(TopBar.url == url)
        top_bar = self.session.exec(top_bar_stmt).first()
        if top_bar:
            return {
                "valid": True,
                "source": "top_bar",
                "record": top_bar,
                "website_id": top_bar.website_id
            }
        
        # Check side_bar table
        side_bar_stmt = select(SideBar).where(SideBar.url == url)
        side_bar = self.session.exec(side_bar_stmt).first()
        if side_bar:
            return {
                "valid": True,
                "source": "side_bar", 
                "record": side_bar,
                "website_id": side_bar.website_id
            }
        
        return {"valid": False, "source": None, "record": None, "website_id": None}


class WebsiteTracker:
    """Tracks website paper URLs and updates scraping status"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def find_paper_url_match(self, url: str) -> Optional[Dict[str, Any]]:
        """Find website record containing the URL in paper_urls JSON field"""
        try:
            # Get all website records with paper_urls
            stmt = select(Website).where(Website.paper_urls.isnot(None))
            websites = self.session.exec(stmt).all()
            
            for website in websites:
                if website.paper_urls:
                    for i, paper_url_obj in enumerate(website.paper_urls):
                        if isinstance(paper_url_obj, dict) and paper_url_obj.get('url') == url:
                            return {
                                "website": website,
                                "url_index": i,
                                "url_object": paper_url_obj
                            }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error finding paper URL match: {e}")
            return None
    
    def update_scraped_status(self, url: str, paper: PaperModel, category: Category, 
                            total_mcqs: int, pages_processed: int) -> bool:
        """Update the is_scraped status and populate remaining details after successful scraping"""
        try:
            match_result = self.find_paper_url_match(url)
            if not match_result:
                logger.info(f"ℹ️ No paper_urls match found for URL: {url}")
                return False
            
            website = match_result["website"]
            url_index = match_result["url_index"]
            url_object = match_result["url_object"]
            
            # Update the URL object with scraping details
            updated_url_object = url_object.copy()
            updated_url_object["is_scraped"] = True
            updated_url_object["scraped_at"] = datetime.now(timezone.utc).isoformat()
            updated_url_object["paper_id"] = paper.id
            updated_url_object["paper_title"] = paper.title
            updated_url_object["category_name"] = category.name
            updated_url_object["category_slug"] = category.slug
            updated_url_object["total_mcqs"] = total_mcqs
            updated_url_object["pages_processed"] = pages_processed
            
            # Update the paper_urls array
            updated_paper_urls = website.paper_urls.copy()
            updated_paper_urls[url_index] = updated_url_object
            
            # Update the website record
            website.paper_urls = updated_paper_urls
            website.updated_at = datetime.now(timezone.utc)
            
            # If this was the current_page_url, update it
            if website.current_page_url == url:
                website.last_scrapped_url = paper.id
            
            self.session.add(website)
            self.session.commit()
            
            logger.info(f"✅ Updated website record {website.web_id} - marked URL as scraped")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update scraped status: {e}")
            self.session.rollback()
            return False


class CategoryManager:
    """Manages dynamic category creation from URLs and titles"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def extract_category_from_url(self, url: str, title: Optional[str] = None) -> Tuple[str, str, List[str]]:
        """Extract category information from URL and title"""
        parsed = urlparse(url)
        path_parts = [part for part in parsed.path.split('/') if part]
        
        # Extract category from URL path
        category_parts = []
        tags = []
        
        # Common patterns for different websites
        if 'testpoint' in parsed.netloc.lower():
            if 'paper-mcqs' in path_parts:
                idx = path_parts.index('paper-mcqs')
                if idx + 2 < len(path_parts):
                    category_parts.append(path_parts[idx + 2])
            elif 'important-mcqs' in path_parts:
                idx = path_parts.index('important-mcqs')
                if idx + 1 < len(path_parts):
                    category_parts.append(path_parts[idx + 1])
            elif 'past-papers-mcqs' in path_parts:
                idx = path_parts.index('past-papers-mcqs')
                if idx + 1 < len(path_parts):
                    category_parts.append(path_parts[idx + 1])
        
        elif 'pakmcqs' in parsed.netloc.lower():
            if 'category' in path_parts:
                idx = path_parts.index('category')
                if idx + 1 < len(path_parts):
                    category_parts.append(path_parts[idx + 1])
        
        # Use title if available and path extraction failed
        if not category_parts and title:
            category_parts.append(title)
        
        # Fallback to last meaningful path part
        if not category_parts and path_parts:
            category_parts.append(path_parts[-1])
        
        # Create category name
        if category_parts:
            category_name = ' '.join(category_parts).replace('-', ' ').replace('_', ' ')
            category_name = re.sub(r'\s+', ' ', category_name).strip().title()
        else:
            category_name = "General MCQs"
        
        # Generate slug
        category_slug = create_slug(category_name)
        
        # Extract tags from URL and title
        for part in path_parts:
            if len(part) > 2 and part not in ['mcqs', 'paper', 'past', 'papers', 'important']:
                tags.append(part.replace('-', ' ').replace('_', ' ').title())
        
        if title:
            # Extract year from title
            year_match = re.search(r'\b(20\d{2})\b', title)
            if year_match:
                tags.append(f"Year {year_match.group(1)}")
            
            # Extract common keywords
            keywords = ['ppsc', 'fpsc', 'css', 'pms', 'lecturer', 'assistant', 'clerk', 'officer']
            for keyword in keywords:
                if keyword.lower() in title.lower():
                    tags.append(keyword.upper())
        
        return category_name, category_slug, list(set(tags))
    
    def get_or_create_category(self, category_name: str, category_slug: str, tags: List[str]) -> Category:
        """Get existing category or create new one"""
        # Check if category exists
        stmt = select(Category).where(Category.slug == category_slug)
        category = self.session.exec(stmt).first()
        
        if not category:
            # Create new category using the existing structure
            category = Category(
                name=category_name,
                slug=category_slug
            )
            self.session.add(category)
            try:
                self.session.commit()
                self.session.refresh(category)
                logger.info(f"✅ Created category: {category_name} ({category_slug})")
            except Exception as e:
                self.session.rollback()
                logger.error(f"❌ Failed to create category: {e}")
                raise
        
        return category


class PaperMCQCollectorV1:
    """Main collector class compatible with current database schema"""
    
    def __init__(self, session: Session):
        self.session = session
        self.requests_session = requests.Session()
        self.requests_session.headers.update(HEADERS)
        self.url_validator = URLValidator(session)
        self.category_manager = CategoryManager(session)
        self.website_tracker = WebsiteTracker(session)
    
    def get_or_create_scraping_state(self, url: str, website_id: int, max_pages: Optional[int] = None) -> ScrapingState:
        """Get existing scraping state or create new one"""
        # Check for existing state
        stmt = select(ScrapingState).where(
            (ScrapingState.base_url == url) &
            (ScrapingState.status.in_([ScrapingStatus.PENDING, ScrapingStatus.IN_PROGRESS, ScrapingStatus.PAUSED]))
        )
        existing_state = self.session.exec(stmt).first()
        
        if existing_state:
            logger.info(f"📋 Found existing scraping state: {existing_state.status.value}")
            return existing_state
        
        # Create new state
        state = ScrapingState(
            base_url=url,
            website_id=website_id,
            max_pages_limit=max_pages,
            status=ScrapingStatus.PENDING
        )
        
        self.session.add(state)
        self.session.commit()
        self.session.refresh(state)
        
        logger.info(f"📋 Created new scraping state")
        return state
    
    def list_resumable_sessions(self) -> List[ScrapingState]:
        """List all sessions that can be resumed"""
        stmt = select(ScrapingState).where(
            ScrapingState.status.in_([ScrapingStatus.PAUSED, ScrapingStatus.FAILED])
        ).order_by(ScrapingState.updated_at.desc())
        
        return list(self.session.exec(stmt).all())
    
    def resume_scraping_session(self, state_id: int) -> Dict[str, Any]:
        """Resume a paused or failed scraping session"""
        stmt = select(ScrapingState).where(ScrapingState.id == state_id)
        state = self.session.exec(stmt).first()
        
        if not state:
            return {"success": False, "error": f"Scraping state {state_id} not found"}
        
        if not state.can_resume():
            return {"success": False, "error": f"Session cannot be resumed (status: {state.status.value})"}
        
        logger.info(f"🔄 Resuming scraping session {state_id}")
        return self.collect_from_url_with_state(state.base_url, existing_state=state)
    
    def collect_from_url_with_state(self, url: str, max_pages: Optional[int] = None, 
                                   existing_state: Optional[ScrapingState] = None) -> Dict[str, Any]:
        """Enhanced collect method with resume state support"""
        print("🔍 SEARCHING...")
        logger.info(f"🎯 Starting collection from: {url}")
        
        # Step 1: Validate URL exists in database
        print("🔍 VALIDATING URL...")
        validation_result = self.url_validator.validate_url(url)
        if not validation_result["valid"]:
            logger.error(f"❌ URL not found in database tables: {url}")
            return {"success": False, "error": "URL not found in database", "url": url}
        
        print(f"✅ VALIDATED - Source: {validation_result['source']}")
        logger.info(f"✅ URL validated - Source: {validation_result['source']}")
        
        try:
            # Step 2: Get or create scraping state
            print("📋 MANAGING SCRAPING STATE...")
            if existing_state:
                scraping_state = existing_state
                print(f"   🔄 Using existing state (ID: {scraping_state.id})")
            else:
                scraping_state = self.get_or_create_scraping_state(url, validation_result["website_id"], max_pages)
                print(f"   📝 Created new state (ID: {scraping_state.id})")
            
            # Update state metadata
            scraping_state.validation_source = validation_result["source"]
            scraping_state.mark_as_started()
            self.session.commit()
            
            # Step 3: Fetch the page (if not resuming from middle)
            print("🌐 GETTING PAGE...")
            response = self.requests_session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            page_title = soup.find('title').get_text(strip=True) if soup.find('title') else "Unknown Title"
            
            # Step 4: Create or get paper record
            print("📄 CREATING PAPER...")
            if scraping_state.paper_id:
                # Resume: Get existing paper
                paper_stmt = select(PaperModel).where(PaperModel.id == scraping_state.paper_id)
                paper = self.session.exec(paper_stmt).first()
                if not paper:
                    logger.error(f"❌ Paper {scraping_state.paper_id} not found for resume")
                    scraping_state.mark_as_failed("Associated paper not found")
                    self.session.commit()
                    return {"success": False, "error": "Associated paper not found", "url": url}
            else:
                # New: Create paper
                paper = self.create_paper_record(
                    url=url,
                    title=page_title,
                    website_id=validation_result["website_id"],
                    validation_result=validation_result
                )
                scraping_state.paper_id = paper.id
                scraping_state.paper_title = paper.title
            
            # Step 5: Create/get category
            print("🏷️ SETTING CATEGORY...")
            if scraping_state.category_name and scraping_state.category_slug:
                # Resume: Get existing category
                category_stmt = select(Category).where(Category.slug == scraping_state.category_slug)
                category = self.session.exec(category_stmt).first()
                if not category:
                    # Category might have been deleted, recreate
                    category_name, category_slug, tags = self.category_manager.extract_category_from_url(url, page_title)
                    category = self.category_manager.get_or_create_category(category_name, category_slug, tags)
            else:
                # New: Create category
                category_name, category_slug, tags = self.category_manager.extract_category_from_url(url, page_title)
                category = self.category_manager.get_or_create_category(category_name, category_slug, tags)
                scraping_state.category_name = category.name
                scraping_state.category_slug = category.slug
            
            # Step 6: Crawl pages (with resume support)
            print("🔎 FINDING PAGES...")
            if not scraping_state.discovered_pages:
                print("   🌐 Starting page discovery (this may take a moment)...")
                import time
                start_time = time.time()
                
                pages = self.crawl_pages(url, max_pages, scraping_state)
                
                discovery_time = time.time() - start_time
                print(f"📄 FOUND {len(pages)} PAGES (took {discovery_time:.1f}s)")
            else:
                pages = scraping_state.discovered_pages
                print(f"📄 USING {len(pages)} PREVIOUSLY DISCOVERED PAGES")
            
            logger.info(f"📄 Processing {len(pages)} pages")
            
            # Step 7: Process pages (with resume support)
            start_page_index = scraping_state.current_page_index
            print(f"📖 PROCESSING PAGES (starting from page {start_page_index + 1})...")
            
            for page_index in range(start_page_index, len(pages)):
                page_url = pages[page_index]
                page_num = page_index + 1
                
                # Check if this page was already processed
                if page_url in scraping_state.processed_pages:
                    print(f"   ⏭️ Page {page_num}/{len(pages)} already processed, skipping")
                    scraping_state.advance_to_next_page()
                    continue
                
                print(f"📖 SCRAPING PAGE {page_num}/{len(pages)}...")
                logger.info(f"🔄 Processing page {page_num}/{len(pages)}: {page_url}")
                
                try:
                    if page_url != url:  # Already fetched the first page
                        response = self.requests_session.get(page_url, timeout=30)
                        response.raise_for_status()
                    
                    # Extract MCQs
                    mcqs = self.extract_mcqs_from_html(response.text, paper)
                    print(f"   📝 FOUND {len(mcqs)} MCQs")
                    logger.info(f"📝 Extracted {len(mcqs)} MCQs from page {page_num}")
                    
                    # Save MCQs
                    saved_count = 0
                    new_count = 0
                    for mcq_data in mcqs:
                        mcq = self.save_mcq(mcq_data, paper, category)
                        if mcq:
                            saved_count += 1
                            # Check if it's a new MCQ
                            if mcq.created_at and mcq.created_at.replace(microsecond=0) >= datetime.now().replace(microsecond=0, second=0):
                                new_count += 1
                    
                    print(f"   💾 SAVED {saved_count} MCQs ({new_count} new)")
                    
                    # Update state
                    scraping_state.mark_page_as_processed(page_url, len(mcqs), saved_count, new_count)
                    scraping_state.advance_to_next_page()
                    self.session.commit()
                    
                except Exception as e:
                    print(f"   ❌ ERROR ON PAGE {page_num}: {e}")
                    logger.error(f"❌ Error processing page {page_num}: {e}")
                    scraping_state.mark_page_as_failed(page_url, str(e))
                    scraping_state.advance_to_next_page()
                    self.session.commit()
                    continue
            
            # Step 8: Final state update
            print("💾 SAVING TO DATABASE...")
            scraping_state.mark_as_completed()
            
            try:
                self.session.commit()
            except Exception as e:
                self.session.rollback()
                logger.error(f"❌ Final commit failed: {e}")
                scraping_state.mark_as_failed(f"Final commit failed: {e}")
                self.session.commit()
            
            result = {
                "success": True,
                "url": url,
                "scraping_state_id": scraping_state.id,
                "paper_id": paper.id,
                "paper_title": paper.title,
                "category_name": category.name,
                "category_slug": category.slug,
                "pages_processed": scraping_state.pages_processed,
                "total_pages": scraping_state.total_pages_discovered,
                "total_mcqs": scraping_state.total_mcqs_saved,
                "new_mcqs": scraping_state.new_mcqs_created,
                "failed_pages": len(scraping_state.failed_pages),
                "validation_source": validation_result["source"]
            }
            
            # Step 9: Update website record tracking
            print("🗂️ UPDATING WEBSITE RECORD...")
            website_updated = self.website_tracker.update_scraped_status(
                url, paper, category, scraping_state.total_mcqs_saved, scraping_state.pages_processed
            )
            result["website_updated"] = website_updated
            
            print(f"✅ COMPLETED! {scraping_state.total_mcqs_saved} MCQs ({scraping_state.new_mcqs_created} new)")
            logger.info(f"✅ Collection completed: {scraping_state.total_mcqs_saved} MCQs ({scraping_state.new_mcqs_created} new)")
            return result
            
        except Exception as e:
            logger.error(f"❌ Collection failed: {e}")
            if 'scraping_state' in locals():
                scraping_state.mark_as_failed(str(e))
                self.session.commit()
            return {"success": False, "error": str(e), "url": url}
    
    def create_paper_record(self, url: str, title: str, website_id: int, validation_result: Dict) -> PaperModel:
        """Create paper record with metadata"""
        # Check if paper already exists
        stmt = select(PaperModel).where(PaperModel.paper_url == url)
        existing_paper = self.session.exec(stmt).first()
        
        if existing_paper:
            logger.info(f"📄 Paper already exists: {title}")
            return existing_paper
        
        # Extract year from title or URL
        year = None
        year_match = re.search(r'\b(20\d{2})\b', title)
        if year_match:
            year = int(year_match.group(1))
        
        # Determine paper type
        paper_type = "General"
        if any(word in title.lower() for word in ['past', 'paper']):
            paper_type = "Past Paper"
        elif any(word in title.lower() for word in ['important', 'mcq']):
            paper_type = "Important MCQs"
        elif any(word in title.lower() for word in ['test', 'quiz']):
            paper_type = "Test/Quiz"
        
        # Extract difficulty
        difficulty = "Medium"
        if any(word in title.lower() for word in ['basic', 'easy', 'beginner']):
            difficulty = "Easy"
        elif any(word in title.lower() for word in ['advanced', 'hard', 'difficult']):
            difficulty = "Hard"
        
        # Create paper
        paper = PaperModel(
            website_id=website_id,
            title=title,
            paper_url=url,
            year=year,
            paper_type=paper_type,
            difficulty=difficulty,
            tags=f"Source: {validation_result['source']}"
        )
        
        self.session.add(paper)
        try:
            self.session.commit()
            self.session.refresh(paper)
            logger.info(f"✅ Created paper: {title}")
            return paper
        except Exception as e:
            self.session.rollback()
            logger.error(f"❌ Failed to create paper: {e}")
            raise
    
    def extract_mcqs_from_html(self, html: str, paper: PaperModel) -> List[Dict[str, Any]]:
        """Extract MCQs from HTML content"""
        soup = BeautifulSoup(html, 'html.parser')
        mcqs = []
        
        # Check if this is a category/listing page or an individual MCQ page
        # Category pages have multiple article links, individual pages have the actual MCQ
        articles = soup.find_all('article')
        
        if len(articles) > 5:  # This looks like a category/listing page
            logger.info(f"📋 Detected category page with {len(articles)} articles - extracting MCQ links")
            return self._extract_mcqs_from_category_page(soup, paper)
        else:
            logger.info(f"📖 Detected individual MCQ page - extracting MCQ content")
            return self._extract_mcqs_from_individual_page(soup, paper)
    
    def _extract_mcqs_from_category_page(self, soup: BeautifulSoup, paper: PaperModel) -> List[Dict[str, Any]]:
        """Extract MCQs by following links from category pages (for sites like pakmcqs.com)"""
        mcqs = []
        
        # Find all article links that might lead to individual MCQs
        articles = soup.find_all('article')
        logger.info(f"🔗 Found {len(articles)} article links to process")
        
        for i, article in enumerate(articles[:5]):  # Limit to 5 per page to avoid overwhelming
            try:
                # Find the main link in the article
                title_link = article.find('a', href=True)
                if not title_link:
                    continue
                    
                mcq_url = title_link.get('href')
                mcq_title = title_link.get_text(strip=True)
                
                if not mcq_url or len(mcq_title) < 5:
                    continue
                
                # Make sure it's a full URL
                if not mcq_url.startswith('http'):
                    mcq_url = urljoin(paper.paper_url, mcq_url)
                
                logger.info(f"  🔗 Fetching MCQ {i+1}: {mcq_title[:50]}...")
                
                # Fetch the individual MCQ page
                response = self.requests_session.get(mcq_url, timeout=15)
                response.raise_for_status()
                
                # Extract MCQs from the individual page
                individual_soup = BeautifulSoup(response.text, 'html.parser')
                individual_mcqs = self._extract_mcqs_from_individual_page(individual_soup, paper)
                
                mcqs.extend(individual_mcqs)
                logger.info(f"  ✅ Extracted {len(individual_mcqs)} MCQs from {mcq_title[:30]}...")
                
            except Exception as e:
                logger.warning(f"  ⚠️ Error fetching MCQ from article {i+1}: {e}")
                continue
        
        logger.info(f"📊 Total MCQs extracted from category page: {len(mcqs)}")
        return mcqs
    
    def _extract_mcqs_from_individual_page(self, soup: BeautifulSoup, paper: PaperModel) -> List[Dict[str, Any]]:
        """Extract MCQs from individual MCQ pages"""
        mcqs = []
        
        # Try different content selectors for individual pages
        content_selectors = [
            ".entry-content",
            "#content",
            ".content",
            ".post-content",
            ".main-content",
            "main",
            "article"
        ]
        
        content = None
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                break
        
        if not content:
            content = soup.find('body')
        
        if not content:
            logger.warning("⚠️ No content container found")
            return mcqs
        
        # Look for MCQ patterns in individual pages
        mcq_blocks = []
        
        # Method 1: Look for ordered lists (common in MCQ sites)
        ol_tags = content.find_all('ol')
        for ol in ol_tags:
            # Check if this ol has at least 4 options (typical MCQ)
            li_items = ol.find_all('li', recursive=False)
            if len(li_items) >= 4:
                # Look for a question before this ol
                question_element = self._find_question_before_element(ol)
                if question_element:
                    mcq_blocks.append({'question': question_element, 'options': ol})
        
        # Method 2: Look for paragraph + list combinations
        if not mcq_blocks:
            for p in content.find_all('p'):
                p_text = p.get_text(strip=True)
                if len(p_text) > 20 and '?' in p_text:  # Likely a question
                    # Look for a list after this paragraph
                    next_sibling = p.find_next_sibling(['ol', 'ul'])
                    if next_sibling:
                        li_items = next_sibling.find_all('li', recursive=False)
                        if len(li_items) >= 4:
                            mcq_blocks.append({'question': p, 'options': next_sibling})
        
        # Method 3: Look for div structures with questions and options
        if not mcq_blocks:
            for div in content.find_all('div'):
                # Look for divs that contain both question text and option lists
                question_text = div.get_text(strip=True)
                if len(question_text) > 20 and '?' in question_text:
                    ol_in_div = div.find(['ol', 'ul'])
                    if ol_in_div:
                        li_items = ol_in_div.find_all('li', recursive=False)
                        if len(li_items) >= 4:
                            mcq_blocks.append({'question': div, 'options': ol_in_div})
        
        logger.info(f"🎯 Found {len(mcq_blocks)} MCQ blocks on individual page")
        
        # Extract MCQs from found blocks
        for block in mcq_blocks:
            mcq_data = self._extract_single_mcq_from_block(block)
            if mcq_data:
                mcqs.append(mcq_data)
        
        return mcqs
    
    def _find_question_before_element(self, element):
        """Find question text before an options list"""
        # Look for siblings before this element
        for sibling in element.previous_siblings:
            if hasattr(sibling, 'get_text'):
                text = sibling.get_text(strip=True)
                if len(text) > 20 and '?' in text:
                    return sibling
        
        # Look for parent's previous siblings
        parent = element.parent
        if parent:
            for sibling in parent.previous_siblings:
                if hasattr(sibling, 'get_text'):
                    text = sibling.get_text(strip=True)
                    if len(text) > 20 and '?' in text:
                        return sibling
        
        return None
    
    def _extract_single_mcq_from_block(self, block: Dict) -> Optional[Dict[str, Any]]:
        """Extract single MCQ from a question-options block"""
        try:
            question_element = block['question']
            options_element = block['options']
            
            # Extract question text
            question_text = question_element.get_text(strip=True)
            
            # Clean up question text (remove extra whitespace, numbers, etc.)
            question_text = re.sub(r'^\d+\.?\s*', '', question_text)  # Remove leading numbers
            question_text = re.sub(r'\s+', ' ', question_text).strip()
            
            if not question_text or len(question_text) < 10:
                return None
            
            # Extract options
            option_items = options_element.find_all('li', recursive=False)
            if len(option_items) < 4:
                return None
            
            all_options = []
            correct_index = None
            
            for i, item in enumerate(option_items):
                option_text = item.get_text(strip=True)
                # Clean up option text
                option_text = re.sub(r'^[A-D]\.?\s*', '', option_text)  # Remove leading A. B. etc.
                option_text = re.sub(r'\s+', ' ', option_text).strip()
                
                all_options.append(option_text)
                
                # Check if this option is marked as correct
                classes = item.get("class", [])
                if any(cls.lower() in ["correct", "right", "answer"] for cls in classes):
                    correct_index = i
                
                # Check for styling that indicates correct answer
                if correct_index is None and item.get("style"):
                    style = item.get("style", "").lower()
                    if any(indicator in style for indicator in ["green", "correct", "#0f0", "#00ff00"]):
                        correct_index = i
            
            # Handle options (limit to 4, store extras)
            additional_options = []
            if len(all_options) > 4:
                main_options = all_options[:4]
                additional_options = all_options[4:]
                
                if correct_index is not None and correct_index >= 4:
                    # Correct answer is in additional options
                    original_correct_option = all_options[correct_index]
                    main_options[3] = "Other"
                    correct_index = 3
                    additional_options.insert(0, f"**Correct Answer:** {original_correct_option}")
                else:
                    main_options[3] = "Other"
            else:
                main_options = all_options[:4]
                while len(main_options) < 4:
                    main_options.append("N/A")
            
            # Build MCQ data
            mcq_data = {
                "question_text": question_text,
                "option_a": main_options[0],
                "option_b": main_options[1],
                "option_c": main_options[2],
                "option_d": main_options[3],
                "correct_answer": None,
                "explanation": None,
                "additional_options": additional_options
            }
            
            # Set correct answer
            if correct_index is not None and correct_index < 4:
                answer_key = f"option_{chr(ord('a') + correct_index)}"
                try:
                    mcq_data["correct_answer"] = AnswerOption(answer_key)
                except ValueError:
                    logger.warning(f"⚠️ Invalid answer option: {answer_key}")
                    # If no correct answer found, try to infer from option styling or context
                    pass
            
            # If no correct answer found, try to find it in the content
            if not mcq_data["correct_answer"]:
                # Look for answer patterns in the surrounding content
                mcq_data["correct_answer"] = AnswerOption("option_a")  # Default to A if can't determine
            
            # Add explanation from additional options
            if additional_options:
                explanation_parts = ["**Additional Options:**"]
                for i, opt in enumerate(additional_options):
                    if opt.startswith("**Correct Answer:**"):
                        explanation_parts.append(opt)
                    else:
                        option_label = chr(ord('E') + i)
                        explanation_parts.append(f"{option_label}. {opt}")
                mcq_data["explanation"] = "\n".join(explanation_parts)
            
            return mcq_data
            
        except Exception as e:
            logger.warning(f"⚠️ Error extracting MCQ from block: {e}")
            return None
    
    def save_mcq(self, mcq_data: Dict[str, Any], paper: PaperModel, category: Category) -> Optional[MCQ]:
        """Save MCQ to database with duplicate checking"""
        # Skip if no correct answer
        if not mcq_data.get("correct_answer"):
            logger.warning(f"⚠️ Skipping MCQ (no correct answer): {mcq_data['question_text'][:50]}...")
            return None
        
        # Check for duplicates
        stmt = select(MCQ).where(
            (MCQ.question_text == mcq_data["question_text"]) &
            (MCQ.category_id == category.id)
        )
        existing_mcq = self.session.exec(stmt).first()
        
        if existing_mcq:
            # Create paper-mcq relationship if not exists
            paper_mcq_stmt = select(PaperMCQ).where(
                (PaperMCQ.paper_id == paper.id) &
                (PaperMCQ.mcq_id == existing_mcq.id)
            )
            if not self.session.exec(paper_mcq_stmt).first():
                paper_mcq = PaperMCQ(paper_id=paper.id, mcq_id=existing_mcq.id)
                self.session.add(paper_mcq)
            
            return existing_mcq
        
        # Create new MCQ (with content truncation)
        mcq = MCQ(
            question_text=truncate_mcq_content(mcq_data["question_text"], 255),
            option_a=truncate_mcq_content(mcq_data["option_a"], 200),
            option_b=truncate_mcq_content(mcq_data["option_b"], 200),
            option_c=truncate_mcq_content(mcq_data["option_c"], 200),
            option_d=truncate_mcq_content(mcq_data["option_d"], 200),
            correct_answer=mcq_data["correct_answer"],
            explanation=truncate_mcq_content(mcq_data.get("explanation", ""), 1000),
            category_id=category.id
        )
        
        self.session.add(mcq)
        try:
            self.session.commit()
            self.session.refresh(mcq)
            
            # Create paper-mcq relationship
            paper_mcq = PaperMCQ(paper_id=paper.id, mcq_id=mcq.id)
            self.session.add(paper_mcq)
            self.session.commit()
            
            # Only log in verbose mode - reduced clutter
            # logger.info(f"✅ Saved MCQ: {mcq_data['question_text'][:50]}...")
            return mcq
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"❌ Failed to save MCQ: {e}")
            return None
    
    def crawl_pages(self, base_url: str, max_pages: Optional[int] = None, 
                    resume_state: Optional[ScrapingState] = None) -> List[str]:
        """Crawl paginated content with unlimited pages and smart loop detection"""
        pages = []
        current_url = base_url
        page_count = 0
        seen_urls = set()  # Track all URLs we've seen to detect loops
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        # If resuming, load previous state
        if resume_state and resume_state.discovered_pages:
            pages = resume_state.discovered_pages.copy()
            page_count = len(pages)
            seen_urls = set(pages)
            print(f"🔄 Resuming from previous session: {page_count} pages already discovered")
            
            # Start from where we left off in discovery
            if page_count > 0:
                current_url = pages[-1]  # Start from last discovered page
        else:
            print(f"🔍 Starting fresh page discovery from: {base_url}")
        
        print(f"🎯 Page discovery mode: {'LIMITED to ' + str(max_pages) if max_pages else 'UNLIMITED'} pages")
        
        while current_url and (max_pages is None or page_count < max_pages):
            # Check if we've seen this URL before (loop detection)
            if current_url in seen_urls:
                print(f"   🔄 URL already seen: {current_url}")
                print(f"   🛑 Loop detected, stopping discovery")
                break
            
            page_count += 1
            pages.append(current_url)
            seen_urls.add(current_url)
            
            print(f"   📄 Found page {page_count}: {current_url}")
            
            # Update resume state if available
            if resume_state:
                resume_state.add_discovered_page(current_url)
            
            try:
                print(f"   🌐 Fetching page {page_count}...")
                response = self.requests_session.get(current_url, timeout=30)
                response.raise_for_status()
                print(f"   ✅ Page {page_count} loaded successfully")
                
                consecutive_errors = 0  # Reset error counter on success
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Look for next page link with multiple selectors
                print(f"   🔍 Looking for next page link...")
                next_selectors = [
                    'ul.pagination a.page-link[rel=next]',
                    'a[rel=next]',
                    '.pagination .next a',
                    '.page-numbers.next',
                    '.pagination-next',
                    '.next-page',
                    'a:contains("Next")',
                    'a:contains("›")',
                    'a:contains("»")'
                ]
                
                next_link = None
                for selector in next_selectors:
                    next_link = soup.select_one(selector)
                    if next_link and next_link.get('href'):
                        break
                
                if next_link and next_link.get('href'):
                    next_url = urljoin(base_url, next_link['href'])
                    
                    # Enhanced loop detection
                    if next_url in seen_urls:
                        print(f"   🔄 Next URL already processed: {next_url}")
                        print(f"   🛑 Loop detected, stopping discovery")
                        current_url = None
                    elif next_url == current_url:
                        print(f"   🔄 Same URL detected: {next_url}")
                        print(f"   🛑 Self-reference loop, stopping discovery")
                        current_url = None
                    else:
                        current_url = next_url
                        print(f"   ➡️ Next page found: {next_url}")
                else:
                    print(f"   🚫 No next page link found, pagination complete")
                    current_url = None
                    
            except requests.exceptions.RequestException as e:
                consecutive_errors += 1
                print(f"   ❌ Network error on page {page_count}: {e}")
                logger.warning(f"⚠️ Network error crawling page {current_url}: {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    print(f"   🛑 Too many consecutive errors ({max_consecutive_errors}), stopping discovery")
                    if resume_state:
                        resume_state.mark_page_as_failed(current_url, f"Network error: {e}")
                    break
                else:
                    print(f"   🔁 Will continue despite error ({consecutive_errors}/{max_consecutive_errors})")
                    current_url = None  # Stop discovery but don't fail completely
                    
            except Exception as e:
                consecutive_errors += 1
                print(f"   ❌ Unexpected error on page {page_count}: {e}")
                logger.error(f"❌ Unexpected error crawling page {current_url}: {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    print(f"   🛑 Too many consecutive errors, stopping discovery")
                    if resume_state:
                        resume_state.mark_page_as_failed(current_url, f"Unexpected error: {e}")
                    break
                else:
                    print(f"   🔁 Will continue despite error ({consecutive_errors}/{max_consecutive_errors})")
                    current_url = None
        
        # Final status
        if max_pages and page_count >= max_pages:
            print(f"   📊 Reached user-specified limit ({max_pages} pages)")
        elif consecutive_errors >= max_consecutive_errors:
            print(f"   ⚠️ Stopped due to consecutive errors")
        else:
            print(f"   ✅ Natural pagination end reached")
        
        print(f"🎯 Page discovery complete: {len(pages)} pages found")
        return pages
    
    def collect_from_url(self, url: str, max_pages: Optional[int] = None) -> Dict[str, Any]:
        """Main method to collect MCQs from a URL (backward compatibility)"""
        return self.collect_from_url_with_state(url, max_pages)


def main():
    """CLI interface for the paper MCQ collector"""
    parser = argparse.ArgumentParser(
        description="Collect MCQs from paper URLs (DB Compatible)",
        epilog="""
Examples:
  python paper_mcqs_collector_v1.py scrape "https://example.com/mcqs" --max-pages 5
  python paper_mcqs_collector_v1.py "https://example.com/mcqs"  (direct URL, unlimited pages)
  python paper_mcqs_collector_v1.py list
  python paper_mcqs_collector_v1.py resume 123
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Scrape command (default)
    scrape_parser = subparsers.add_parser('scrape', help='Scrape MCQs from a URL')
    scrape_parser.add_argument("url", help="URL to scrape MCQs from")
    scrape_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    scrape_parser.add_argument("--max-pages", type=int, help="Maximum number of pages to scrape (unlimited if not specified)")
    
    # Resume command
    resume_parser = subparsers.add_parser('resume', help='Resume a paused scraping session')
    resume_parser.add_argument("state_id", type=int, help="Scraping state ID to resume")
    resume_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    
    # List command
    list_parser = subparsers.add_parser('list', help='List resumable scraping sessions')
    list_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    
    # If no arguments provided, show help
    if len(sys.argv) == 1:
        parser.print_help()
        print("\n" + "="*60)
        print("🎯 Enhanced MCQ Scraper - Main Features:")
        print("  ✅ Unlimited page scraping (removes 50-page limit)")
        print("  ✅ Resume functionality for interrupted sessions")
        print("  ✅ Smart content extraction for multiple website types")
        print("  ✅ Database-compatible content truncation")
        print("="*60)
        sys.exit(0)
    
    # For backward compatibility, allow URL as first argument without subcommand
    if len(sys.argv) > 1 and not sys.argv[1] in ['scrape', 'resume', 'list', '-h', '--help']:
        # Insert 'scrape' command for backward compatibility
        sys.argv.insert(1, 'scrape')
    
    args = parser.parse_args()
    
    if args.verbose if hasattr(args, 'verbose') else False:
        logging.basicConfig(level=logging.DEBUG)
    
    # Get database session
    session_gen = get_session()
    session = next(session_gen)
    
    try:
        collector = PaperMCQCollectorV1(session)
        
        if args.command == 'scrape' or args.command is None:
            # Handle scrape command
            url = args.url
            max_pages = getattr(args, 'max_pages', None)
            
            print(f"🎯 Starting scraping with {'unlimited' if max_pages is None else max_pages} pages")
            result = collector.collect_from_url(url, max_pages)
            
            if result["success"]:
                print(f"\n🎉 SUCCESS!")
                print(f"📄 Paper: {result['paper_title']}")
                print(f"📂 Category: {result['category_name']}")
                print(f"📊 MCQs: {result['total_mcqs']} total ({result['new_mcqs']} new)")
                print(f"📄 Pages: {result['pages_processed']}/{result.get('total_pages', result['pages_processed'])}")
                if result.get('failed_pages', 0) > 0:
                    print(f"⚠️ Failed Pages: {result['failed_pages']}")
                print(f"🔗 Source: {result['validation_source']} table")
                website_status = "✅ Updated" if result.get('website_updated') else "ℹ️ No match found"
                print(f"🗂️ Website Record: {website_status}")
                if 'scraping_state_id' in result:
                    print(f"📋 Scraping State ID: {result['scraping_state_id']}")
            else:
                print(f"\n❌ FAILED: {result.get('error', 'Unknown error')}")
                sys.exit(1)
                
        elif args.command == 'resume':
            # Handle resume command
            state_id = args.state_id
            print(f"🔄 Resuming scraping session {state_id}")
            
            result = collector.resume_scraping_session(state_id)
            
            if result["success"]:
                print(f"\n🎉 RESUMED AND COMPLETED!")
                print(f"📄 Paper: {result['paper_title']}")
                print(f"📂 Category: {result['category_name']}")
                print(f"📊 MCQs: {result['total_mcqs']} total ({result['new_mcqs']} new)")
                print(f"📄 Pages: {result['pages_processed']}/{result.get('total_pages', result['pages_processed'])}")
                if result.get('failed_pages', 0) > 0:
                    print(f"⚠️ Failed Pages: {result['failed_pages']}")
                print(f"🔗 Source: {result['validation_source']} table")
                website_status = "✅ Updated" if result.get('website_updated') else "ℹ️ No match found"
                print(f"🗂️ Website Record: {website_status}")
            else:
                print(f"\n❌ RESUME FAILED: {result.get('error', 'Unknown error')}")
                sys.exit(1)
                
        elif args.command == 'list':
            # Handle list command
            print("📋 Resumable Scraping Sessions:")
            sessions = collector.list_resumable_sessions()
            
            if not sessions:
                print("   No resumable sessions found.")
            else:
                for session_state in sessions:
                    resume_info = session_state.get_resume_info()
                    print(f"\n   ID: {session_state.id}")
                    print(f"   URL: {session_state.base_url}")
                    print(f"   Status: {session_state.status.value}")
                    print(f"   Progress: {resume_info['processed_pages']}/{resume_info['total_pages']} pages ({resume_info['progress_percentage']:.1f}%)")
                    print(f"   MCQs: {resume_info['mcqs_collected']} ({resume_info['new_mcqs']} new)")
                    print(f"   Paper: {session_state.paper_title or 'Not created yet'}")
                    print(f"   Category: {session_state.category_name or 'Not set yet'}")
                    print(f"   Updated: {session_state.updated_at}")
                    if resume_info['failed_pages'] > 0:
                        print(f"   ⚠️ Failed Pages: {resume_info['failed_pages']}")
                    print(f"   Resume Command: python {sys.argv[0]} resume {session_state.id}")
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
    finally:
        try:
            session_gen.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
