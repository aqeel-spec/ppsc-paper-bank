#!/usr/bin/env python3
"""
Website Data Management Runner Script

This script provides a simple way to test the website data service
and setup your database with website data.
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.services.website_data_service import WebsiteDataService, setup_all_predefined_websites

def display_menu():
    """Display the main menu options."""
    print("\n" + "="*60)
    print("🌐 Website Data Management Service")
    print("="*60)
    print("1. Setup a single website")
    print("2. Setup all predefined websites")
    print("3. View all websites in database")
    print("4. Create categories for existing website")
    print("5. Create top bar for existing website")
    print("6. Test URL collection only")
    print("7. Exit")
    print("="*60)

def setup_single_website():
    """Interactive setup for a single website."""
    print("\n📝 Single Website Setup")
    print("-" * 30)
    
    url = input("Enter website URL: ").strip()
    if not url:
        print("❌ URL is required!")
        return
    
    name = input("Enter website name (optional): ").strip()
    if not name:
        name = f"Website from {url}"
    
    create_categories = input("Create categories? (y/n): ").strip().lower() == 'y'
    create_top_bar = input("Create top bar? (y/n): ").strip().lower() == 'y'
    
    print(f"\n🚀 Setting up website: {name}")
    print(f"URL: {url}")
    
    service = WebsiteDataService()
    result = service.setup_complete_website_data(
        website_url=url,
        website_name=name,
        create_categories=create_categories,
        create_top_bar=create_top_bar
    )
    
    if result['success']:
        print(f"✅ Successfully setup website!")
        print(f"   Website ID: {result['website_id']}")
        print(f"   Website Name: {result['website_name']}")
        
        setup_results = result['setup_results']
        collection = setup_results['website_collection']
        print(f"   URLs Collected: {collection['total_urls_collected']}")
        print(f"   Website Type: {collection['website_type']}")
        
        if create_categories:
            categories = setup_results.get('categories_created', [])
            print(f"   Categories Created: {len(categories)}")
        
        if create_top_bar:
            top_bar = setup_results.get('top_bar_created')
            if top_bar and top_bar['success']:
                print(f"   Top Bar Created: ID {top_bar['top_bar_id']}")
    else:
        print(f"❌ Failed to setup website: {result.get('error')}")

def setup_all_predefined():
    """Setup all predefined websites."""
    print("\n🚀 Setting up all predefined websites...")
    print("This may take a while...")
    
    confirm = input("Are you sure? This will add multiple websites to your database (y/n): ").strip().lower()
    if confirm != 'y':
        print("Operation cancelled.")
        return
    
    result = setup_all_predefined_websites()
    
    print(f"\n📊 Results:")
    print(f"Total sites processed: {result['total_sites_processed']}")
    print(f"Successful setups: {result['successful_setups']}")
    print(f"Failed setups: {result['total_sites_processed'] - result['successful_setups']}")
    
    print("\n📋 Details:")
    for site_result in result['results']:
        site_name = site_result['site_name']
        success = site_result['result']['success']
        
        if success:
            website_id = site_result['result']['website_id']
            urls_count = site_result['result']['setup_results']['website_collection']['total_urls_collected']
            print(f"✅ {site_name} (ID: {website_id}, URLs: {urls_count})")
        else:
            error = site_result['result'].get('error', 'Unknown error')
            print(f"❌ {site_name}: {error}")

def view_all_websites():
    """View all websites in the database."""
    print("\n📋 All Websites in Database")
    print("-" * 40)
    
    service = WebsiteDataService()
    websites = service.get_all_websites()
    
    if not websites:
        print("No websites found in database.")
        return
    
    for i, website in enumerate(websites, 1):
        print(f"\n{i}. Website ID: {website.id}")
        print(f"   Current URL: {website.current_page_url}")
        print(f"   Total URLs: {len(website.websites_urls) if website.websites_urls else 0}")
        print(f"   Website Names: {len(website.website_names) if website.website_names else 0}")
        print(f"   Created: {website.created_at}")
        print(f"   Updated: {website.updated_at}")

def create_categories_for_website():
    """Create categories for an existing website."""
    print("\n📂 Create Categories for Website")
    print("-" * 35)
    
    view_all_websites()
    
    try:
        website_id = int(input("\nEnter Website ID: ").strip())
    except ValueError:
        print("❌ Invalid Website ID!")
        return
    
    service = WebsiteDataService()
    categories = service.create_categories_from_website_data(website_id)
    
    if categories:
        print(f"✅ Created {len(categories)} categories:")
        for cat in categories[:5]:  # Show first 5
            print(f"   - {cat['name']} (slug: {cat['slug']})")
        if len(categories) > 5:
            print(f"   ... and {len(categories) - 5} more")
    else:
        print("❌ No categories created. Check if website exists and has URLs.")

def create_top_bar_for_website():
    """Create top bar for an existing website."""
    print("\n📊 Create Top Bar for Website")
    print("-" * 32)
    
    view_all_websites()
    
    try:
        website_id = int(input("\nEnter Website ID: ").strip())
    except ValueError:
        print("❌ Invalid Website ID!")
        return
    
    title = input("Enter top bar title (optional): ").strip()
    if not title:
        title = f"Top Bar for Website {website_id}"
    
    service = WebsiteDataService()
    result = service.create_top_bar_from_website_data(website_id, title)
    
    if result['success']:
        print(f"✅ Top bar created successfully!")
        print(f"   Top Bar ID: {result['top_bar_id']}")
        print(f"   Title: {result['title']}")
        print(f"   Total Items: {result['total_items']}")
    else:
        print(f"❌ Failed to create top bar: {result.get('error')}")

def test_url_collection():
    """Test URL collection without database operations."""
    print("\n🔗 Test URL Collection Only")
    print("-" * 28)
    
    url = input("Enter URL to test: ").strip()
    if not url:
        print("❌ URL is required!")
        return
    
    print(f"\n🚀 Testing URL collection from: {url}")
    
    from app.services.scrapper.top_urls import WebsiteTopService
    
    service = WebsiteTopService()
    result = service.extract_urls_and_title(url)
    
    if result['success']:
        print(f"✅ Successfully collected URLs!")
        print(f"   Website Type: {result['website_type']}")
        print(f"   Page Title: {result['page_title']}")
        print(f"   Total URLs: {len(result['urls'])}")
        
        print(f"\n📋 First 5 URLs:")
        for i, url_item in enumerate(result['urls'][:5], 1):
            print(f"   {i}. {url_item['url']}")
            print(f"      Title: {url_item['title']}")
        
        if len(result['urls']) > 5:
            print(f"   ... and {len(result['urls']) - 5} more URLs")
    else:
        print(f"❌ Failed to collect URLs: {result.get('error')}")

def main():
    """Main application loop."""
    print("🌐 Welcome to Website Data Management Service!")
    
    while True:
        display_menu()
        
        try:
            choice = input("\nEnter your choice (1-7): ").strip()
            
            if choice == '1':
                setup_single_website()
            elif choice == '2':
                setup_all_predefined()
            elif choice == '3':
                view_all_websites()
            elif choice == '4':
                create_categories_for_website()
            elif choice == '5':
                create_top_bar_for_website()
            elif choice == '6':
                test_url_collection()
            elif choice == '7':
                print("\n👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice! Please select 1-7.")
                
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ An error occurred: {str(e)}")
            print("Please try again or check your input.")
        
        input("\nPress Enter to continue...")

if __name__ == "__main__":
    main()
