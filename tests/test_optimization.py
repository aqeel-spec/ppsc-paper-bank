#!/usr/bin/env python3
"""
Test script to demonstrate the optimization in urls_collector.py
This shows that we're only making one HTTP request instead of multiple requests.
"""

import time
from unittest.mock import patch
from app.services.scrapper.urls_collector import UrlsCollector

def test_single_request_optimization():
    """Test that the optimized collector makes only one HTTP request."""
    
    url = 'https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf'
    
    # Counter to track HTTP requests
    request_count = 0
    original_get = None
    
    def mock_get(*args, **kwargs):
        nonlocal request_count, original_get
        request_count += 1
        print(f"HTTP Request #{request_count}: {args[0] if args else 'Unknown URL'}")
        return original_get(*args, **kwargs)
    
    # Patch the requests.Session.get method to count requests
    with patch('requests.Session.get') as mock_session_get:
        # Store the original method for actual execution
        import requests
        original_get = requests.Session().get
        mock_session_get.side_effect = mock_get
        
        print("="*60)
        print("TESTING OPTIMIZED URLs COLLECTOR")
        print("="*60)
        print(f"Target URL: {url}")
        print(f"Expected: 1 HTTP request (optimized version)")
        print("-"*60)
        
        start_time = time.time()
        
        # Create and run the collector
        collector = UrlsCollector(url=url)
        result = collector.run()
        
        end_time = time.time()
        
        print("-"*60)
        print(f"RESULTS:")
        print(f"Total HTTP Requests Made: {request_count}")
        print(f"Execution Time: {end_time - start_time:.2f} seconds")
        print(f"Success: {result['success']}")
        
        if result['success']:
            data = result['data']
            availability = data['data_availability']
            
            print(f"\nDATA AVAILABILITY:")
            print(f"  Has Top Data: {availability['has_top_data']}")
            print(f"  Has Sidebar Data: {availability['has_sidebar_data']}")
            
            top_data = data['top_data']
            side_data = data['side_data']
            
            print(f"\nEXTRACTED DATA:")
            print(f"  Top URLs: {top_data.get('total_urls', 0)} URLs")
            print(f"  Sidebar URLs: {side_data.get('total_urls', 0)} URLs in {side_data.get('total_sections', 0)} sections")
            print(f"  Total URLs: {top_data.get('total_urls', 0) + side_data.get('total_urls', 0)}")
        
        print("="*60)
        
        # Verify optimization
        if request_count == 1:
            print("✅ OPTIMIZATION SUCCESS: Only 1 HTTP request made!")
        else:
            print(f"❌ OPTIMIZATION FAILED: {request_count} HTTP requests made (expected 1)")
        
        return request_count == 1

if __name__ == "__main__":
    success = test_single_request_optimization()
    exit(0 if success else 1)
