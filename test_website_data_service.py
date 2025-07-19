#!/usr/bin/env python3

from app.services.website_data_service import WebsiteDataService, setup_all_predefined_websites

def test_website_data_service():
    """Test the website data service with a single website."""
    print("Testing Website Data Service")
    print("=" * 50)
    
    service = WebsiteDataService()
    
    # Test with a single PakMcqs category
    print("1. Setting up PakMcqs English MCQs...")
    result = service.setup_complete_website_data(
        website_url="https://pakmcqs.com/category/english-mcqs",
        website_name="PakMcqs English MCQs",
        create_categories=True,
        create_top_bar=True
    )
    
    if result['success']:
        print(f"✅ Successfully setup website")
        print(f"   Website ID: {result['website_id']}")
        print(f"   Website Name: {result['website_name']}")
        
        setup_results = result['setup_results']
        
        # Website collection results
        collection = setup_results['website_collection']
        print(f"   URLs Collected: {collection['total_urls_collected']}")
        print(f"   Website Type: {collection['website_type']}")
        print(f"   Page Title: {collection['page_title']}")
        
        # Categories created
        categories = setup_results.get('categories_created', [])
        print(f"   Categories Created: {len(categories)}")
        for i, cat in enumerate(categories[:3]):  # Show first 3
            print(f"     {i+1}. {cat['name']} (slug: {cat['slug']})")
        
        # Top bar created
        top_bar = setup_results.get('top_bar_created')
        if top_bar and top_bar['success']:
            print(f"   Top Bar Created: ID {top_bar['top_bar_id']}")
            print(f"   Top Bar Title: {top_bar['title']}")
            print(f"   Top Bar Items: {top_bar['total_items']}")
        
    else:
        print(f"❌ Failed to setup website: {result.get('error')}")
    
    print("\n" + "=" * 50)
    
    # Test getting all websites
    print("2. Getting all websites...")
    websites = service.get_all_websites()
    print(f"   Total websites in database: {len(websites)}")
    
    for website in websites:
        print(f"   - ID: {website.id}")
        print(f"     Website Name: {website.website_name}")
        print(f"     Base URL: {website.base_url}")
        print(f"     Website Type: {website.website_type}")
        print(f"     Active: {website.is_active}")
        print(f"     Created: {website.created_at}")

def test_predefined_websites():
    """Test setting up all predefined websites."""
    print("\n" + "=" * 50)
    print("Testing Predefined Websites Setup")
    print("=" * 50)
    
    result = setup_all_predefined_websites()
    
    print(f"Total sites processed: {result['total_sites_processed']}")
    print(f"Successful setups: {result['successful_setups']}")
    
    print("\nDetails:")
    for site_result in result['results']:
        site_name = site_result['site_name']
        success = site_result['result']['success']
        
        if success:
            website_id = site_result['result']['website_id']
            print(f"✅ {site_name} (ID: {website_id})")
        else:
            error = site_result['result'].get('error', 'Unknown error')
            print(f"❌ {site_name}: {error}")

def test_individual_operations():
    """Test individual service operations."""
    print("\n" + "=" * 50)
    print("Testing Individual Operations")
    print("=" * 50)
    
    service = WebsiteDataService()
    
    # Test just collecting data without categories/top bar
    print("1. Testing data collection only...")
    result = service.collect_and_store_website_data(
        website_url="https://pakmcqs.com/category/pak-study-mcqs",
        website_name="PakMcqs Pak Study"
    )
    
    if result['success']:
        website_id = result['website_id']
        urls_data = result.get('collected_urls', [])
        print(f"✅ Data collected - Website ID: {website_id}")
        print(f"   Total URLs: {result['total_urls_collected']}")
        print(f"   Website Type: {result['website_type']}")
        
        # Test creating categories separately
        print("2. Creating categories from collected data...")
        categories = service.create_categories_from_website_data(website_id, urls_data)
        print(f"✅ Created {len(categories)} categories")
        
        # Test creating top bar separately
        print("3. Creating top bar from collected data...")
        top_bar_result = service.create_top_bar_from_website_data(
            website_id, 
            title="Pakistan Studies MCQs",
            urls_data=urls_data
        )
        
        if top_bar_result['success']:
            print(f"✅ Top bar created - ID: {top_bar_result['top_bar_id']}")
            print(f"   Title: {top_bar_result['title']}")
            print(f"   Items: {top_bar_result['total_items']}")
        else:
            print(f"❌ Top bar creation failed: {top_bar_result.get('error')}")
            
    else:
        print(f"❌ Data collection failed: {result.get('error')}")

if __name__ == "__main__":
    try:
        # Test individual website setup
        test_website_data_service()
        
        # Test individual operations
        test_individual_operations()
        
        # Test predefined websites (comment this out if you don't want to setup all)
        # test_predefined_websites()
        
        print("\n🎉 All tests completed!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
