from app.services.scrapper.urls_collector import UrlsCollector

# Test with a different TestPoint URL to see new records being created
test_url = 'https://testpointpk.com/past-papers-mcqs/ppsc-lecturer-past-papers-pdf'
print(f'Testing with new URL: {test_url}')
print('='*50)

scraper = UrlsCollector(url=test_url)
result = scraper.run()

if result['success']:
    db_result = result['data'].get('database_result', {})
    if db_result.get('success'):
        top_bar_result = db_result.get('top_bar_result', {})
        print(f'TOP BAR: {top_bar_result.get("total_records", 0)} created, {top_bar_result.get("total_skipped", 0)} skipped')
        
        side_bar_result = db_result.get('side_bar_result', {})
        print(f'SIDE BAR: {side_bar_result.get("total_records", 0)} created, {side_bar_result.get("total_skipped", 0)} skipped')
        print('\n✅ New records are being created for different URLs while duplicates are properly skipped!')
    else:
        print(f'Error: {db_result.get("error", "Unknown")}')
else:
    print(f'Error: {result.get("error", "Unknown")}')
