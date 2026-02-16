

#!/usr/bin/env python3
"""
Paper MCQ Collector Service

This service scrapes MCQs from URLs that exist in the website, top_bar, or side_bar tables.
It validates URL existence before scraping and creates:
1. Paper records with metadata
2. Dynamic categories from URL/title with tags
3. MCQs with up to 5 options (A-E) and explanations in markdown format

Features:
- URL validation against database tables
- Automatic category creation from URL structure
- Dynamic MCQ options (4 or 5 options)
- Markdown explanations
- Comprehensive duplicate prevention
- Progress tracking and resumable scraping
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
from app.database import get_session

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "PaperMCQ-Collector/1.0"}


class URLValidator:
    """Validates if a URL exists in database tables before scraping"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def validate_url(self, url: str) -> Dict[str, Any]:
        """
        Check if URL exists in website, top_bar, or side_bar tables
        Returns validation result with source table and record info
        """
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
        """
        Extract category information from URL and title
        Returns: (category_name, category_slug, tags)
        """
        parsed = urlparse(url)
        path_parts = [part for part in parsed.path.split('/') if part]
        
        # Extract category from URL path
        category_parts = []
        tags = []
        
        # Common patterns for different websites
        if 'testpoint' in parsed.netloc.lower():
            # Extract from testpoint URLs
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
            # Extract from pakmcqs URLs
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


