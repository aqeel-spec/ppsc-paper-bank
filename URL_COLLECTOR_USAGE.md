# URL Collector Service - Multi-Website Support

This service now supports multiple website types including TestPoint and PakMcqs with automatic detection.

## 1. Basic Usage - TestPoint Website

```python
from app.services.top_urls import WebsiteTopService, collect_ppsc_assistant_urls

# Quick way to get PPSC Assistant URLs (TestPoint)
result = collect_ppsc_assistant_urls()
print(f"Title: {result['title']}")
print(f"Found {result['total_urls']} URLs")
print(f"Website type: {result['website_type']}")
for url_data in result['urls'][:5]:  # First 5 URLs
    print(f"- {url_data['title']}: {url_data['url']}")
```

## 2. Basic Usage - PakMcqs Website

```python
from app.services.top_urls import collect_pakmcqs_urls

# Quick way to get Pakistan Current Affairs URLs (PakMcqs)
result = collect_pakmcqs_urls()
print(f"Title: {result['title']}")
print(f"Found {result['total_urls']} URLs")
print(f"Website type: {result['website_type']}")

# Or specify a different category
result = collect_pakmcqs_urls("https://pakmcqs.com/category/english-mcqs")
for url_data in result['urls']:
    print(f"- {url_data['title']}: {url_data['url']}")
```

## 3. Universal URL Extraction (Auto-Detection)

```python
from app.services.top_urls import WebsiteTopService

collector = WebsiteTopService()

# Works with both TestPoint and PakMcqs - automatically detects website type
testpoint_result = collector.extract_urls_and_title("https://testpointpk.com/important-mcqs/islamic-studies-mcqs")
pakmcqs_result = collector.extract_urls_and_title("https://pakmcqs.com/category/pak-study-mcqs")

for result in [testpoint_result, pakmcqs_result]:
    if result['success']:
        print(f"Website: {result['website_type']}")
        print(f"Page Title: {result['title']}")
        print(f"Found {result['total_urls']} URLs")
        for url_data in result['urls'][:3]:
            print(f"- {url_data['title']}: {url_data['url']}")
        print("-" * 50)
    else:
        print(f"Error: {result['error']}")
```

## 4. Extract from multiple pages with pagination

```python
from app.services.top_urls import WebsiteTopService

collector = WebsiteTopService()

# Collect URLs from first 5 pages of a category (works with both sites)
base_url = "https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf"
results = collector.extract_multiple_pages(base_url, max_pages=5)
unique_urls = collector.get_all_unique_urls(results)

print(f"Scraped {len([r for r in results if r.get('success')])} pages")
print(f"Found {len(unique_urls)} unique URLs")

# Access all URLs
for url_data in unique_urls:
    print(f"- {url_data['title']}: {url_data['url']}")
```

## 4. Integration with Database

```python
from app.services.top_urls import collect_ppsc_assistant_urls
from app.models.paper import Paper
from sqlmodel import Session
from app.database import get_session

def save_papers_to_database():
    """Save collected URLs to database"""
    result = collect_ppsc_assistant_urls()

    if not result['success']:
        print(f"Failed to collect URLs: {result.get('error')}")
        return

    with Session(get_session()) as session:
        for url_data in result['urls']:
            # Check if paper already exists
            existing = session.query(Paper).filter(Paper.url == url_data['url']).first()
            if not existing:
                paper = Paper(
                    title=url_data['title'],
                    url=url_data['url'],
                    category="PPSC Assistant"
                )
                session.add(paper)

        session.commit()
        print(f"Saved {len(result['urls'])} papers to database")

# Call the function
save_papers_to_database()
```

## 5. Use in FastAPI endpoint

```python
from fastapi import APIRouter, HTTPException
from app.services.top_urls import collect_ppsc_assistant_urls

router = APIRouter()

@router.get("/papers/ppsc-assistant")
async def get_ppsc_assistant_papers():
    """Get PPSC Assistant papers"""
    result = collect_ppsc_assistant_urls()

    if not result['success']:
        raise HTTPException(status_code=500, detail=result.get('error'))

    return {
        "title": result['title'],
        "total_papers": result['total_urls'],
        "papers": result['urls']
    }
```

## 6. Filter and process URLs

```python
from app.services.top_urls import collect_ppsc_assistant_urls

def get_recent_papers(year=2024):
    """Get papers from a specific year"""
    result = collect_ppsc_assistant_urls()

    if not result['success']:
        return []

    # Filter papers by year
    recent_papers = []
    for url_data in result['urls']:
        if str(year) in url_data['title']:
            recent_papers.append(url_data)

    return recent_papers

# Get 2024 papers
papers_2024 = get_recent_papers(2024)
print(f"Found {len(papers_2024)} papers from 2024")
```

## 7. Error handling and retry logic

```python
import time
from app.services.top_urls import URLCollectorService

def collect_with_retry(url, max_retries=3, delay=1):
    """Collect URLs with retry logic"""
    collector = URLCollectorService()

    for attempt in range(max_retries):
        try:
            result = collector.extract_urls_and_title(url)
            if result['success']:
                return result
            else:
                print(f"Attempt {attempt + 1} failed: {result.get('error')}")
        except Exception as e:
            print(f"Attempt {attempt + 1} error: {str(e)}")

        if attempt < max_retries - 1:
            time.sleep(delay)
            delay *= 2  # Exponential backoff

    return {'success': False, 'error': 'All retry attempts failed'}

# Use with retry
result = collect_with_retry("https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf")
```

## 8. Async version for better performance

```python
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict

async def async_extract_urls(urls: List[str]) -> List[Dict]:
    """Extract URLs from multiple pages asynchronously"""
    async def fetch_page(session, url):
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.text()
                    # Use your existing extraction logic here
                    soup = BeautifulSoup(content, 'html.parser')
                    # ... extraction logic
                    return {'url': url, 'success': True, 'data': []}
                else:
                    return {'url': url, 'success': False, 'error': f'HTTP {response.status}'}
        except Exception as e:
            return {'url': url, 'success': False, 'error': str(e)}

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_page(session, url) for url in urls]
        results = await asyncio.gather(*tasks)
        return results

# Usage
urls_to_scrape = [
    "https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf",
    "https://testpointpk.com/important-mcqs/islamic-studies-mcqs",
    # ... more URLs
]

results = asyncio.run(async_extract_urls(urls_to_scrape))
```

## Available Service Methods

### URLCollectorService Class Methods:

- `extract_urls_and_title(page_url)` - Extract from a single page
- `extract_multiple_pages(base_url, max_pages)` - Extract from multiple pages
- `get_all_unique_urls(results)` - Get unique URLs from multiple results

### Helper Functions:

- `collect_ppsc_assistant_urls()` - Quick function for PPSC Assistant URLs
- `collect_urls_from_multiple_pages(base_url, max_pages)` - Multi-page collection

### Response Format:

```python
{
    'success': bool,
    'title': str,  # Page title
    'urls': [
        {
            'url': str,      # Full URL
            'title': str,    # Link text
            'index': int     # Sequential number
        }
    ],
    'total_urls': int,
    'source_url': str,
    'error': str  # Only present if success is False
}
```
