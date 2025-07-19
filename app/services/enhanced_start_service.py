from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_engine
from app.models.websites import Websites, WebsitesCreate
from app.models.website import Website, WebsiteCreate
from app.services.website_auto_detection import WebsiteAutoDetectionService
from app.services.scrapper.top_urls import WebsiteTopService


class EnhancedStartService:
    """
    Enhanced start service that uses auto-detection to dynamically configure websites
    instead of relying on hardcoded configurations.
    """
    
    def __init__(self):
        self.auto_detector = WebsiteAutoDetectionService()
        self.url_service = WebsiteTopService()
    
    # Base URLs to analyze (easily extensible)
    BASE_URLS_TO_ANALYZE = [
        "https://pakmcqs.com",
        "https://testpoint.pk",
        # Add more URLs here as needed
    ]
    
    def step1_auto_discover_and_insert_websites(self, custom_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Step 1: Auto-discover website configurations and insert unique websites.
        
        Args:
            custom_urls: Optional list of custom URLs to analyze instead of defaults
            
        Returns:
            Dictionary with discovery and insertion results
        """
        try:
            print("🤖 STEP 1: Auto-Discovering and Inserting Websites")
            print("=" * 60)
            
            urls_to_analyze = custom_urls or self.BASE_URLS_TO_ANALYZE
            
            results = {
                'total_urls_analyzed': len(urls_to_analyze),
                'successful_detections': 0,
                'failed_detections': 0,
                'websites_created': [],
                'websites_updated': [],
                'detection_results': [],
                'errors': []
            }
            
            for i, base_url in enumerate(urls_to_analyze, 1):
                print(f"\n🔍 Analyzing {i}/{len(urls_to_analyze)}: {base_url}")
                
                try:
                    # Auto-detect website configuration
                    detection_result = self.auto_detector.create_dynamic_website_config(base_url)
                    
                    if detection_result['success']:
                        config = detection_result['config']
                        results['successful_detections'] += 1
                        results['detection_results'].append(config)
                        
                        # Insert or update website in database
                        website_result = self._insert_or_update_website(config)
                        
                        if website_result['success']:
                            if website_result['action'] == 'created':
                                results['websites_created'].append(website_result['website'])
                            else:
                                results['websites_updated'].append(website_result['website'])
                            
                            print(f"   ✅ {website_result['action'].title()}: {config['website_name']}")
                        else:
                            results['errors'].append(f"Database error for {base_url}: {website_result['error']}")
                    else:
                        results['failed_detections'] += 1
                        error_msg = f"Detection failed for {base_url}: {detection_result.get('error')}"
                        results['errors'].append(error_msg)
                        print(f"   ❌ {error_msg}")
                
                except Exception as e:
                    error_msg = f"Exception analyzing {base_url}: {str(e)}"
                    results['errors'].append(error_msg)
                    results['failed_detections'] += 1
                    print(f"   ❌ {error_msg}")
            
            print(f"\n✅ Step 1 Complete!")
            print(f"   Successful detections: {results['successful_detections']}")
            print(f"   Failed detections: {results['failed_detections']}")
            print(f"   Websites created: {len(results['websites_created'])}")
            print(f"   Websites updated: {len(results['websites_updated'])}")
            
            return {
                'success': True,
                'step': 'STEP_1_AUTO_DISCOVERY',
                'results': results
            }
            
        except Exception as e:
            return {
                'success': False,
                'step': 'STEP_1_AUTO_DISCOVERY',
                'error': str(e)
            }
    
    def _insert_or_update_website(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update website based on auto-detected configuration."""
        try:
            with Session(get_engine()) as session:
                # Check if website already exists
                statement = select(Websites).where(
                    Websites.base_url == config['base_url']
                )
                existing_website = session.exec(statement).first()
                
                website_data = WebsitesCreate(
                    website_name=config['website_name'],
                    base_url=config['base_url'],
                    website_type=config['website_type'],
                    description=config['description'],
                    is_active=config['is_active']
                )
                
                if existing_website:
                    # Update existing website
                    for field, value in website_data.model_dump().items():
                        setattr(existing_website, field, value)
                    existing_website.updated_at = datetime.now()
                    
                    session.add(existing_website)
                    session.commit()
                    session.refresh(existing_website)
                    
                    return {
                        'success': True,
                        'action': 'updated',
                        'website': {
                            'id': existing_website.id,
                            'name': existing_website.website_name,
                            'url': existing_website.base_url,
                            'type': existing_website.website_type
                        }
                    }
                else:
                    # Create new website
                    db_website = Websites(**website_data.model_dump())
                    session.add(db_website)
                    session.commit()
                    session.refresh(db_website)
                    
                    return {
                        'success': True,
                        'action': 'created',
                        'website': {
                            'id': db_website.id,
                            'name': db_website.website_name,
                            'url': db_website.base_url,
                            'type': db_website.website_type
                        }
                    }
        
        except SQLAlchemyError as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def step2_create_dynamic_website_records(self) -> Dict[str, Any]:
        """
        Step 2: Create Website records with dynamically detected processing flags.
        
        Returns:
            Dictionary with creation results
        """
        try:
            print("\n🏭 STEP 2: Creating Dynamic Website Records")
            print("=" * 60)
            
            results = {
                'websites_found': 0,
                'records_created': [],
                'records_updated': [],
                'errors': []
            }
            
            with Session(get_engine()) as session:
                # Get all active websites
                statement = select(Websites).where(Websites.is_active == True)
                websites = session.exec(statement).all()
                
                results['websites_found'] = len(websites)
                print(f"🔍 Found {len(websites)} active websites to process")
                
                for website in websites:
                    try:
                        print(f"\n🔧 Processing: {website.website_name}")
                        
                        # Re-detect configuration for this website
                        detection_result = self.auto_detector.create_dynamic_website_config(website.base_url)
                        
                        if not detection_result['success']:
                            error_msg = f"Failed to detect config for {website.website_name}: {detection_result.get('error')}"
                            results['errors'].append(error_msg)
                            print(f"   ❌ {error_msg}")
                            continue
                        
                        config = detection_result['config']
                        
                        # Check if Website record already exists
                        website_statement = select(Website).where(
                            Website.website_name == website.id
                        )
                        existing_record = session.exec(website_statement).first()
                        
                        # Prepare URLs for processing
                        processable_urls = config.get('processable_urls', [])
                        high_value_urls = config.get('high_value_urls', [])
                        # Prioritize high-value URLs, but include others too
                        urls_to_process = high_value_urls + [url for url in processable_urls if url not in high_value_urls]
                        urls_to_process = urls_to_process[:20]  # Limit to 20 URLs
                        
                        if existing_record:
                            # Update existing record
                            existing_record.is_top_bar = config['processing_flags']['is_top_bar']
                            existing_record.is_paper_exit = config['processing_flags']['is_paper_exit']
                            existing_record.is_side_bar = config['processing_flags']['is_side_bar']
                            existing_record.paper_urls = urls_to_process
                            existing_record.pages_count = len(urls_to_process)
                            existing_record.total_pages = len(urls_to_process)
                            existing_record.updated_at = datetime.now()
                            
                            session.add(existing_record)
                            session.commit()
                            session.refresh(existing_record)
                            
                            print(f"   🔄 Updated Website record (ID: {existing_record.web_id})")
                            print(f"      URLs to process: {len(urls_to_process)}")
                            print(f"      TopBar: {config['processing_flags']['is_top_bar']}")
                            
                            results['records_updated'].append({
                                'web_id': existing_record.web_id,
                                'website_name': website.website_name,
                                'websites_id': website.id,
                                'processing_flags': config['processing_flags'],
                                'urls_count': len(urls_to_process),
                                'confidence_score': config['confidence_score'],
                                'status': 'UPDATED'
                            })
                        else:
                            # Create new Website record
                            website_record_data = WebsiteCreate(
                                is_top_bar=config['processing_flags']['is_top_bar'],
                                is_paper_exit=config['processing_flags']['is_paper_exit'],
                                is_side_bar=config['processing_flags']['is_side_bar'],
                                website_name=website.id,  # Reference to Websites table
                                paper_urls=urls_to_process,
                                pages_count=len(urls_to_process),
                                current_page=1,
                                total_pages=len(urls_to_process),
                                is_last_completed=False,
                                ul_config={
                                    'auto_detected': True,
                                    'confidence_score': config['confidence_score'],
                                    'website_type': config['website_type'],
                                    'capabilities': config['capabilities'],
                                    'recommended_settings': config['recommended_settings']
                                }
                            )
                            
                            db_website_record = Website(**website_record_data.model_dump())
                            session.add(db_website_record)
                            session.commit()
                            session.refresh(db_website_record)
                            
                            print(f"   ✅ Created Website record (ID: {db_website_record.web_id})")
                            print(f"      URLs to process: {len(urls_to_process)}")
                            print(f"      TopBar: {config['processing_flags']['is_top_bar']}")
                            print(f"      Confidence: {config['confidence_score']:.1%}")
                            
                            results['records_created'].append({
                                'web_id': db_website_record.web_id,
                                'website_name': website.website_name,
                                'websites_id': website.id,
                                'processing_flags': config['processing_flags'],
                                'urls_count': len(urls_to_process),
                                'confidence_score': config['confidence_score'],
                                'status': 'CREATED'
                            })
                    
                    except Exception as e:
                        error_msg = f"Failed to process {website.website_name}: {str(e)}"
                        results['errors'].append(error_msg)
                        print(f"   ❌ {error_msg}")
            
            print(f"\n✅ Step 2 Complete!")
            print(f"   Records created: {len(results['records_created'])}")
            print(f"   Records updated: {len(results['records_updated'])}")
            print(f"   Errors: {len(results['errors'])}")
            
            return {
                'success': True,
                'step': 'STEP_2_DYNAMIC_RECORDS',
                'results': results
            }
            
        except Exception as e:
            return {
                'success': False,
                'step': 'STEP_2_DYNAMIC_RECORDS',
                'error': str(e)
            }
    
    def step3_process_auto_detected_topbar_websites(self) -> Dict[str, Any]:
        """
        Step 3: Process websites with auto-detected TopBar capabilities.
        
        Returns:
            Dictionary with processing results
        """
        try:
            print("\n📊 STEP 3: Processing Auto-Detected TopBar Websites")
            print("=" * 60)
            
            results = {
                'topbar_websites_found': 0,
                'processed_websites': [],
                'skipped_websites': [],
                'errors': []
            }
            
            with Session(get_engine()) as session:
                # Get all Website records with is_top_bar = True
                statement = select(Website).where(Website.is_top_bar == True)
                topbar_websites = session.exec(statement).all()
                
                results['topbar_websites_found'] = len(topbar_websites)
                print(f"🔍 Found {len(topbar_websites)} websites with auto-detected TopBar")
                
                for website_record in topbar_websites:
                    try:
                        # Get the corresponding Websites record
                        websites_statement = select(Websites).where(
                            Websites.id == website_record.website_name
                        )
                        websites_info = session.exec(websites_statement).first()
                        
                        if not websites_info:
                            print(f"   ⚠️  Websites info not found for Website ID {website_record.web_id}")
                            results['skipped_websites'].append({
                                'web_id': website_record.web_id,
                                'reason': 'Websites info not found'
                            })
                            continue
                        
                        print(f"\n🚀 Processing Auto-Detected TopBar for: {websites_info.website_name}")
                        
                        # Get auto-detected configuration
                        auto_config = website_record.ul_config or {}
                        confidence_score = auto_config.get('confidence_score', 0.0)
                        website_type = auto_config.get('website_type', 'UNKNOWN')
                        
                        print(f"   📊 Website Type: {website_type}")
                        print(f"   📊 Confidence: {confidence_score:.1%}")
                        
                        # Process URLs using the start_urls service
                        if website_record.paper_urls:
                            url_processing_results = []
                            
                            for i, url in enumerate(website_record.paper_urls, 1):
                                print(f"   Processing URL {i}/{len(website_record.paper_urls)}: {url}")
                                
                                try:
                                    # Use the URL service to extract URLs and title
                                    extraction_result = self.url_service.extract_urls_and_title(url)
                                    
                                    if extraction_result['success']:
                                        url_processing_results.append({
                                            'url': url,
                                            'success': True,
                                            'urls_found': len(extraction_result['urls']),
                                            'title': extraction_result.get('title', 'Unknown'),
                                            'website_type': extraction_result.get('website_type', 'Unknown')
                                        })
                                        print(f"      ✅ Found {len(extraction_result['urls'])} URLs")
                                    else:
                                        url_processing_results.append({
                                            'url': url,
                                            'success': False,
                                            'error': extraction_result.get('error', 'Unknown error')
                                        })
                                        print(f"      ❌ Failed: {extraction_result.get('error', 'Unknown error')}")
                                
                                except Exception as e:
                                    url_processing_results.append({
                                        'url': url,
                                        'success': False,
                                        'error': str(e)
                                    })
                                    print(f"      ❌ Exception: {str(e)}")
                            
                            # Update Website record with processing status
                            successful_urls = sum(1 for result in url_processing_results if result['success'])
                            website_record.current_page = len(website_record.paper_urls)
                            website_record.is_last_completed = successful_urls > 0
                            website_record.updated_at = datetime.now()
                            
                            session.add(website_record)
                            session.commit()
                            
                            results['processed_websites'].append({
                                'web_id': website_record.web_id,
                                'website_name': websites_info.website_name,
                                'website_type': website_type,
                                'confidence_score': confidence_score,
                                'total_urls': len(website_record.paper_urls),
                                'successful_urls': successful_urls,
                                'failed_urls': len(website_record.paper_urls) - successful_urls,
                                'success_rate': successful_urls / len(website_record.paper_urls) if website_record.paper_urls else 0,
                                'url_results': url_processing_results
                            })
                            
                            print(f"   ✅ Completed: {successful_urls}/{len(website_record.paper_urls)} URLs processed successfully")
                            print(f"   📈 Success Rate: {(successful_urls / len(website_record.paper_urls) * 100):.1f}%")
                        else:
                            print(f"   ⚠️  No URLs found for {websites_info.website_name}")
                            results['skipped_websites'].append({
                                'web_id': website_record.web_id,
                                'website_name': websites_info.website_name,
                                'reason': 'No URLs to process'
                            })
                    
                    except Exception as e:
                        error_msg = f"Failed to process Website ID {website_record.web_id}: {str(e)}"
                        print(f"   ❌ {error_msg}")
                        results['errors'].append(error_msg)
            
            print(f"\n✅ Step 3 Complete!")
            print(f"   Processed: {len(results['processed_websites'])}")
            print(f"   Skipped: {len(results['skipped_websites'])}")
            print(f"   Errors: {len(results['errors'])}")
            
            return {
                'success': True,
                'step': 'STEP_3_AUTO_TOPBAR_PROCESSING',
                'results': results
            }
            
        except Exception as e:
            return {
                'success': False,
                'step': 'STEP_3_AUTO_TOPBAR_PROCESSING',
                'error': str(e)
            }
    
    def run_enhanced_start_process(self, custom_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Run the enhanced start process with auto-detection.
        
        Args:
            custom_urls: Optional list of custom URLs to analyze
            
        Returns:
            Dictionary with complete process results
        """
        try:
            print("🤖 STARTING ENHANCED AUTO-DETECTION PROCESS")
            print("=" * 70)
            print("Flow: Auto-Discovery → Dynamic Config → Intelligent Processing")
            print("=" * 70)
            
            overall_results = {
                'process_start_time': datetime.now().isoformat(),
                'step_results': {},
                'overall_summary': {
                    'successful_steps': 0,
                    'failed_steps': 0,
                    'total_steps': 3,
                    'websites_discovered': 0,
                    'total_urls_processed': 0,
                    'avg_confidence_score': 0.0
                }
            }
            
            # Step 1: Auto-discover and insert websites
            step1_result = self.step1_auto_discover_and_insert_websites(custom_urls)
            overall_results['step_results']['step1'] = step1_result
            if step1_result['success']:
                overall_results['overall_summary']['successful_steps'] += 1
                overall_results['overall_summary']['websites_discovered'] = (
                    len(step1_result['results']['websites_created']) + 
                    len(step1_result['results']['websites_updated'])
                )
            else:
                overall_results['overall_summary']['failed_steps'] += 1
            
            # Step 2: Create dynamic website records
            step2_result = self.step2_create_dynamic_website_records()
            overall_results['step_results']['step2'] = step2_result
            if step2_result['success']:
                overall_results['overall_summary']['successful_steps'] += 1
                
                # Calculate average confidence score
                records = step2_result['results']['records_created'] + step2_result['results']['records_updated']
                if records:
                    avg_confidence = sum(r.get('confidence_score', 0) for r in records) / len(records)
                    overall_results['overall_summary']['avg_confidence_score'] = avg_confidence
            else:
                overall_results['overall_summary']['failed_steps'] += 1
            
            # Step 3: Process auto-detected TopBar websites
            step3_result = self.step3_process_auto_detected_topbar_websites()
            overall_results['step_results']['step3'] = step3_result
            if step3_result['success']:
                overall_results['overall_summary']['successful_steps'] += 1
                
                # Calculate total URLs processed
                processed_websites = step3_result['results']['processed_websites']
                total_urls = sum(w['total_urls'] for w in processed_websites)
                overall_results['overall_summary']['total_urls_processed'] = total_urls
            else:
                overall_results['overall_summary']['failed_steps'] += 1
            
            overall_results['process_end_time'] = datetime.now().isoformat()
            
            # Generate final summary
            print(f"\n🎉 ENHANCED PROCESS SUMMARY")
            print("=" * 50)
            print(f"✅ Successful steps: {overall_results['overall_summary']['successful_steps']}/{overall_results['overall_summary']['total_steps']}")
            print(f"🌐 Websites discovered: {overall_results['overall_summary']['websites_discovered']}")
            print(f"🔗 URLs processed: {overall_results['overall_summary']['total_urls_processed']}")
            print(f"📊 Avg confidence: {overall_results['overall_summary']['avg_confidence_score']:.1%}")
            
            return {
                'success': True,
                'results': overall_results
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'step': 'ENHANCED_PROCESS'
            }


# Convenience functions
def run_enhanced_auto_detection(custom_urls: Optional[List[str]] = None):
    """Run the enhanced auto-detection process."""
    service = EnhancedStartService()
    return service.run_enhanced_start_process(custom_urls)

def detect_single_website(url: str):
    """Detect and configure a single website."""
    service = EnhancedStartService()
    return service.step1_auto_discover_and_insert_websites([url])

if __name__ == "__main__":
    print("🤖 Testing Enhanced Auto-Detection Service")
    print("=" * 60)
    
    # Test with default URLs
    result = run_enhanced_auto_detection()
    
    if result['success']:
        summary = result['results']['overall_summary']
        print(f"\n🎯 FINAL RESULTS:")
        print(f"   Websites: {summary['websites_discovered']}")
        print(f"   URLs: {summary['total_urls_processed']}")
        print(f"   Success Rate: {summary['successful_steps']}/{summary['total_steps']}")
    else:
        print(f"\n❌ Process failed: {result['error']}")