class PaperMCQCollector:
    """Main collector class for scraping paper MCQs"""
    
    def __init__(self, session: Session):
        self.session = session
        self.requests_session = requests.Session()
        self.requests_session.headers.update(HEADERS)
        self.url_validator = URLValidator(session)
        self.category_manager = CategoryManager(session)
        self.website_tracker = WebsiteTracker(session)
    
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
        
        # Try different selectors based on website structure
        content_selectors = [
            "#content",
            ".content",
            ".main-content",
            ".mcq-container",
            ".question-container"
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
        
        # Extract MCQ blocks
        mcq_blocks = []
        
        # Method 1: Find divs with h5 containing question links
        for block in content.find_all("div", recursive=False):
            h5 = block.find("h5")
            if h5 and h5.find("a"):
                mcq_blocks.append(block)
        
        # Method 2: Find question patterns
        if not mcq_blocks:
            for block in content.find_all(["div", "section"], class_=re.compile(r"question|mcq")):
                mcq_blocks.append(block)
        
        # Method 3: Find by structure (question + options list)
        if not mcq_blocks:
            for block in content.find_all("div"):
                if block.find(["h3", "h4", "h5", "p"]) and block.find("ol"):
                    mcq_blocks.append(block)
        
        logger.info(f"📋 Found {len(mcq_blocks)} potential MCQ blocks")
        
        for block in mcq_blocks:
            mcq_data = self._extract_single_mcq(block)
            if mcq_data:
                mcqs.append(mcq_data)
        
        return mcqs
    
    def _extract_single_mcq(self, block) -> Optional[Dict[str, Any]]:
        """Extract single MCQ from HTML block"""
        try:
            # Extract question text
            question_element = None
            for tag in ["h5", "h4", "h3", "p", "div"]:
                question_element = block.find(tag)
                if question_element:
                    # Look for link inside or use the element itself
                    link = question_element.find("a")
                    if link:
                        question_element = link
                    break
            
            if not question_element:
                return None
            
            question_text = question_element.get_text(strip=True)
            if not question_text or len(question_text) < 5:
                return None
            
            # Extract options
            options_list = block.find("ol", {"type": "A"}) or block.find("ol") or block.find("ul")
            if not options_list:
                return None
            
            option_items = options_list.find_all("li", recursive=False)
            if len(option_items) < 4:
                return None
            
            # Extract option texts
            options = []
            correct_index = None
            
            for i, item in enumerate(option_items):
                option_text = item.get_text(strip=True)
                options.append(option_text)
                
                # Check if this option is marked as correct
                classes = item.get("class", [])
                if any(cls.lower() in ["correct", "right", "answer"] for cls in classes):
                    correct_index = i
                
                # Also check for styling or special attributes
                if not correct_index and item.get("style"):
                    style = item.get("style", "").lower()
                    if "green" in style or "correct" in style:
                        correct_index = i
            
            # Build MCQ data
            mcq_data = {
                "question_text": question_text,
                "option_a": options[0],
                "option_b": options[1], 
                "option_c": options[2],
                "option_d": options[3],
                "option_e": options[4] if len(options) > 4 else None,
                "correct_answer": None,
                "explanation": None
            }
            
            # Set correct answer
            if correct_index is not None:
                answer_key = f"option_{chr(ord('a') + correct_index)}"
                try:
                    mcq_data["correct_answer"] = AnswerOption(answer_key)
                except ValueError:
                    logger.warning(f"⚠️ Invalid answer option: {answer_key}")
                    return None
            
            # Extract explanation
            explanation_element = block.find("div", class_=re.compile(r"explanation|answer|solution"))
            if explanation_element:
                explanation_text = explanation_element.get_text(" ", strip=True)
                # Convert to markdown format
                mcq_data["explanation"] = f"**Explanation:**\n\n{explanation_text}"
            
            return mcq_data
            
        except Exception as e:
            logger.warning(f"⚠️ Error extracting MCQ: {e}")
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
        
        # Create new MCQ
        mcq = MCQ(
            question_text=mcq_data["question_text"],
            option_a=mcq_data["option_a"],
            option_b=mcq_data["option_b"],
            option_c=mcq_data["option_c"],
            option_d=mcq_data["option_d"],
            option_e=mcq_data["option_e"],
            correct_answer=mcq_data["correct_answer"],
            explanation=mcq_data.get("explanation"),
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
            
            return mcq
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"❌ Failed to save MCQ: {e}")
            return None
    
    def crawl_pages(self, base_url: str) -> List[str]:
        """Crawl paginated content"""
        pages = []
        current_url = base_url
        
        while current_url:
            pages.append(current_url)
            
            try:
                response = self.requests_session.get(current_url, timeout=30)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Look for next page link
                next_link = soup.select_one('ul.pagination a.page-link[rel=next]') or \
                           soup.select_one('a[rel=next]') or \
                           soup.select_one('.pagination .next a') or \
                           soup.select_one('.page-numbers.next')
                
                if next_link and next_link.get('href'):
                    current_url = urljoin(base_url, next_link['href'])
                else:
                    current_url = None
                    
            except Exception as e:
                logger.warning(f"⚠️ Error crawling page {current_url}: {e}")
                break
        
        return pages
    
    def collect_from_url(self, url: str) -> Dict[str, Any]:
        """Main method to collect MCQs from a URL"""
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
            # Step 2: Fetch the page
            print("🌐 GETTING PAGE...")
            response = self.requests_session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            page_title = soup.find('title').get_text(strip=True) if soup.find('title') else "Unknown Title"
            
            # Step 3: Create paper record
            print("📄 CREATING PAPER...")
            paper = self.create_paper_record(
                url=url,
                title=page_title,
                website_id=validation_result["website_id"],
                validation_result=validation_result
            )
            
            # Step 4: Create/get category
            print("🏷️ SETTING CATEGORY...")
            category_name, category_slug, tags = self.category_manager.extract_category_from_url(url, page_title)
            category = self.category_manager.get_or_create_category(category_name, category_slug, tags)
            
            # Step 5: Crawl all pages
            print("🔎 FINDING PAGES...")
            pages = self.crawl_pages(url)
            print(f"📄 FOUND {len(pages)} PAGES")
            logger.info(f"📄 Found {len(pages)} pages to process")
            
            total_mcqs = 0
            total_new_mcqs = 0
            
            # Step 6: Process each page
            for page_num, page_url in enumerate(pages, 1):
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
                    for mcq_data in mcqs:
                        mcq = self.save_mcq(mcq_data, paper, category)
                        if mcq:
                            total_mcqs += 1
                            saved_count += 1
                            # Check if it's a new MCQ (not just a relationship)
                            if mcq.created_at.replace(microsecond=0) >= datetime.now().replace(microsecond=0, second=0):
                                total_new_mcqs += 1
                    
                    print(f"   💾 SAVED {saved_count} MCQs")
                    
                except Exception as e:
                    print(f"   ❌ ERROR ON PAGE {page_num}")
                    logger.error(f"❌ Error processing page {page_num}: {e}")
                    continue
            
            # Final commit
            print("💾 SAVING TO DATABASE...")
            try:
                self.session.commit()
            except Exception as e:
                self.session.rollback()
                logger.error(f"❌ Final commit failed: {e}")
            
            result = {
                "success": True,
                "url": url,
                "paper_id": paper.id,
                "paper_title": paper.title,
                "category_name": category.name,
                "category_slug": category.slug,
                "pages_processed": len(pages),
                "total_mcqs": total_mcqs,
                "new_mcqs": total_new_mcqs,
                "validation_source": validation_result["source"]
            }
            
            # Step 7: Update website record tracking
            print("🗂️ UPDATING WEBSITE RECORD...")
            website_updated = self.website_tracker.update_scraped_status(
                url, paper, category, total_mcqs, len(pages)
            )
            result["website_updated"] = website_updated
            
            print(f"✅ COMPLETED! {total_mcqs} MCQs ({total_new_mcqs} new)")
            logger.info(f"✅ Collection completed: {total_mcqs} MCQs ({total_new_mcqs} new)")
            return result
            
        except Exception as e:
            logger.error(f"❌ Collection failed: {e}")
            return {"success": False, "error": str(e), "url": url}


def main():
    """CLI interface for the paper MCQ collector"""
    parser = argparse.ArgumentParser(description="Collect MCQs from paper URLs")
    parser.add_argument("url", help="URL to scrape MCQs from")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    
    # Get database session
    session_gen = get_session()
    session = next(session_gen)
    
    try:
        collector = PaperMCQCollector(session)
        result = collector.collect_from_url(args.url)
        
        if result["success"]:
            print(f"\n🎉 SUCCESS!")
            print(f"📄 Paper: {result['paper_title']}")
            print(f"📂 Category: {result['category_name']}")
            print(f"📊 MCQs: {result['total_mcqs']} total ({result['new_mcqs']} new)")
            print(f"📄 Pages: {result['pages_processed']}")
            print(f"🔗 Source: {result['validation_source']} table")
            website_status = "✅ Updated" if result.get('website_updated') else "ℹ️ No match found"
            print(f"🗂️ Website Record: {website_status}")
        else:
            print(f"\n❌ FAILED: {result.get('error', 'Unknown error')}")
            sys.exit(1)
            
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

