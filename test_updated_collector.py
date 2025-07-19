#!/usr/bin/env python3
"""
Test the updated urls_collector with JSON objects in paper_urls
"""

from app.services.scrapper.urls_collector import UrlsCollector

def test_updated_collector():
    # Test with a single URL
    url = 'https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf'
    
    print("="*60)
    print("TESTING UPDATED URLS COLLECTOR (JSON OBJECTS)")
    print("="*60)
    print(f"URL: {url}")
    print()
    
    collector = UrlsCollector(url=url)
    result = collector.run()

    if result['success']:
        data = result['data']
        db_result = data.get('database_result', {})
        
        print(f'Database Success: {db_result.get("success", False)}')
        print(f'Web Record ID: {db_result.get("web_id")}')
        print(f'Total URLs Saved: {db_result.get("total_urls_saved", 0)}')
        
        # Show sample of merged URLs with complete metadata
        merged_urls = data.get('merged_urls', [])
        print(f'\nSample URLs with Complete Metadata (first 3):')
        for i, url_obj in enumerate(merged_urls[:3]):
            print(f'  {i+1}. Title: {url_obj.get("title", "Unknown")}')
            print(f'     URL: {url_obj.get("url", "")}')
            print(f'     Source: {url_obj.get("source", "")}')
            print(f'     Section: {url_obj.get("section", "")}')
            print(f'     Is Scraped: {url_obj.get("is_scraped", False)}')
            print()
            
        # Show breakdown by source
        top_count = len([u for u in merged_urls if u['source'] == 'top_bar'])
        sidebar_count = len([u for u in merged_urls if u['source'] == 'sidebar'])
        
        print(f"Source Breakdown:")
        print(f"  - Top Bar URLs: {top_count}")
        print(f"  - Sidebar URLs: {sidebar_count}")
        print(f"  - Total: {len(merged_urls)}")
    else:
        print(f'Error: {result.get("error")}')

if __name__ == "__main__":
    test_updated_collector()
