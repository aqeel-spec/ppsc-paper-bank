#!/usr/bin/env python3
"""
Test Script for Paper MCQ Collector V1
Simple wrapper to test the main functionality
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from app.services.scrapper.paper_mcqs_collector_v1 import PaperMCQCollectorV1
    from app.database import get_session
    import argparse

    def main():
        parser = argparse.ArgumentParser(description="Test Paper MCQ Collector V1")
        parser.add_argument("url", nargs='?', help="URL to scrape MCQs from")
        parser.add_argument("--max-pages", type=int, default=2, help="Maximum number of pages to scrape")
        parser.add_argument("--list", action="store_true", help="List resumable sessions")
        parser.add_argument("--resume", type=int, help="Resume session by ID")
        
        args = parser.parse_args()
        
        if not any([args.url, args.list, args.resume]):
            print("🎯 Paper MCQ Collector V1 - Test Interface")
            print("=" * 50)
            print("Usage:")
            print("  python test_collector.py 'URL' --max-pages 5")
            print("  python test_collector.py --list")
            print("  python test_collector.py --resume 123")
            print("=" * 50)
            return
        
        # Get database session
        session_gen = get_session()
        session = next(session_gen)
        
        try:
            collector = PaperMCQCollectorV1(session)
            
            if args.list:
                print("📋 Resumable Sessions:")
                sessions = collector.list_resumable_sessions()
                if not sessions:
                    print("   No resumable sessions found.")
                else:
                    for state in sessions:
                        info = state.get_resume_info()
                        print(f"   ID: {state.id} | URL: {state.base_url}")
                        print(f"       Progress: {info['processed_pages']}/{info['total_pages']} pages")
                        print(f"       MCQs: {info['mcqs_collected']} | Status: {state.status.value}")
                        
            elif args.resume:
                print(f"🔄 Resuming session {args.resume}")
                result = collector.resume_scraping_session(args.resume)
                print(f"Result: {result}")
                
            elif args.url:
                print(f"🚀 Starting collection from: {args.url}")
                print(f"📄 Max pages: {args.max_pages}")
                result = collector.collect_from_url(args.url, args.max_pages)
                
                if result["success"]:
                    print(f"\n✅ SUCCESS!")
                    print(f"📊 MCQs: {result['total_mcqs']} total ({result['new_mcqs']} new)")
                    print(f"📄 Pages: {result['pages_processed']}")
                    print(f"📋 State ID: {result.get('scraping_state_id', 'N/A')}")
                else:
                    print(f"\n❌ FAILED: {result.get('error', 'Unknown error')}")
                    
        finally:
            session_gen.close()

    if __name__ == "__main__":
        main()
        
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please run this from the project root directory")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
