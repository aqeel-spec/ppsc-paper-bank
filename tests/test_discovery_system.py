#!/usr/bin/env python3
"""
Test the website discovery and MCQ collection system
"""

import sys
sys.path.insert(0, '.')

from app.services.website_discovery_system import WebsiteDiscoverySystem
from app.database import get_session
from sqlmodel import text

def test_discovery_system():
    """Test the discovery system with a known website"""
    print("🧪 TESTING WEBSITE DISCOVERY SYSTEM\n")
    
    # Test with testpointpk.com
    test_url = "https://testpointpk.com"
    
    print(f"🔍 Testing with: {test_url}")
    
    discovery = WebsiteDiscoverySystem()
    
    # Test Case 1: Website discovery
    print("\n📋 Case 1: Website Analysis and URL Collection")
    website_data = discovery.analyze_website(test_url)
    
    if 'error' in website_data:
        print(f"❌ Error: {website_data['error']}")
        return False
    
    print(f"✅ Website analyzed successfully!")
    print(f"   📊 Total URLs: {website_data['total_urls']}")
    print(f"   📄 Top URLs: {len(website_data['top_urls'])}")
    print(f"   📂 Side URLs: {len(website_data['side_urls'])}")
    
    # Show sample URLs
    print(f"\n📋 Sample Top URLs (first 5):")
    for i, url_data in enumerate(website_data['top_urls'][:5], 1):
        print(f"   {i}. {url_data['title'][:60]}...")
        print(f"      🔗 {url_data['url'][:80]}...")
    
    print(f"\n📋 Sample Side URLs (first 5):")
    for i, url_data in enumerate(website_data['side_urls'][:5], 1):
        print(f"   {i}. {url_data['section_title'][:60]}...")
        print(f"      🔗 {url_data['url'][:80]}...")
    
    return True

def test_database_status():
    """Check current database status"""
    print("\n📊 DATABASE STATUS CHECK")
    
    session = next(get_session())
    
    # Check websites
    website_count = session.exec(text("SELECT COUNT(*) FROM websites")).first()[0]
    print(f"🌐 Websites in database: {website_count}")
    
    # Check URLs
    top_count = session.exec(text("SELECT COUNT(*) FROM top_bar")).first()[0]
    side_count = session.exec(text("SELECT COUNT(*) FROM side_bar")).first()[0]
    print(f"📄 Top navigation URLs: {top_count}")
    print(f"📂 Side navigation URLs: {side_count}")
    print(f"📋 Total URLs: {top_count + side_count}")
    
    # Check MCQs
    mcq_count = session.exec(text("SELECT COUNT(*) FROM mcqs_bank")).first()[0]
    print(f"❓ MCQs in database: {mcq_count}")
    
    # Check papers
    paper_count = session.exec(text("SELECT COUNT(*) FROM paper")).first()[0]
    print(f"📃 Papers in database: {paper_count}")

def show_usage_examples():
    """Show usage examples"""
    print("\n🚀 USAGE EXAMPLES")
    
    print("\n1. 🔍 DISCOVER NEW WEBSITE:")
    print("   python -m app.services.website_discovery_system https://pakmcqs.com")
    print("   python -m app.services.website_discovery_system https://mcqsworld.com")
    
    print("\n2. 📋 INTERACTIVE SCRAPING:")
    print("   python show_urls.py")
    print("   # Then select option 2 for interactive scraping")
    
    print("\n3. ⚡ QUICK SCRAPE:")
    print("   python show_urls.py")
    print("   # Then select option 3 for quick scrape")
    
    print("\n4. 🎯 DIRECT MCQ COLLECTION:")
    print('   python -m app.services.scrapper.paper_mcqs_collector_v1 "URL_HERE"')

if __name__ == "__main__":
    print("🎯 WEBSITE DISCOVERY & MCQ COLLECTION SYSTEM TEST")
    print("=" * 60)
    
    # Test database status first
    test_database_status()
    
    # Test discovery system
    success = test_discovery_system()
    
    if success:
        print("\n✅ SYSTEM TEST PASSED!")
    else:
        print("\n❌ SYSTEM TEST FAILED!")
    
    # Show usage examples
    show_usage_examples()
    
    print("\n🎉 Ready to use the system!")
