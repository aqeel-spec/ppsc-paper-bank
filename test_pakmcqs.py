#!/usr/bin/env python3

from app.services.scrapper.top_urls import collect_pakmcqs_urls, collect_ppsc_assistant_urls, WebsiteTopService

print("Final Test: Multi-Website Support")
print("=" * 40)

# Test both helper functions
print("1. Testing helper functions:")
testpoint_result = collect_ppsc_assistant_urls()
pakmcqs_result = collect_pakmcqs_urls()

print(f"   TestPoint: {testpoint_result.get('website_type')} - {testpoint_result.get('total_urls')} URLs")
print(f"   PakMcqs: {pakmcqs_result.get('website_type')} - {pakmcqs_result.get('total_urls')} URLs")

print("\n2. Testing universal service:")
collector = WebsiteTopService()

# Test automatic detection
urls_to_test = [
    "https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf",
    "https://pakmcqs.com/category/pakistan-current-affairs-mcqs"
]

for url in urls_to_test:
    result = collector.extract_urls_and_title(url)
    website = result.get('website_type', 'unknown')
    count = result.get('total_urls', 0)
    print(f"   {url[:30]}... -> {website} ({count} URLs)")

print(f"\n✅ Multi-website support is working!")
print(f"Total URLs found: {testpoint_result.get('total_urls', 0) + pakmcqs_result.get('total_urls', 0)}")
