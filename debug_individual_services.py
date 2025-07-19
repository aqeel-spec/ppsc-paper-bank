#!/usr/bin/env python3
"""
Simple test to check what's causing multiple HTTP requests
"""

import requests
from unittest.mock import patch
from bs4 import BeautifulSoup
from app.services.scrapper.top_urls import WebsiteTopService
from app.services.scrapper.side_urls import WebsiteSideService

def test_individual_services():
    """Test each service individually to find the issue."""
    
    url = 'https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf'
    
    # Counter to track HTTP requests
    request_count = 0
    original_get = None
    
    def mock_get(*args, **kwargs):
        nonlocal request_count, original_get
        request_count += 1
        print(f"HTTP Request #{request_count}: {args[0] if args else 'Unknown URL'}")
        return original_get(*args, **kwargs)
    
    # Test top service
    print("="*60)
    print("TESTING TOP SERVICE INDIVIDUALLY")
    print("="*60)
    
    with patch('requests.Session.get') as mock_session_get:
        import requests
        original_get = requests.Session().get
        mock_session_get.side_effect = mock_get
        request_count = 0
        
        top_service = WebsiteTopService(urls=[url])
        result = top_service.extract_urls(url)
        
        print(f"Top Service - HTTP Requests: {request_count}")
        print(f"Top Service - Success: {result.get('success', False)}")
        print(f"Top Service - URLs Found: {result.get('total_urls', 0)}")
    
    # Test side service
    print("\n" + "="*60)
    print("TESTING SIDE SERVICE INDIVIDUALLY")
    print("="*60)
    
    with patch('requests.Session.get') as mock_session_get:
        import requests
        original_get = requests.Session().get
        mock_session_get.side_effect = mock_get
        request_count = 0
        
        side_service = WebsiteSideService(urls=[url])
        result = side_service.extract_sidebar_urls(url)
        
        print(f"Side Service - HTTP Requests: {request_count}")
        print(f"Side Service - Success: {result.get('success', False)}")
        print(f"Side Service - URLs Found: {result.get('total_urls', 0)}")

if __name__ == "__main__":
    test_individual_services()
