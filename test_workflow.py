from app.services.complete_data_workflow import DatabaseInsertionService, show_database_stats

def test_workflow():
    """Test the workflow and show results."""
    print("🚀 Testing Complete Data Collection and Insertion")
    print("=" * 60)
    
    # Show initial database stats
    print("\n📊 INITIAL DATABASE STATE:")
    show_database_stats()
    
    # Run the workflow
    service = DatabaseInsertionService()
    results = service.run_complete_data_collection_and_insertion(max_urls_per_category=5)
    
    if results['success']:
        print("\n✅ WORKFLOW COMPLETED SUCCESSFULLY!")
        
        # Show final database stats
        print("\n📊 FINAL DATABASE STATE:")
        show_database_stats()
        
        # Show summary
        insertion_summary = results['insertion_results']['insertion_summary']
        print(f"\n📋 WORKFLOW SUMMARY:")
        print(f"   Content items processed: {insertion_summary['total_content_items']}")
        print(f"   MCQ records created: {insertion_summary['mcq_records_created']}")
        print(f"   Paper records created: {insertion_summary['paper_records_created']}")
        print(f"   Insertion errors: {insertion_summary['insertion_errors']}")
        
        print(f"\n🎯 SUCCESS RATE: {((insertion_summary['mcq_records_created'] + insertion_summary['paper_records_created']) / max(insertion_summary['total_content_items'], 1)) * 100:.1f}%")
        
    else:
        print(f"\n❌ WORKFLOW FAILED: {results.get('error')}")
        print(f"   Failed at step: {results.get('step', 'unknown')}")

if __name__ == "__main__":
    test_workflow()
