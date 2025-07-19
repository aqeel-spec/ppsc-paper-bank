#!/usr/bin/env python3
"""
Check database records created by urls_collector
"""

from app.database import get_session
from app.models.websites import Websites
from app.models.website import Website
from sqlmodel import select

def check_database_records():
    session = next(get_session())
    
    try:
        # Check websites table
        print('=' * 60)
        print('WEBSITES TABLE RECORDS')
        print('=' * 60)
        websites = session.exec(select(Websites)).all()
        for website in websites:
            print(f'ID: {website.id}')
            print(f'  Name: {website.website_name}')
            print(f'  Base URL: {website.base_url}')
            print(f'  Type: {website.website_type}')
            print(f'  Active: {website.is_active}')
            print(f'  Created: {website.created_at}')
            print()

        # Check website table
        print('=' * 60)
        print('WEBSITE TABLE RECORDS')
        print('=' * 60)
        website_records = session.exec(select(Website)).all()
        for record in website_records:
            print(f'Web ID: {record.web_id}')
            print(f'  Website Name ID: {record.website_name}')
            print(f'  Top Bar: {record.is_top_bar}')
            print(f'  Side Bar: {record.is_side_bar}')
            print(f'  Paper Exit: {record.is_paper_exit}')
            print(f'  URLs Count: {len(record.paper_urls) if record.paper_urls else 0}')
            print(f'  Pages Count: {record.pages_count}')
            print(f'  Current Page URL: {record.current_page_url}')
            print(f'  Created: {record.created_at}')
            if record.paper_urls:
                print(f'  Sample URLs (first 3):')
                for i, url in enumerate(record.paper_urls[:3]):
                    print(f'    {i+1}. {url}')
                if len(record.paper_urls) > 3:
                    print(f'    ... and {len(record.paper_urls) - 3} more')
            print()
            
    except Exception as e:
        print(f"Error checking database: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    check_database_records()
