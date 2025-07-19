"""
Test script for enhanced auto-detection service
Demonstrates detecting custom websites and analyzing their configurations
"""

from app.services.enhanced_start_service import EnhancedStartService, detect_single_website
from app.services.website_auto_detection import WebsiteAutoDetectionService

def test_custom_website_detection():
    """Test detecting a custom website"""
    print("🧪 TESTING CUSTOM WEBSITE AUTO-DETECTION")
    print("=" * 60)
    
    # Example: Test with a custom URL
    test_url = "https://mcqsbank.com"  # Another MCQ website
    
    auto_detector = WebsiteAutoDetectionService()
    
    print(f"🔍 Analyzing: {test_url}")
    
    # Detect configuration
    result = auto_detector.create_dynamic_website_config(test_url)
    
    if result['success']:
        config = result['config']
        print(f"\n✅ Detection Successful!")
        print(f"   Website Name: {config['website_name']}")
        print(f"   Type: {config['website_type']}")
        print(f"   Confidence: {config['confidence_score']:.1%}")
        print(f"   Processable URLs: {len(config['processable_urls'])}")
        print(f"   High Value URLs: {len(config['high_value_urls'])}")
        print(f"\n🔧 Processing Flags:")
        for flag, value in config['processing_flags'].items():
            print(f"      {flag}: {value}")
        print(f"\n📊 Capabilities:")
        for capability in config['capabilities']:
            print(f"      • {capability}")
        print(f"\n⚙️  Recommended Settings:")
        for setting, value in config['recommended_settings'].items():
            print(f"      {setting}: {value}")
    else:
        print(f"❌ Detection failed: {result.get('error')}")

def test_bulk_website_detection():
    """Test detecting multiple websites at once"""
    print("\n🔍 TESTING BULK WEBSITE DETECTION")
    print("=" * 60)
    
    test_urls = [
        "https://pakmcqs.com",
        "https://testpoint.pk",
        "https://mcqsbank.com",  # Another test site
        "https://exampaper.pk"   # Another potential site
    ]
    
    service = EnhancedStartService()
    
    print(f"📝 Testing {len(test_urls)} URLs...")
    
    result = service.step1_auto_discover_and_insert_websites(test_urls)
    
    if result['success']:
        results_data = result['results']
        print(f"\n✅ Bulk Detection Complete!")
        print(f"   Successful: {results_data['successful_detections']}")
        print(f"   Failed: {results_data['failed_detections']}")
        print(f"   Created: {len(results_data['websites_created'])}")
        print(f"   Updated: {len(results_data['websites_updated'])}")
        
        if results_data['detection_results']:
            print(f"\n📊 Detection Results:")
            for i, config in enumerate(results_data['detection_results'], 1):
                print(f"   {i}. {config['website_name']} ({config['website_type']}) - {config['confidence_score']:.1%}")
    else:
        print(f"❌ Bulk detection failed: {result.get('error')}")

def test_intelligent_analysis():
    """Test the intelligent analysis capabilities"""
    print("\n🧠 TESTING INTELLIGENT ANALYSIS")
    print("=" * 60)
    
    auto_detector = WebsiteAutoDetectionService()
    
    # Test website type detection
    test_cases = [
        ("https://pakmcqs.com", "Should detect MCQ platform"),
        ("https://github.com", "Should detect unknown/other type"),
        ("https://stackoverflow.com", "Should detect Q&A platform"),
        ("https://wikipedia.org", "Should detect information/educational")
    ]
    
    for url, expected in test_cases:
        print(f"\n🔍 Testing: {url}")
        print(f"   Expected: {expected}")
        
        try:
            # Just test the website type detection
            detection_result = auto_detector.detect_website_type(url)
            if detection_result['success']:
                print(f"   ✅ Detected: {detection_result['analysis']['website_type']}")
                print(f"   📊 Confidence: {detection_result['analysis']['confidence']:.1%}")
                print(f"   🔧 Capabilities: {', '.join(detection_result['analysis']['capabilities'])}")
            else:
                print(f"   ❌ Failed: {detection_result.get('error')}")
        except Exception as e:
            print(f"   ❌ Exception: {str(e)}")

if __name__ == "__main__":
    print("🤖 ENHANCED AUTO-DETECTION TEST SUITE")
    print("=" * 70)
    
    # Test 1: Custom website detection
    test_custom_website_detection()
    
    # Test 2: Bulk detection
    test_bulk_website_detection()
    
    # Test 3: Intelligent analysis
    test_intelligent_analysis()
    
    print("\n🎉 ALL TESTS COMPLETED!")
    print("=" * 70)
