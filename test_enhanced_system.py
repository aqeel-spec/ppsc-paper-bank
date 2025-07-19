#!/usr/bin/env python3
"""
Test script for the enhanced auto-detection system.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_enhanced_system():
    try:
        print("🚀 Testing Enhanced Auto-Detection System")
        print("=" * 50)
        
        # Import the enhanced auto-detection system
        from app.services.website_auto_detection import WebsiteAutoDetection
        print("✅ Import successful")
        
        # Create detector instance
        detector = WebsiteAutoDetection()
        print("✅ Detector instance created")
        
        # Test URL from the user's HTML analysis
        test_url = 'https://www.allpaperspk.com/past-papers/ppsc-past-papers/'
        print(f"\n🎯 Testing URL: {test_url}")
        
        # Test basic discovery
        print("\n1. 📊 Basic URL Discovery:")
        basic_result = detector.discover_processable_urls(test_url)
        print(f"   URLs found: {basic_result.get('total_discovered', 0)}")
        
        if basic_result.get('success') and basic_result.get('discovered_urls'):
            print("   Sample URLs:")
            for i, url_info in enumerate(basic_result['discovered_urls'][:3]):
                print(f"   {i+1}. {url_info.get('title', 'No title')[:40]}...")
                print(f"      Confidence: {url_info.get('confidence', 0):.2f}")
        
        # Test enhanced discovery with pagination
        print("\n2. 🔄 Enhanced Discovery with Pagination:")
        paginated_result = detector.discover_with_pagination(test_url, max_pages=2)
        
        if paginated_result.get('success'):
            print(f"   ✅ Success!")
            print(f"   Total URLs found: {paginated_result.get('total_discovered', 0)}")
            print(f"   Pages processed: {paginated_result.get('pages_processed', 0)}")
            
            # Show comparison
            basic_count = basic_result.get('total_discovered', 0)
            enhanced_count = paginated_result.get('total_discovered', 0)
            improvement = enhanced_count - basic_count
            
            print(f"\n📈 Improvement Analysis:")
            print(f"   Basic discovery: {basic_count} URLs")
            print(f"   Enhanced discovery: {enhanced_count} URLs")
            print(f"   Improvement: +{improvement} URLs ({improvement/max(basic_count,1)*100:.1f}% increase)")
            
            # Show sample enhanced URLs
            urls = paginated_result.get('discovered_urls', [])
            if urls:
                print(f"\n📋 Sample Enhanced URLs (showing top 5):")
                for i, url_info in enumerate(urls[:5]):
                    print(f"   {i+1}. {url_info.get('title', 'No title')[:50]}...")
                    print(f"      URL: {url_info.get('url', '')[:60]}...")
                    print(f"      Confidence: {url_info.get('confidence', 0):.2f}")
                    print(f"      Type: {url_info.get('content_type', 'Unknown')}")
                    print()
        else:
            print(f"   ❌ Error: {paginated_result.get('error', 'Unknown error')}")
            
        print("\n🎉 Enhanced System Test Complete!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_enhanced_system()
