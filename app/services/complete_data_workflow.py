from typing import Dict, List, Any, Optional
from datetime import datetime
import json
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_engine
from app.models.websites import Websites
from app.models.category import Category
from app.models.mcqs_bank import MCQ, MCQCreate, AnswerOption
from app.models.paper import PaperModel, PaperCreate
from app.services.targeted_data_insertion import TargetedDataInsertionService


class DatabaseInsertionService:
    """
    Service for inserting collected data into the database.
    Takes the processed content and stores it in appropriate database tables.
    """
    
    def __init__(self):
        self.targeted_service = TargetedDataInsertionService()
    
    def store_content_as_mcq_placeholder(self, content_data: Dict[str, Any]) -> Optional[int]:
        """
        Store content data as MCQ placeholder records.
        
        Args:
            content_data: Processed content data
            
        Returns:
            ID of created MCQ record or None if failed
        """
        try:
            with Session(get_engine()) as session:
                # Get the category to get its slug
                statement = select(Category).where(Category.id == content_data['category_id'])
                category = session.exec(statement).first()
                
                if not category:
                    print(f"   ❌ Category with ID {content_data['category_id']} not found")
                    return None
                
                # Create MCQ placeholder with collected data using correct field names
                mcq_data = MCQCreate(
                    question_text=f"[PLACEHOLDER] {content_data['title']}",
                    option_a="Option A (To be collected)",
                    option_b="Option B (To be collected)", 
                    option_c="Option C (To be collected)",
                    option_d="Option D (To be collected)",
                    correct_answer=AnswerOption.OPTION_A,  # Use enum value
                    explanation=f"Content from: {content_data['url']}",
                    category_slug=category.slug  # Use category slug instead of category_id
                )
                
                # Convert to dict for MCQ model creation, but we need to manually handle category_id
                mcq_dict = mcq_data.model_dump(exclude={'category_slug', 'new_category_slug', 'new_category_name'})
                mcq_dict['category_id'] = content_data['category_id']
                
                # Add metadata as a separate field if MCQ model supports it
                # For now, we'll include it in explanation
                mcq_dict['explanation'] = f"""Content from: {content_data['url']}
Source: {content_data['website_name']} - {content_data['category_name']}
Title: {content_data['title']}
Collected: {content_data['collected_at']}
Status: PLACEHOLDER_CREATED"""
                
                db_mcq = MCQ(**mcq_dict)
                session.add(db_mcq)
                session.commit()
                session.refresh(db_mcq)
                
                return db_mcq.id
                
        except SQLAlchemyError as e:
            print(f"   ❌ Failed to store MCQ placeholder: {str(e)}")
            return None
    
    def store_content_as_paper_placeholder(self, content_data: Dict[str, Any]) -> Optional[int]:
        """
        Store content data as Paper placeholder records.
        
        Args:
            content_data: Processed content data
            
        Returns:
            ID of created Paper record or None if failed
        """
        try:
            with Session(get_engine()) as session:
                # Create Paper placeholder with collected data
                paper_data = PaperCreate(
                    title=content_data['title'],
                    paper_url=content_data['url'],
                    year=datetime.now().year,  # Default to current year
                    paper_type="PRACTICE_TEST",
                    difficulty="Medium",
                    tags=f"{content_data['website_name']},{content_data['category_name']},collected"
                )
                
                db_paper = PaperModel(**paper_data.model_dump())
                session.add(db_paper)
                session.commit()
                session.refresh(db_paper)
                
                return db_paper.id
                
        except SQLAlchemyError as e:
            print(f"   ❌ Failed to store Paper placeholder: {str(e)}")
            return None
    
    def determine_content_type(self, content_data: Dict[str, Any]) -> str:
        """
        Determine the type of content based on URL patterns and title.
        
        Args:
            content_data: Content data to analyze
            
        Returns:
            Content type string
        """
        url = content_data.get('url', '').lower()
        title = content_data.get('title', '').lower()
        
        # Determine content type based on patterns
        if any(keyword in url for keyword in ['mcq', 'quiz', 'question']):
            return 'MCQ'
        elif any(keyword in url for keyword in ['paper', 'test', 'exam']):
            return 'PAPER'
        elif any(keyword in title for keyword in ['mcq', 'quiz', 'question']):
            return 'MCQ'
        elif any(keyword in title for keyword in ['paper', 'test', 'exam']):
            return 'PAPER'
        else:
            # Default to MCQ for most educational content
            return 'MCQ'
    
    def insert_processed_content_to_database(self, processed_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Insert all processed content into the database.
        
        Args:
            processed_results: Results from targeted data insertion
            
        Returns:
            Dictionary with insertion summary
        """
        try:
            if not processed_results['success']:
                return {
                    'success': False,
                    'error': f"Cannot insert data from failed processing: {processed_results.get('error')}"
                }
            
            print("🗄️  Starting Database Insertion Process")
            print("=" * 50)
            
            insertion_summary = {
                'total_websites_processed': 0,
                'total_content_items': 0,
                'mcq_records_created': 0,
                'paper_records_created': 0,
                'insertion_errors': 0,
                'detailed_results': []
            }
            
            results = processed_results['results']
            
            for website_data in results['websites_processed']:
                if not website_data['success']:
                    continue
                
                website_results = website_data['results']
                website_name = website_results['website_name']
                
                print(f"\n🌐 Inserting data for: {website_name}")
                
                website_insertion = {
                    'website_name': website_name,
                    'categories_processed': [],
                    'mcq_records': 0,
                    'paper_records': 0,
                    'errors': 0
                }
                
                for category_data in website_results['processed_categories']:
                    if not category_data['success']:
                        continue
                    
                    category_name = category_data['category']
                    processed_content = category_data.get('processed_content', [])
                    
                    print(f"   📂 {category_name}: {len(processed_content)} items")
                    
                    category_insertion = {
                        'category_name': category_name,
                        'category_id': category_data['category_id'],
                        'content_items': len(processed_content),
                        'mcq_created': 0,
                        'paper_created': 0,
                        'errors': 0
                    }
                    
                    for i, content_item in enumerate(processed_content, 1):
                        content_type = self.determine_content_type(content_item)
                        
                        print(f"      {i}/{len(processed_content)}: {content_item['title'][:40]}... ({content_type})")
                        
                        if content_type == 'MCQ':
                            mcq_id = self.store_content_as_mcq_placeholder(content_item)
                            if mcq_id:
                                category_insertion['mcq_created'] += 1
                                website_insertion['mcq_records'] += 1
                                insertion_summary['mcq_records_created'] += 1
                            else:
                                category_insertion['errors'] += 1
                                website_insertion['errors'] += 1
                                insertion_summary['insertion_errors'] += 1
                        
                        elif content_type == 'PAPER':
                            paper_id = self.store_content_as_paper_placeholder(content_item)
                            if paper_id:
                                category_insertion['paper_created'] += 1
                                website_insertion['paper_records'] += 1
                                insertion_summary['paper_records_created'] += 1
                            else:
                                category_insertion['errors'] += 1
                                website_insertion['errors'] += 1
                                insertion_summary['insertion_errors'] += 1
                        
                        insertion_summary['total_content_items'] += 1
                    
                    website_insertion['categories_processed'].append(category_insertion)
                
                insertion_summary['detailed_results'].append(website_insertion)
                insertion_summary['total_websites_processed'] += 1
            
            print(f"\n✅ Database insertion completed!")
            print(f"   Total content items processed: {insertion_summary['total_content_items']}")
            print(f"   MCQ records created: {insertion_summary['mcq_records_created']}")
            print(f"   Paper records created: {insertion_summary['paper_records_created']}")
            print(f"   Insertion errors: {insertion_summary['insertion_errors']}")
            
            return {
                'success': True,
                'insertion_summary': insertion_summary
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def run_complete_data_collection_and_insertion(self, max_urls_per_category: int = 10) -> Dict[str, Any]:
        """
        Run the complete workflow: collect data and insert into database.
        
        Args:
            max_urls_per_category: Maximum URLs to process per category
            
        Returns:
            Complete workflow results
        """
        try:
            print("🚀 Starting Complete Data Collection and Insertion Workflow")
            print("=" * 70)
            
            # Step 1: Collect data from websites
            print("\n📥 STEP 1: Collecting data from websites...")
            collection_results = self.targeted_service.process_all_websites(max_urls_per_category)
            
            if not collection_results['success']:
                return {
                    'success': False,
                    'error': f"Data collection failed: {collection_results.get('error')}",
                    'step': 'COLLECTION'
                }
            
            # Step 2: Insert collected data into database
            print("\n💾 STEP 2: Inserting collected data into database...")
            insertion_results = self.insert_processed_content_to_database(collection_results)
            
            if not insertion_results['success']:
                return {
                    'success': False,
                    'error': f"Database insertion failed: {insertion_results.get('error')}",
                    'step': 'INSERTION',
                    'collection_results': collection_results
                }
            
            # Step 3: Generate final report
            print("\n📊 STEP 3: Generating final report...")
            final_report = self.create_comprehensive_report(collection_results, insertion_results)
            
            return {
                'success': True,
                'collection_results': collection_results,
                'insertion_results': insertion_results,
                'final_report': final_report
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'step': 'WORKFLOW'
            }
    
    def create_comprehensive_report(self, collection_results: Dict[str, Any], insertion_results: Dict[str, Any]) -> str:
        """Create a comprehensive report of the entire process."""
        
        collection_summary = collection_results['results']['overall_summary']
        insertion_summary = insertion_results['insertion_summary']
        
        report_lines = [
            "📊 COMPREHENSIVE DATA COLLECTION & INSERTION REPORT",
            "=" * 70,
            "",
            "🔍 COLLECTION PHASE:",
            f"   Websites processed: {collection_summary['successful_websites']}/{collection_summary['total_websites']}",
            f"   Categories processed: {collection_summary['total_categories_processed']}",
            f"   URLs collected: {collection_summary['total_urls_collected']}",
            f"   Content items processed: {collection_summary['total_content_processed']}",
            "",
            "💾 DATABASE INSERTION PHASE:",
            f"   Content items inserted: {insertion_summary['total_content_items']}",
            f"   MCQ records created: {insertion_summary['mcq_records_created']}",
            f"   Paper records created: {insertion_summary['paper_records_created']}",
            f"   Insertion errors: {insertion_summary['insertion_errors']}",
            "",
            "📈 SUCCESS RATES:",
            f"   Collection success rate: {(collection_summary['total_content_processed'] / max(collection_summary['total_urls_collected'], 1)) * 100:.1f}%",
            f"   Insertion success rate: {((insertion_summary['mcq_records_created'] + insertion_summary['paper_records_created']) / max(insertion_summary['total_content_items'], 1)) * 100:.1f}%",
            "",
            "🌐 WEBSITE BREAKDOWN:",
            "-" * 40
        ]
        
        for website_data in insertion_summary['detailed_results']:
            report_lines.extend([
                f"",
                f"🌐 {website_data['website_name']}:",
                f"   Categories: {len(website_data['categories_processed'])}",
                f"   MCQ records: {website_data['mcq_records']}",
                f"   Paper records: {website_data['paper_records']}",
                f"   Errors: {website_data['errors']}"
            ])
            
            for category_data in website_data['categories_processed']:
                report_lines.append(
                    f"   📂 {category_data['category_name']}: "
                    f"{category_data['mcq_created']} MCQs, {category_data['paper_created']} Papers"
                )
        
        return "\n".join(report_lines)
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get current database statistics."""
        try:
            with Session(get_engine()) as session:
                # Count records in each table
                websites_count = len(session.exec(select(Websites)).all())
                categories_count = len(session.exec(select(Category)).all())
                mcqs_count = len(session.exec(select(MCQ)).all())
                papers_count = len(session.exec(select(PaperModel)).all())
                
                return {
                    'websites': websites_count,
                    'categories': categories_count,
                    'mcqs': mcqs_count,
                    'papers': papers_count,
                    'total_records': websites_count + categories_count + mcqs_count + papers_count
                }
        except Exception as e:
            return {'error': str(e)}


# Convenience functions
def run_complete_workflow(max_urls_per_category: int = 10):
    """Run the complete data collection and insertion workflow."""
    service = DatabaseInsertionService()
    results = service.run_complete_data_collection_and_insertion(max_urls_per_category)
    
    if results['success']:
        print(f"\n{results['final_report']}")
    else:
        print(f"\n❌ Workflow failed at {results.get('step', 'unknown')} step: {results.get('error')}")
    
    return results

def run_quick_workflow_test(max_urls_per_category: int = 3):
    """Run a quick test of the complete workflow."""
    print("🧪 Running Quick Workflow Test...")
    return run_complete_workflow(max_urls_per_category)

def show_database_stats():
    """Show current database statistics."""
    service = DatabaseInsertionService()
    stats = service.get_database_stats()
    
    if 'error' in stats:
        print(f"❌ Error getting database stats: {stats['error']}")
    else:
        print("\n📊 CURRENT DATABASE STATISTICS:")
        print("=" * 40)
        print(f"🌐 Websites: {stats['websites']}")
        print(f"📂 Categories: {stats['categories']}")
        print(f"❓ MCQs: {stats['mcqs']}")
        print(f"📄 Papers: {stats['papers']}")
        print(f"📊 Total Records: {stats['total_records']}")

if __name__ == "__main__":
    print("🚀 Running Complete Data Workflow...")
    run_quick_workflow_test(max_urls_per_category=5)
