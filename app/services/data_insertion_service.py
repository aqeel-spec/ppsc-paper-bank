from typing import Dict, List, Any, Optional
from datetime import datetime
import time
from urllib.parse import urljoin, urlparse
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_engine
from app.models.websites import Websites, WebsitesRead
from app.models.category import Category
from app.models.top_bar import TopBar
from app.models.mcqs_bank import MCQ, MCQCreate
from app.models.paper import PaperModel, PaperCreate
from app.services.scrapper.top_urls import WebsiteTopService
from app.services.website_data_service import WebsiteDataService


class DataInsertionService:
    """
    Service for systematically inserting data from all websites.
    Goes through each website and collects all available data.
    """
    
    def __init__(self):
        self.url_service = WebsiteTopService()
        self.website_service = WebsiteDataService()
    
    def get_all_websites_for_processing(self) -> List[WebsitesRead]:
        """Get all websites that need data processing."""
        try:
            with Session(get_engine()) as session:
                statement = select(Websites).where(Websites.is_active == True)
                websites = session.exec(statement).all()
                return [WebsitesRead.from_orm(website) for website in websites]
        except SQLAlchemyError as e:
            raise Exception(f"Failed to get websites: {str(e)}")
    
    def get_categories_for_website(self, website_id: int) -> List[Category]:
        """Get all categories associated with a website."""
        try:
            with Session(get_engine()) as session:
                # For now, get all categories since we don't have direct website-category relationship
                # In future, you might want to add website_id to Category model
                statement = select(Category)
                categories = session.exec(statement).all()
                return list(categories)
        except SQLAlchemyError as e:
            raise Exception(f"Failed to get categories: {str(e)}")
    
    def collect_detailed_urls_from_category(self, category_url: str, website_type: str) -> Dict[str, Any]:
        """
        Collect detailed URLs from a specific category page.
        
        Args:
            category_url: URL of the category page
            website_type: Type of website (PakMcqs, TestPoint, etc.)
            
        Returns:
            Dictionary with collected URLs and metadata
        """
        try:
            print(f"Collecting detailed URLs from: {category_url}")
            
            # Use the existing URL service to collect URLs
            result = self.url_service.extract_urls_and_title(category_url)
            
            if not result['success']:
                return {
                    'success': False,
                    'error': result.get('error'),
                    'category_url': category_url
                }
            
            return {
                'success': True,
                'category_url': category_url,
                'website_type': website_type,
                'total_urls': len(result['urls']),
                'page_title': result.get('title', 'Unknown'),
                'collected_urls': result['urls']
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'category_url': category_url
            }
    
    def process_single_content_url(self, content_url: str, website_type: str, category_name: str) -> Dict[str, Any]:
        """
        Process a single content URL to extract detailed information.
        
        Args:
            content_url: URL of the content page
            website_type: Type of website
            category_name: Name of the category
            
        Returns:
            Dictionary with processed content information
        """
        try:
            print(f"Processing content URL: {content_url}")
            
            # For now, we'll collect basic information
            # In future, you can add specific content extraction logic here
            
            parsed_url = urlparse(content_url)
            url_parts = parsed_url.path.strip('/').split('/')
            content_title = url_parts[-1].replace('-', ' ').title() if url_parts else 'Unknown Content'
            
            return {
                'success': True,
                'url': content_url,
                'title': content_title,
                'category': category_name,
                'website_type': website_type,
                'processed_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': content_url
            }
    
    def insert_data_for_website(self, website: WebsitesRead, max_urls_per_category: int = 20) -> Dict[str, Any]:
        """
        Insert all data for a specific website.
        
        Args:
            website: Website record to process
            max_urls_per_category: Maximum URLs to process per category
            
        Returns:
            Dictionary with insertion results
        """
        try:
            print(f"\n🔄 Processing Website: {website.website_name} (ID: {website.id})")
            print(f"   Base URL: {website.base_url}")
            
            results = {
                'website_id': website.id,
                'website_name': website.website_name,
                'categories_processed': [],
                'total_urls_collected': 0,
                'total_content_processed': 0,
                'errors': []
            }
            
            # Get categories for this website
            categories = self.get_categories_for_website(website.id)
            print(f"   Found {len(categories)} categories to process")
            
            # Process each category
            for category in categories[:5]:  # Limit to first 5 categories for testing
                print(f"\n   📁 Processing Category: {category.name}")
                
                category_result = {
                    'category_id': category.id,
                    'category_name': category.name,
                    'urls_collected': [],
                    'content_processed': [],
                    'errors': []
                }
                
                # Construct category URL based on website type
                if website.website_type == 'PakMcqs':
                    category_url = f"{website.base_url}/category/{category.slug or category.name.lower().replace(' ', '-')}"
                elif website.website_type == 'TestPoint':
                    category_url = f"{website.base_url}/papers/{category.slug or category.name.lower().replace(' ', '-')}"
                else:
                    category_url = f"{website.base_url}/{category.slug or category.name.lower().replace(' ', '-')}"
                
                # Collect URLs from category
                url_collection = self.collect_detailed_urls_from_category(category_url, website.website_type)
                
                if url_collection['success']:
                    urls_to_process = url_collection['collected_urls'][:max_urls_per_category]
                    category_result['urls_collected'] = urls_to_process
                    results['total_urls_collected'] += len(urls_to_process)
                    
                    print(f"      Collected {len(urls_to_process)} URLs from category")
                    
                    # Process each URL
                    for i, url_item in enumerate(urls_to_process, 1):
                        content_url = url_item.get('url', '')
                        content_title = url_item.get('title', f'Content {i}')
                        
                        print(f"      Processing {i}/{len(urls_to_process)}: {content_title}")
                        
                        content_result = self.process_single_content_url(
                            content_url, 
                            website.website_type, 
                            category.name
                        )
                        
                        if content_result['success']:
                            category_result['content_processed'].append(content_result)
                            results['total_content_processed'] += 1
                        else:
                            category_result['errors'].append({
                                'url': content_url,
                                'error': content_result.get('error')
                            })
                        
                        # Add small delay to be respectful to the server
                        time.sleep(0.5)
                else:
                    category_result['errors'].append({
                        'category_url': category_url,
                        'error': url_collection.get('error')
                    })
                
                results['categories_processed'].append(category_result)
            
            print(f"✅ Completed processing {website.website_name}")
            print(f"   Total URLs collected: {results['total_urls_collected']}")
            print(f"   Total content processed: {results['total_content_processed']}")
            
            return {
                'success': True,
                'results': results
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'website_id': website.id
            }
    
    def insert_all_website_data(self, max_urls_per_category: int = 10) -> Dict[str, Any]:
        """
        Insert data from all websites systematically.
        
        Args:
            max_urls_per_category: Maximum URLs to process per category
            
        Returns:
            Dictionary with complete insertion results
        """
        try:
            print("🚀 Starting comprehensive data insertion for all websites")
            
            # Get all websites to process
            websites = self.get_all_websites_for_processing()
            print(f"Found {len(websites)} websites to process")
            
            if not websites:
                return {
                    'success': False,
                    'error': 'No active websites found in database'
                }
            
            overall_results = {
                'total_websites': len(websites),
                'websites_processed': [],
                'summary': {
                    'successful_websites': 0,
                    'failed_websites': 0,
                    'total_urls_collected': 0,
                    'total_content_processed': 0
                }
            }
            
            # Process each website
            for i, website in enumerate(websites, 1):
                print(f"\n{'='*60}")
                print(f"Processing Website {i}/{len(websites)}: {website.website_name}")
                print(f"{'='*60}")
                
                website_result = self.insert_data_for_website(website, max_urls_per_category)
                
                if website_result['success']:
                    overall_results['summary']['successful_websites'] += 1
                    overall_results['summary']['total_urls_collected'] += website_result['results']['total_urls_collected']
                    overall_results['summary']['total_content_processed'] += website_result['results']['total_content_processed']
                else:
                    overall_results['summary']['failed_websites'] += 1
                
                overall_results['websites_processed'].append(website_result)
                
                # Add delay between websites
                if i < len(websites):
                    print(f"\n⏳ Waiting before processing next website...")
                    time.sleep(2)
            
            print(f"\n{'='*60}")
            print("🎉 COMPLETE DATA INSERTION SUMMARY")
            print(f"{'='*60}")
            print(f"Total websites processed: {overall_results['total_websites']}")
            print(f"Successful: {overall_results['summary']['successful_websites']}")
            print(f"Failed: {overall_results['summary']['failed_websites']}")
            print(f"Total URLs collected: {overall_results['summary']['total_urls_collected']}")
            print(f"Total content processed: {overall_results['summary']['total_content_processed']}")
            
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
        """
        Create a detailed report of the data insertion process.
        
        Args:
            results: Results from insert_all_website_data
            
        Returns:
            Formatted report string
        """
        if not results['success']:
            return f"❌ Data insertion failed: {results.get('error')}"
        
        report_lines = [
            "📊 DETAILED DATA INSERTION REPORT",
            "=" * 50,
            "",
            f"🌐 Total Websites: {results['results']['total_websites']}",
            f"✅ Successful: {results['results']['summary']['successful_websites']}",
            f"❌ Failed: {results['results']['summary']['failed_websites']}",
            f"🔗 Total URLs Collected: {results['results']['summary']['total_urls_collected']}",
            f"📄 Total Content Processed: {results['results']['summary']['total_content_processed']}",
            "",
            "WEBSITE DETAILS:",
            "-" * 30
        ]
        
        for website_data in results['results']['websites_processed']:
            if website_data['success']:
                website_results = website_data['results']
                report_lines.extend([
                    f"",
                    f"🌐 {website_results['website_name']} (ID: {website_results['website_id']})",
                    f"   Categories: {len(website_results['categories_processed'])}",
                    f"   URLs Collected: {website_results['total_urls_collected']}",
                    f"   Content Processed: {website_results['total_content_processed']}"
                ])
                
                for category_data in website_results['categories_processed']:
                    report_lines.append(f"   📁 {category_data['category_name']}: {len(category_data['content_processed'])} items")
            else:
                report_lines.append(f"❌ Website ID {website_data.get('website_id', 'Unknown')}: {website_data.get('error')}")
        
        return "\n".join(report_lines)


# Convenience functions for easy execution
def start_comprehensive_data_insertion(max_urls_per_category: int = 10) -> Dict[str, Any]:
    """
    Start comprehensive data insertion for all websites.
    
    Args:
        max_urls_per_category: Maximum URLs to process per category
        
    Returns:
        Complete insertion results
    """
    service = DataInsertionService()
    return service.insert_all_website_data(max_urls_per_category)


def quick_data_insertion_test(max_urls_per_category: int = 3) -> str:
    """
    Quick test of data insertion with limited URLs per category.
    
    Args:
        max_urls_per_category: Maximum URLs to process per category (default: 3 for testing)
        
    Returns:
        Formatted report
    """
    service = DataInsertionService()
    results = service.insert_all_website_data(max_urls_per_category)
    return service.create_detailed_report(results)


if __name__ == "__main__":
    # Run a quick test
    print("🧪 Running quick data insertion test...")
    report = quick_data_insertion_test(max_urls_per_category=2)
    print(report)
