#!/usr/bin/env python3
"""
Test Website Tracking Functionality

This script tests the website tracking features added to the MCQ collectors.
"""

import sys
import logging
from datetime import datetime, timezone

from app.database import get_session
from app.services.scrapper.paper_mcqs_collector_v1 import WebsiteTracker, URLValidator
from app.models.website import Website
from app.models.paper import PaperModel
from app.models.category import Category

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_website_tracking():
    """Test the website tracking functionality"""
    
    # Get database session
    session_gen = get_session()
    session = next(session_gen)
    
    try:
        # Initialize tracker
        tracker = WebsiteTracker(session)
        
        print("🔍 Testing Website Tracking Functionality")
        print("=" * 50)
        
        # Test 1: Get a sample website record with paper_urls
        websites = session.query(Website).filter(Website.paper_urls.isnot(None)).limit(3).all()
        
        if not websites:
            print("❌ No website records with paper_urls found for testing")
            return
        
        print(f"\n📊 Found {len(websites)} website records with paper_urls:")
        
        for website in websites:
            print(f"\n🌐 Website ID: {website.web_id}")
            print(f"📄 Current Page URL: {website.current_page_url}")
            
            if website.paper_urls:
                print(f"📁 Paper URLs Count: {len(website.paper_urls)}")
                
                # Show first few URLs and their scraping status
                for i, url_obj in enumerate(website.paper_urls[:3]):
                    if isinstance(url_obj, dict):
                        url = url_obj.get('url', 'N/A')
                        title = url_obj.get('title', 'N/A')
                        is_scraped = url_obj.get('is_scraped', False)
                        source = url_obj.get('source', 'N/A')
                        
                        status_icon = "✅" if is_scraped else "⏳"
                        print(f"  {status_icon} [{i+1}] {url}")
                        print(f"      Title: {title}")
                        print(f"      Source: {source}")
                        print(f"      Scraped: {is_scraped}")
                        
                        # Test finding URL match
                        match_result = tracker.find_paper_url_match(url)
                        if match_result:
                            print(f"      🎯 Match found in website {match_result['website'].web_id} at index {match_result['url_index']}")
                        else:
                            print(f"      ❌ No match found (unexpected)")
                
                if len(website.paper_urls) > 3:
                    print(f"    ... and {len(website.paper_urls) - 3} more URLs")
        
        # Test 2: Test URL matching with a known URL
        if websites and websites[0].paper_urls:
            test_url = websites[0].paper_urls[0].get('url') if isinstance(websites[0].paper_urls[0], dict) else None
            
            if test_url:
                print(f"\n🧪 Testing URL matching with: {test_url}")
                match_result = tracker.find_paper_url_match(test_url)
                
                if match_result:
                    print(f"✅ Successfully found match:")
                    print(f"   Website ID: {match_result['website'].web_id}")
                    print(f"   URL Index: {match_result['url_index']}")
                    print(f"   URL Object: {match_result['url_object']}")
                else:
                    print(f"❌ Failed to find match for known URL")
        
        # Test 3: Test with non-existent URL
        print(f"\n🧪 Testing with non-existent URL")
        fake_url = "https://example.com/fake-test-url"
        match_result = tracker.find_paper_url_match(fake_url)
        
        if match_result:
            print(f"❌ Unexpected match found for fake URL")
        else:
            print(f"✅ Correctly returned None for non-existent URL")
        
        print(f"\n✅ Website tracking tests completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise
    finally:
        try:
            session_gen.close()
        except Exception:
            pass


def show_scraped_status_summary():
    """Show summary of scraped vs unscraped URLs"""
    
    session_gen = get_session()
    session = next(session_gen)
    
    try:
        print("\n📈 Scraping Status Summary")
        print("=" * 30)
        
        websites = session.query(Website).filter(Website.paper_urls.isnot(None)).all()
        
        total_websites = len(websites)
        total_urls = 0
        scraped_urls = 0
        unscraped_urls = 0
        
        for website in websites:
            if website.paper_urls:
                for url_obj in website.paper_urls:
                    if isinstance(url_obj, dict):
                        total_urls += 1
                        if url_obj.get('is_scraped', False):
                            scraped_urls += 1
                        else:
                            unscraped_urls += 1
        
        print(f"🌐 Total Websites: {total_websites}")
        print(f"🔗 Total URLs: {total_urls}")
        print(f"✅ Scraped URLs: {scraped_urls}")
        print(f"⏳ Unscraped URLs: {unscraped_urls}")
        
        if total_urls > 0:
            scraped_percentage = (scraped_urls / total_urls) * 100
            print(f"📊 Scraping Progress: {scraped_percentage:.1f}%")
        
    except Exception as e:
        logger.error(f"❌ Summary failed: {e}")
    finally:
        try:
            session_gen.close()
        except Exception:
            pass


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        show_scraped_status_summary()
    else:
        test_website_tracking()
