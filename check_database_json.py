#!/usr/bin/env python3
"""
Check the database to verify JSON objects are stored properly
"""

from app.database import get_session
from app.models.website import Website
from sqlmodel import select
import json

def check_database_json():
    session = next(get_session())
    
    try:
        print("="*60)
        print("CHECKING DATABASE - PAPER_URLS JSON STRUCTURE")
        print("="*60)
        
        # Get the latest website record
        stmt = select(Website).order_by(Website.web_id.desc()).limit(1)
        latest_record = session.exec(stmt).first()
        
        if latest_record:
            print(f"Web ID: {latest_record.web_id}")
            print(f"Website Name ID: {latest_record.website_name}")
            print(f"Total URLs: {len(latest_record.paper_urls) if latest_record.paper_urls else 0}")
            print()
            
            if latest_record.paper_urls:
                print("Sample URLs with Complete JSON Structure (first 3):")
                for i, url_obj in enumerate(latest_record.paper_urls[:3]):
                    print(f"  {i+1}. {json.dumps(url_obj, indent=6)}")
                    print()
                
                # Verify structure
                first_url = latest_record.paper_urls[0]
                required_fields = ['title', 'url', 'source', 'section', 'is_scraped']
                
                print("Structure Validation:")
                for field in required_fields:
                    has_field = field in first_url
                    print(f"  ✅ {field}: {has_field} - {first_url.get(field, 'N/A')}")
                
                # Count by source
                sources = {}
                for url_obj in latest_record.paper_urls:
                    source = url_obj.get('source', 'unknown')
                    sources[source] = sources.get(source, 0) + 1
                
                print(f"\nSource Distribution:")
                for source, count in sources.items():
                    print(f"  - {source}: {count} URLs")
                    
                # Count by section
                sections = {}
                for url_obj in latest_record.paper_urls:
                    section = url_obj.get('section', 'unknown')
                    sections[section] = sections.get(section, 0) + 1
                
                print(f"\nSection Distribution:")
                for section, count in sections.items():
                    print(f"  - {section}: {count} URLs")
            else:
                print("No paper_urls found in the record")
        else:
            print("No website records found")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    check_database_json()
