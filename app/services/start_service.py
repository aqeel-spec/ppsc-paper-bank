from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_engine
from app.models.websites import Websites, WebsitesCreate, WebsitesUpdate
from app.models.website import Website, WebsiteCreate, WebsiteUpdate
from app.services.scrapper.top_urls import WebsiteTopService
from app.services.website_data_service import WebsiteDataService


class StartService:
    """
    Comprehensive service for starting the website data collection process.
    
    Flow:
    1. Websites - Insert unique websites (no duplicates)
    2. Website - Handle individual website records with processing flags
    3. isTopBar check - If true, use start_urls service for URL collection
    4. isPaperExit - For future paper processing (placeholder)
    5. isSideBar - For future sidebar processing (placeholder)
    """
    
    def __init__(self):
        self.website_data_service = WebsiteDataService()
        self.url_service = WebsiteTopService()
    
    # Define unique websites for scraping
    UNIQUE_WEBSITES = [
        {
            'website_name': 'PakMcqs',
            'base_url': 'https://pakmcqs.com',
            'website_type': 'PakMcqs',
            'description': 'Pakistani Multiple Choice Questions platform for educational content',
            'is_active': True
        },
        {
            'website_name': 'TestPoint',
            'base_url': 'https://testpoint.pk',
            'website_type': 'TestPoint',
            'description': 'Test preparation platform for competitive exams',
            'is_active': True
        }
    ]
    
    # Website configurations with processing flags
    WEBSITE_CONFIGS = [
        {
            'website_name': 'PakMcqs',
            'is_top_bar': True,
            'is_paper_exit': False,  # Future implementation
            'is_side_bar': False,    # Future implementation
            'urls_to_process': [
                'https://pakmcqs.com/category/english-mcqs',
                'https://pakmcqs.com/category/pak-study-mcqs',
                'https://pakmcqs.com/category/islamiat-mcqs',
                'https://pakmcqs.com/category/general-knowledge-mcqs'
            ]
        },
        {
            'website_name': 'TestPoint',
            'is_top_bar': True,
            'is_paper_exit': False,  # Future implementation
            'is_side_bar': False,    # Future implementation
            'urls_to_process': [
                'https://testpoint.pk/papers/ppsc',
                'https://testpoint.pk/papers/fpsc',
                'https://testpoint.pk/papers/nts'
            ]
        }
    ]
    
    def step1_insert_unique_websites(self) -> Dict[str, Any]:
        """
        Step 1: Insert unique websites without duplicates.
        
        Returns:
            Dictionary with insertion results
        """
        try:
            print("🌐 STEP 1: Inserting Unique Websites")
            print("=" * 50)
            
            results = {
                'total_websites': len(self.UNIQUE_WEBSITES),
                'created_websites': [],
                'existing_websites': [],
                'errors': []
            }
            
            for website_info in self.UNIQUE_WEBSITES:
                print(f"\n🔍 Processing: {website_info['website_name']}")
                
                try:
                    # Use the existing get_or_create_website method to prevent duplicates
                    website_record = self.website_data_service.get_or_create_website(
                        website_name=website_info['website_name'],
                        base_url=website_info['base_url'],
                        website_type=website_info['website_type']
                    )
                    
                    if website_record:
                        # Check if it was newly created or existing
                        with Session(get_engine()) as session:
                            # Count how many records have this name and URL
                            statement = select(Websites).where(
                                Websites.website_name == website_info['website_name'],
                                Websites.base_url == website_info['base_url']
                            )
                            existing_count = len(session.exec(statement).all())
                            
                            if existing_count == 1:
                                print(f"   ✅ Created new website: {website_info['website_name']} (ID: {website_record.id})")
                                results['created_websites'].append({
                                    'id': website_record.id,
                                    'name': website_record.website_name,
                                    'url': website_record.base_url,
                                    'status': 'CREATED'
                                })
                            else:
                                print(f"   ♻️  Using existing website: {website_info['website_name']} (ID: {website_record.id})")
                                results['existing_websites'].append({
                                    'id': website_record.id,
                                    'name': website_record.website_name,
                                    'url': website_record.base_url,
                                    'status': 'EXISTING'
                                })
                    
                except Exception as e:
                    error_msg = f"Failed to process {website_info['website_name']}: {str(e)}"
                    print(f"   ❌ {error_msg}")
                    results['errors'].append(error_msg)
            
            print(f"\n✅ Step 1 Complete!")
            print(f"   Created: {len(results['created_websites'])}")
            print(f"   Existing: {len(results['existing_websites'])}")
            print(f"   Errors: {len(results['errors'])}")
            
            return {
                'success': True,
                'step': 'STEP_1_WEBSITES',
                'results': results
            }
            
        except Exception as e:
            return {
                'success': False,
                'step': 'STEP_1_WEBSITES',
                'error': str(e)
            }
    
    def step2_create_website_records(self) -> Dict[str, Any]:
        """
        Step 2: Create Website records with processing flags.
        
        Returns:
            Dictionary with creation results
        """
        try:
            print("\n🏭 STEP 2: Creating Website Records with Processing Flags")
            print("=" * 60)
            
            results = {
                'total_configs': len(self.WEBSITE_CONFIGS),
                'created_records': [],
                'updated_records': [],
                'errors': []
            }
            
            for config in self.WEBSITE_CONFIGS:
                print(f"\n🔧 Processing config for: {config['website_name']}")
                
                try:
                    # Get the corresponding Websites record
                    with Session(get_engine()) as session:
                        websites_statement = select(Websites).where(
                            Websites.website_name == config['website_name']
                        )
                        websites_record = session.exec(websites_statement).first()
                        
                        if not websites_record:
                            error_msg = f"Websites record not found for {config['website_name']}"
                            print(f"   ❌ {error_msg}")
                            results['errors'].append(error_msg)
                            continue
                        
                        # Check if Website record already exists
                        website_statement = select(Website).where(
                            Website.website_name == websites_record.id
                        )
                        existing_website = session.exec(website_statement).first()
                        
                        if existing_website:
                            # Update existing record
                            existing_website.is_top_bar = config['is_top_bar']
                            existing_website.is_paper_exit = config['is_paper_exit']
                            existing_website.is_side_bar = config['is_side_bar']
                            existing_website.paper_urls = config['urls_to_process']
                            existing_website.updated_at = datetime.now()
                            
                            session.add(existing_website)
                            session.commit()
                            session.refresh(existing_website)
                            
                            print(f"   🔄 Updated existing Website record (ID: {existing_website.web_id})")
                            results['updated_records'].append({
                                'web_id': existing_website.web_id,
                                'website_name': config['website_name'],
                                'websites_id': websites_record.id,
                                'is_top_bar': config['is_top_bar'],
                                'is_paper_exit': config['is_paper_exit'],
                                'is_side_bar': config['is_side_bar'],
                                'urls_count': len(config['urls_to_process']),
                                'status': 'UPDATED'
                            })
                        else:
                            # Create new Website record
                            website_data = WebsiteCreate(
                                is_top_bar=config['is_top_bar'],
                                is_paper_exit=config['is_paper_exit'],
                                is_side_bar=config['is_side_bar'],
                                website_name=websites_record.id,  # Reference to Websites table
                                paper_urls=config['urls_to_process'],
                                pages_count=len(config['urls_to_process']),
                                current_page=1,
                                total_pages=len(config['urls_to_process']),
                                is_last_completed=False
                            )
                            
                            db_website = Website(**website_data.model_dump())
                            session.add(db_website)
                            session.commit()
                            session.refresh(db_website)
                            
                            print(f"   ✅ Created new Website record (ID: {db_website.web_id})")
                            results['created_records'].append({
                                'web_id': db_website.web_id,
                                'website_name': config['website_name'],
                                'websites_id': websites_record.id,
                                'is_top_bar': config['is_top_bar'],
                                'is_paper_exit': config['is_paper_exit'],
                                'is_side_bar': config['is_side_bar'],
                                'urls_count': len(config['urls_to_process']),
                                'status': 'CREATED'
                            })
                
                except Exception as e:
                    error_msg = f"Failed to process {config['website_name']}: {str(e)}"
                    print(f"   ❌ {error_msg}")
                    results['errors'].append(error_msg)
            
            print(f"\n✅ Step 2 Complete!")
            print(f"   Created: {len(results['created_records'])}")
            print(f"   Updated: {len(results['updated_records'])}")
            print(f"   Errors: {len(results['errors'])}")
            
            return {
                'success': True,
                'step': 'STEP_2_WEBSITE_RECORDS',
                'results': results
            }
            
        except Exception as e:
            return {
                'success': False,
                'step': 'STEP_2_WEBSITE_RECORDS',
                'error': str(e)
            }
    
    def step3_process_topbar_websites(self) -> Dict[str, Any]:
        """
        Step 3: Process websites with isTopBar = True using start_urls service.
        
        Returns:
            Dictionary with processing results
        """
        try:
            print("\n📊 STEP 3: Processing TopBar Websites")
            print("=" * 50)
            
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
                print(f"🔍 Found {len(topbar_websites)} websites with TopBar enabled")
                
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
                        
                        print(f"\n🚀 Processing TopBar for: {websites_info.website_name}")
                        
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
                                'total_urls': len(website_record.paper_urls),
                                'successful_urls': successful_urls,
                                'failed_urls': len(website_record.paper_urls) - successful_urls,
                                'url_results': url_processing_results
                            })
                            
                            print(f"   ✅ Completed: {successful_urls}/{len(website_record.paper_urls)} URLs processed successfully")
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
                'step': 'STEP_3_TOPBAR_PROCESSING',
                'results': results
            }
            
        except Exception as e:
            return {
                'success': False,
                'step': 'STEP_3_TOPBAR_PROCESSING',
                'error': str(e)
            }
    
    def step4_process_paper_exit_websites(self) -> Dict[str, Any]:
        """
        Step 4: Process websites with isPaperExit = True (Future implementation).
        
        Returns:
            Dictionary with processing results
        """
        print("\n📄 STEP 4: Processing PaperExit Websites (Future Implementation)")
        print("=" * 60)
        print("🚧 This feature will be implemented in future iterations")
        print("   - Will handle paper extraction and processing")
        print("   - Will integrate with paper processing services")
        
        return {
            'success': True,
            'step': 'STEP_4_PAPER_EXIT',
            'message': 'Feature reserved for future implementation',
            'status': 'PLACEHOLDER'
        }
    
    def step5_process_sidebar_websites(self) -> Dict[str, Any]:
        """
        Step 5: Process websites with isSideBar = True (Future implementation).
        
        Returns:
            Dictionary with processing results
        """
        print("\n📋 STEP 5: Processing SideBar Websites (Future Implementation)")
        print("=" * 60)
        print("🚧 This feature will be implemented in future iterations")
        print("   - Will handle sidebar navigation processing")
        print("   - Will integrate with navigation services")
        
        return {
            'success': True,
            'step': 'STEP_5_SIDEBAR',
            'message': 'Feature reserved for future implementation',
            'status': 'PLACEHOLDER'
        }
    
    def run_complete_start_process(self) -> Dict[str, Any]:
        """
        Run the complete start process following the defined flow.
        
        Returns:
            Dictionary with complete process results
        """
        try:
            print("🚀 STARTING COMPLETE WEBSITE DATA PROCESSING")
            print("=" * 70)
            print("Flow: Websites → Website → TopBar → PaperExit → SideBar")
            print("=" * 70)
            
            overall_results = {
                'process_start_time': datetime.now().isoformat(),
                'step_results': {},
                'overall_summary': {
                    'successful_steps': 0,
                    'failed_steps': 0,
                    'total_steps': 5
                }
            }
            
            # Step 1: Insert unique websites
            step1_result = self.step1_insert_unique_websites()
            overall_results['step_results']['step1'] = step1_result
            if step1_result['success']:
                overall_results['overall_summary']['successful_steps'] += 1
            else:
                overall_results['overall_summary']['failed_steps'] += 1
                # Continue with other steps even if this fails
            
            # Step 2: Create website records
            step2_result = self.step2_create_website_records()
            overall_results['step_results']['step2'] = step2_result
            if step2_result['success']:
                overall_results['overall_summary']['successful_steps'] += 1
            else:
                overall_results['overall_summary']['failed_steps'] += 1
            
            # Step 3: Process TopBar websites
            step3_result = self.step3_process_topbar_websites()
            overall_results['step_results']['step3'] = step3_result
            if step3_result['success']:
                overall_results['overall_summary']['successful_steps'] += 1
            else:
                overall_results['overall_summary']['failed_steps'] += 1
            
            # Step 4: Process PaperExit websites (Future)
            step4_result = self.step4_process_paper_exit_websites()
            overall_results['step_results']['step4'] = step4_result
            if step4_result['success']:
                overall_results['overall_summary']['successful_steps'] += 1
            else:
                overall_results['overall_summary']['failed_steps'] += 1
            
            # Step 5: Process SideBar websites (Future)
            step5_result = self.step5_process_sidebar_websites()
            overall_results['step_results']['step5'] = step5_result
            if step5_result['success']:
                overall_results['overall_summary']['successful_steps'] += 1
            else:
                overall_results['overall_summary']['failed_steps'] += 1
            
            overall_results['process_end_time'] = datetime.now().isoformat()
            
            # Generate final summary
            print(f"\n🎉 COMPLETE PROCESS SUMMARY")
            print("=" * 50)
            print(f"✅ Successful steps: {overall_results['overall_summary']['successful_steps']}/{overall_results['overall_summary']['total_steps']}")
            print(f"❌ Failed steps: {overall_results['overall_summary']['failed_steps']}")
            
            # Show step-by-step results
            for step_name, step_result in overall_results['step_results'].items():
                status = "✅" if step_result['success'] else "❌"
                print(f"{status} {step_result['step']}: {'Success' if step_result['success'] else step_result.get('error', 'Failed')}")
            
            return {
                'success': True,
                'results': overall_results
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'step': 'COMPLETE_PROCESS'
            }
    
    def create_process_report(self, results: Dict[str, Any]) -> str:
        """Create a detailed report of the complete process."""
        if not results['success']:
            return f"❌ Process failed: {results.get('error')}"
        
        process_results = results['results']
        report_lines = [
            "📊 COMPLETE START PROCESS REPORT",
            "=" * 60,
            "",
            f"🕐 Process Duration: {process_results['process_start_time']} → {process_results['process_end_time']}",
            f"✅ Successful Steps: {process_results['overall_summary']['successful_steps']}/{process_results['overall_summary']['total_steps']}",
            f"❌ Failed Steps: {process_results['overall_summary']['failed_steps']}",
            "",
            "STEP-BY-STEP BREAKDOWN:",
            "-" * 40
        ]
        
        for step_name, step_result in process_results['step_results'].items():
            status = "✅" if step_result['success'] else "❌"
            report_lines.append(f"{status} {step_result['step']}")
            
            if step_result['success'] and 'results' in step_result:
                step_results = step_result['results']
                if step_name == 'step1':
                    report_lines.append(f"   Created websites: {len(step_results['created_websites'])}")
                    report_lines.append(f"   Existing websites: {len(step_results['existing_websites'])}")
                elif step_name == 'step2':
                    report_lines.append(f"   Created records: {len(step_results['created_records'])}")
                    report_lines.append(f"   Updated records: {len(step_results['updated_records'])}")
                elif step_name == 'step3':
                    report_lines.append(f"   Processed websites: {len(step_results['processed_websites'])}")
                    report_lines.append(f"   Skipped websites: {len(step_results['skipped_websites'])}")
            elif not step_result['success']:
                report_lines.append(f"   Error: {step_result.get('error', 'Unknown error')}")
        
        return "\n".join(report_lines)


# Convenience functions for easy execution
def run_start_process():
    """Run the complete start process."""
    service = StartService()
    results = service.run_complete_start_process()
    report = service.create_process_report(results)
    print(f"\n{report}")
    return results

def run_individual_step(step_number: int):
    """Run an individual step of the process."""
    service = StartService()
    
    if step_number == 1:
        return service.step1_insert_unique_websites()
    elif step_number == 2:
        return service.step2_create_website_records()
    elif step_number == 3:
        return service.step3_process_topbar_websites()
    elif step_number == 4:
        return service.step4_process_paper_exit_websites()
    elif step_number == 5:
        return service.step5_process_sidebar_websites()
    else:
        return {'success': False, 'error': f'Invalid step number: {step_number}'}

if __name__ == "__main__":
    print("🚀 Running Complete Start Process...")
    run_start_process()
