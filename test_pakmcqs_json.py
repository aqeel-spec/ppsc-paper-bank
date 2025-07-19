#!/usr/bin/env python3
"""
Test PakMcqs with updated JSON structure
"""

from app.services.scrapper.urls_collector import UrlsCollector

def test_pakmcqs():
    url = 'https://pakmcqs.com/category/pakistan-current-affairs-mcqs'
    
    print("="*60)
    print("TESTING PAKMCQS WITH JSON STRUCTURE")
    print("="*60)
    
    collector = UrlsCollector(url=url)
    result = collector.run()

    if result['success']:
        data = result['data']
        db_result = data.get('database_result', {})
        merged_urls = data.get('merged_urls', [])
        
        print(f'Success: {db_result.get("success", False)}')
        print(f'Web Record ID: {db_result.get("web_id")}')
        print(f'Total URLs: {len(merged_urls)}')
        
        # Show sections breakdown
        sections = {}
        for url_obj in merged_urls:
            section = url_obj.get('section', 'unknown')
            sections[section] = sections.get(section, 0) + 1
        
        print(f'\nSections:')
        for section, count in sections.items():
            print(f'  - {section}: {count} URLs')
            
        # Show sample URL
        if merged_urls:
            print(f'\nSample URL structure:')
            sample = merged_urls[0]
            for key, value in sample.items():
                print(f'  {key}: {value}')
    else:
        print(f'Error: {result.get("error")}')

if __name__ == "__main__":
    test_pakmcqs()
