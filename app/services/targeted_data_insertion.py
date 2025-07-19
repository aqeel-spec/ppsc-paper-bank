from typing import Dict, List, Any, Optional
from datetime import datetime
import time
from urllib.parse import urljoin, urlparse
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_engine
from app.models.websites import Websites, WebsitesRead
from app.models.category import Category
from app.models.mcqs_bank import MCQ, MCQCreate
from app.services.scrapper.top_urls import WebsiteTopService
from app.services.website_data_service import WebsiteDataService


class TargetedDataInsertionService:
    """
    Service for inserting data from specific known working URLs.
    Uses the predefined URLs that we know work for each website.
    """
    
    def __init__(self):
        self.url_service = WebsiteTopService()
        self.website_service = WebsiteDataService()
    
    # Define working URLs for each website
    WORKING_URLS = {
        'PakMcqs': [
            {
                'url': 'https://pakmcqs.com/category/english-mcqs',
                'category': 'English MCQs',
                'description': 'English language multiple choice questions'
            },
            {
                'url': 'https://pakmcqs.com/category/pak-study-mcqs',
                'category': 'Pakistan Studies',
                'description': 'Pakistan Studies multiple choice questions'
            },
            {
                'url': 'https://pakmcqs.com/category/islamiat-mcqs',
                'category': 'Islamic Studies',
                'description': 'Islamic Studies multiple choice questions'
            },
            {
                'url': 'https://pakmcqs.com/category/general-knowledge-mcqs',
                'category': 'General Knowledge',
                'description': 'General Knowledge multiple choice questions'
            },
            {
                'url': 'https://pakmcqs.com/category/current-affairs-mcqs',
                'category': 'Current Affairs',
                'description': 'Current Affairs multiple choice questions'
            }
        ],
        'TestPoint': [
            {
                'url': 'https://testpoint.pk/papers/ppsc',
                'category': 'PPSC Papers',
                'description': 'Punjab Public Service Commission papers'
            },
            {
                'url': 'https://testpoint.pk/papers/fpsc',
                'category': 'FPSC Papers',
                'description': 'Federal Public Service Commission papers'
            },
            {
                'url': 'https://testpoint.pk/papers/nts',
                'category': 'NTS Papers',
                'description': 'National Testing Service papers'
            }
        ]
    }
    
    def process_specific_category_url(self, website_name: str, category_info: Dict[str, str], max_urls: int = 20) -> Dict[str, Any]:
        """
        Process a specific category URL and collect all its data.
        
        Args:
            website_name: Name of the website (PakMcqs, TestPoint, etc.)
            category_info: Dictionary with url, category, description
            max_urls: Maximum URLs to process from this category
            
        Returns:
            Dictionary with processing results
        """
        try:
            print(f"\n📂 Processing Category: {category_info['category']}")
            print(f"   URL: {category_info['url']}")
            
            # Step 1: Collect URLs from the category page
            collection_result = self.url_service.extract_urls_and_title(category_info['url'])
            
            if not collection_result['success']:
                return {
                    'success': False,
                    'error': f"Failed to collect URLs: {collection_result.get('error')}",
                    'category': category_info['category'],
                    'url': category_info['url']
                }
            
            collected_urls = collection_result['urls'][:max_urls]
            print(f"   ✅ Collected {len(collected_urls)} URLs from category")
            
            # Step 2: Get or create website record
            parsed_url = urlparse(category_info['url'])
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            website_record = self.website_service.get_or_create_website(
                website_name=website_name,
                base_url=base_url,
                website_type=website_name
            )
            
            # Step 3: Create or get category
            category_record = None
            with Session(get_engine()) as session:
                # Check if category exists
                statement = select(Category).where(Category.name == category_info['category'])
                existing_category = session.exec(statement).first()
                
                if not existing_category:
                    category_record = Category.create_with_auto_slug(category_info['category'], session)
                    print(f"   ✅ Created new category: {category_record.name} (slug: {category_record.slug})")
                else:
                    category_record = existing_category
                    print(f"   ♻️  Using existing category: {category_record.name}")
            
            # Step 4: Process individual URLs and extract content
            processed_content = []
            content_errors = []
            
            for i, url_item in enumerate(collected_urls, 1):
                content_url = url_item.get('url', '')
                content_title = url_item.get('title', f'Content {i}')
                
                print(f"   Processing {i}/{len(collected_urls)}: {content_title[:50]}...")
                
                try:
                    # For now, we'll store basic information
                    # In future iterations, you can add detailed content extraction here
                    content_data = {
                        'url': content_url,
                        'title': content_title,
                        'category_id': category_record.id,
                        'website_id': website_record.id,
                        'category_name': category_info['category'],
                        'website_name': website_name,
                        'collected_at': datetime.now().isoformat(),
                        'content_type': 'MCQ_PAGE'  # You can determine this based on URL patterns
                    }
                    
                    processed_content.append(content_data)
                    
                    # Add small delay to be respectful to the server
                    time.sleep(0.3)
                    
                except Exception as e:
                    content_errors.append({
                        'url': content_url,
                        'title': content_title,
                        'error': str(e)
                    })
            
            print(f"   ✅ Successfully processed {len(processed_content)} content items")
            if content_errors:
                print(f"   ⚠️  {len(content_errors)} content items had errors")
            
            return {
                'success': True,
                'category': category_info['category'],
                'category_id': category_record.id,
                'website_id': website_record.id,
                'website_name': website_name,
                'total_urls_collected': len(collected_urls),
                'total_content_processed': len(processed_content),
                'processed_content': processed_content,
                'content_errors': content_errors,
                'collection_metadata': {
                    'page_title': collection_result.get('title'),
                    'website_type': collection_result.get('website_type'),
                    'collection_time': datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'category': category_info['category'],
                'url': category_info['url']
            }
    
    def process_website_categories(self, website_name: str, max_urls_per_category: int = 15) -> Dict[str, Any]:
        """
        Process all categories for a specific website.
        
        Args:
            website_name: Name of the website to process
            max_urls_per_category: Maximum URLs to process per category
            
        Returns:
            Dictionary with processing results
        """
        try:
            if website_name not in self.WORKING_URLS:
                return {
                    'success': False,
                    'error': f"No working URLs defined for website: {website_name}"
                }
            
            print(f"\n🌐 Processing Website: {website_name}")
            print(f"{'='*60}")
            
            categories = self.WORKING_URLS[website_name]
            website_results = {
                'website_name': website_name,
                'total_categories': len(categories),
                'processed_categories': [],
                'summary': {
                    'successful_categories': 0,
                    'failed_categories': 0,
                    'total_urls_collected': 0,
                    'total_content_processed': 0
                }
            }
            
            for i, category_info in enumerate(categories, 1):
                print(f"\n🔄 Processing Category {i}/{len(categories)}")
                
                category_result = self.process_specific_category_url(
                    website_name, 
                    category_info, 
                    max_urls_per_category
                )
                
                if category_result['success']:
                    website_results['summary']['successful_categories'] += 1
                    website_results['summary']['total_urls_collected'] += category_result['total_urls_collected']
                    website_results['summary']['total_content_processed'] += category_result['total_content_processed']
                else:
                    website_results['summary']['failed_categories'] += 1
                
                website_results['processed_categories'].append(category_result)
                
                # Add delay between categories
                if i < len(categories):
                    print(f"   ⏳ Waiting before next category...")
                    time.sleep(1)
            
            print(f"\n✅ Completed processing {website_name}")
            print(f"   Successful categories: {website_results['summary']['successful_categories']}")
            print(f"   Total URLs collected: {website_results['summary']['total_urls_collected']}")
            print(f"   Total content processed: {website_results['summary']['total_content_processed']}")
            
            return {
                'success': True,
                'results': website_results
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'website_name': website_name
            }
    
    def process_all_websites(self, max_urls_per_category: int = 10) -> Dict[str, Any]:
        """
        Process all defined websites systematically.
        
        Args:
            max_urls_per_category: Maximum URLs to process per category
            
        Returns:
            Dictionary with complete processing results
        """
        try:
            print("🚀 Starting Targeted Data Insertion for All Websites")
            print(f"{'='*70}")
            
            website_names = list(self.WORKING_URLS.keys())
            overall_results = {
                'total_websites': len(website_names),
                'websites_processed': [],
                'overall_summary': {
                    'successful_websites': 0,
                    'failed_websites': 0,
                    'total_categories_processed': 0,
                    'total_urls_collected': 0,
                    'total_content_processed': 0
                }
            }
            
            for i, website_name in enumerate(website_names, 1):
                print(f"\n🏠 Processing Website {i}/{len(website_names)}: {website_name}")
                
                website_result = self.process_website_categories(website_name, max_urls_per_category)
                
                if website_result['success']:
                    overall_results['overall_summary']['successful_websites'] += 1
                    overall_results['overall_summary']['total_categories_processed'] += website_result['results']['total_categories']
                    overall_results['overall_summary']['total_urls_collected'] += website_result['results']['summary']['total_urls_collected']
                    overall_results['overall_summary']['total_content_processed'] += website_result['results']['summary']['total_content_processed']
                else:
                    overall_results['overall_summary']['failed_websites'] += 1
                
                overall_results['websites_processed'].append(website_result)
                
                # Add delay between websites
                if i < len(website_names):
                    print(f"\n⏸️  Waiting before next website...")
                    time.sleep(2)
            
            # Final summary
            print(f"\n🎉 FINAL PROCESSING SUMMARY")
            print(f"{'='*70}")
            print(f"🌐 Total websites: {overall_results['total_websites']}")
            print(f"✅ Successful: {overall_results['overall_summary']['successful_websites']}")
            print(f"❌ Failed: {overall_results['overall_summary']['failed_websites']}")
            print(f"📂 Total categories: {overall_results['overall_summary']['total_categories_processed']}")
            print(f"🔗 Total URLs collected: {overall_results['overall_summary']['total_urls_collected']}")
            print(f"📄 Total content processed: {overall_results['overall_summary']['total_content_processed']}")
            
            return {
                'success': True,
                'results': overall_results
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_detailed_report(self, results: Dict[str, Any]) -> str:
        """Create a detailed report of the processing results."""
        if not results['success']:
            return f"❌ Processing failed: {results.get('error')}"
        
        report_lines = [
            "📊 TARGETED DATA INSERTION REPORT",
            "=" * 60,
            "",
            f"🌐 Total Websites: {results['results']['total_websites']}",
            f"✅ Successful: {results['results']['overall_summary']['successful_websites']}",
            f"❌ Failed: {results['results']['overall_summary']['failed_websites']}",
            f"📂 Total Categories: {results['results']['overall_summary']['total_categories_processed']}",
            f"🔗 Total URLs Collected: {results['results']['overall_summary']['total_urls_collected']}",
            f"📄 Total Content Processed: {results['results']['overall_summary']['total_content_processed']}",
            "",
            "DETAILED WEBSITE BREAKDOWN:",
            "-" * 40
        ]
        
        for website_data in results['results']['websites_processed']:
            if website_data['success']:
                website_results = website_data['results']
                report_lines.extend([
                    f"",
                    f"🌐 {website_results['website_name']}",
                    f"   Total Categories: {website_results['total_categories']}",
                    f"   Successful: {website_results['summary']['successful_categories']}",
                    f"   URLs Collected: {website_results['summary']['total_urls_collected']}",
                    f"   Content Processed: {website_results['summary']['total_content_processed']}"
                ])
                
                for category_data in website_results['processed_categories']:
                    if category_data['success']:
                        report_lines.append(
                            f"   📂 {category_data['category']}: "
                            f"{category_data['total_content_processed']} items"
                        )
                    else:
                        report_lines.append(
                            f"   ❌ {category_data['category']}: {category_data.get('error', 'Unknown error')}"
                        )
            else:
                report_lines.append(
                    f"❌ {website_data.get('website_name', 'Unknown')}: {website_data.get('error')}"
                )
        
        return "\n".join(report_lines)


# Convenience functions
def run_targeted_data_insertion(max_urls_per_category: int = 10):
    """Run targeted data insertion for all websites."""
    service = TargetedDataInsertionService()
    results = service.process_all_websites(max_urls_per_category)
    report = service.create_detailed_report(results)
    print(f"\n{report}")
    return results

def quick_test_targeted_insertion(max_urls_per_category: int = 3):
    """Quick test with limited URLs per category."""
    service = TargetedDataInsertionService()
    results = service.process_all_websites(max_urls_per_category)
    report = service.create_detailed_report(results)
    print(f"\n{report}")
    return results

if __name__ == "__main__":
    print("🧪 Running targeted data insertion test...")
    quick_test_targeted_insertion(max_urls_per_category=5)
