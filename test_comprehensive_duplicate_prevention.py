#!/usr/bin/env python3

from app.services.website_data_service import WebsiteDataService

def test_comprehensive_duplicate_prevention():
    """Test comprehensive duplicate prevention and unique website creation."""
    print("Testing Comprehensive Duplicate Prevention")
    print("=" * 60)
    
    service = WebsiteDataService()
    
    test_cases = [
        {
            'name': 'PakMcqs',
            'url': 'https://pakmcqs.com/category/english-mcqs',
            'category': 'English MCQs'
        },
        {
            'name': 'PakMcqs',
            'url': 'https://pakmcqs.com/category/pak-study-mcqs',
            'category': 'Pakistan Studies'
        },
        {
            'name': 'PakMcqs',
            'url': 'https://pakmcqs.com/category/islamiat-mcqs',
            'category': 'Islamic Studies'
        },
        {
            'name': 'TestPoint',
            'url': 'https://testpoint.pk/papers/ppsc',
            'category': 'PPSC Papers'
        },
        {
            'name': 'TestPoint',
            'url': 'https://testpoint.pk/papers/fpsc',
            'category': 'FPSC Papers'
        }
    ]
    
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. Setting up {test_case['name']} - {test_case['category']}...")
        
        try:
            result = service.collect_and_store_website_data(
                website_url=test_case['url'],
                website_name=test_case['name']
            )
            
            if result['success']:
                print(f"✅ Website ID: {result['website_id']}")
                print(f"   URLs Collected: {result['total_urls_collected']}")
                print(f"   Website Type: {result['website_type']}")
                results.append(result)
            else:
                print(f"❌ Failed: {result.get('error')}")
                
        except Exception as e:
            print(f"❌ Exception: {str(e)}")
    
    # Analyze results
    print(f"\n📊 Analysis:")
    print(f"   Total operations: {len(test_cases)}")
    print(f"   Successful operations: {len(results)}")
    
    if results:
        website_ids = [r['website_id'] for r in results]
        unique_ids = set(website_ids)
        
        print(f"   Website IDs: {website_ids}")
        print(f"   Unique website IDs: {list(unique_ids)}")
        print(f"   Expected unique websites: 2 (PakMcqs, TestPoint)")
        
        if len(unique_ids) == 2:
            print(f"✅ SUCCESS: Correct number of unique websites created!")
        else:
            print(f"❌ ISSUE: Expected 2 unique websites, got {len(unique_ids)}")
    
    # Show final database state
    print(f"\n🗄️  Final Database State:")
    websites = service.get_all_websites()
    for website in websites:
        print(f"   - ID: {website.id}")
        print(f"     Name: {website.website_name}")
        print(f"     Base URL: {website.base_url}")
        print(f"     Type: {website.website_type}")
        print(f"     Active: {website.is_active}")
        print()

if __name__ == "__main__":
    test_comprehensive_duplicate_prevention()
