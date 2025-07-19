#!/usr/bin/env python3

from app.services.website_data_service import WebsiteDataService

def test_duplicate_prevention():
    """Test that the service prevents duplicate website creation."""
    print("Testing Duplicate Prevention")
    print("=" * 50)
    
    service = WebsiteDataService()
    
    # Test multiple URLs from the same website (PakMcqs)
    print("1. Setting up PakMcqs first time...")
    result1 = service.collect_and_store_website_data(
        website_url="https://pakmcqs.com/category/english-mcqs",
        website_name="PakMcqs"
    )
    
    if result1['success']:
        print(f"✅ First setup - Website ID: {result1['website_id']}")
    
    print("\n2. Setting up PakMcqs second time (different category)...")
    result2 = service.collect_and_store_website_data(
        website_url="https://pakmcqs.com/category/pak-study-mcqs",
        website_name="PakMcqs"
    )
    
    if result2['success']:
        print(f"✅ Second setup - Website ID: {result2['website_id']}")
    
    print("\n3. Setting up PakMcqs third time (another category)...")
    result3 = service.collect_and_store_website_data(
        website_url="https://pakmcqs.com/category/islamiat-mcqs",
        website_name="PakMcqs"
    )
    
    if result3['success']:
        print(f"✅ Third setup - Website ID: {result3['website_id']}")
    
    # Check if all three operations reused the same website ID
    if result1['success'] and result2['success'] and result3['success']:
        website_ids = [result1['website_id'], result2['website_id'], result3['website_id']]
        unique_ids = set(website_ids)
        
        print(f"\n📊 Results:")
        print(f"   Website IDs: {website_ids}")
        print(f"   Unique IDs: {list(unique_ids)}")
        
        if len(unique_ids) == 1:
            print(f"✅ SUCCESS: All operations reused the same website ID ({list(unique_ids)[0]})")
            print("   No duplicate websites created!")
        else:
            print(f"❌ FAILURE: Multiple website IDs created: {list(unique_ids)}")
            print("   Duplicate prevention not working properly!")
    
    # Show all websites in database
    print(f"\n4. All websites in database:")
    websites = service.get_all_websites()
    for website in websites:
        print(f"   - ID: {website.id}, Name: {website.website_name}, URL: {website.base_url}")

if __name__ == "__main__":
    test_duplicate_prevention()
