from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional
from pydantic import BaseModel
from app.services.scrapper.top_urls import WebsiteTopService, collect_ppsc_assistant_urls, collect_pakmcqs_urls

router = APIRouter(prefix="/api/collector", tags=["URL Collector"])


class URLResponse(BaseModel):
    success: bool
    title: Optional[str]
    total_urls: int
    urls: List[Dict[str, str]]
    source_url: Optional[str]
    website_type: Optional[str] = None
    error: Optional[str] = None


class MultiPageResponse(BaseModel):
    success: bool
    title: Optional[str]
    total_pages_scraped: int
    total_unique_urls: int
    urls: List[Dict[str, str]]


@router.get("/ppsc-assistant", response_model=URLResponse)
async def get_ppsc_assistant_urls():
    """
    Extract URLs from PPSC Assistant Past Papers page (TestPoint)
    """
    try:
        result = collect_ppsc_assistant_urls()
        return URLResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to collect URLs: {str(e)}")


@router.get("/pakmcqs", response_model=URLResponse)
async def get_pakmcqs_urls(category_url: str = "https://pakmcqs.com/category/pakistan-current-affairs-mcqs"):
    """
    Extract URLs from PakMcqs category page
    
    Args:
        category_url: The URL of the PakMcqs category page to scrape
    """
    try:
        result = collect_pakmcqs_urls(category_url)
        return URLResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to collect PakMcqs URLs: {str(e)}")


@router.get("/extract", response_model=URLResponse)
async def extract_urls_from_page(page_url: str):
    """
    Extract URLs from any supported page (TestPoint, PakMcqs, etc.)
    Automatically detects website type
    
    Args:
        page_url: The URL of the page to scrape
    """
    try:
        collector = WebsiteTopService()
        result = collector.extract_urls_and_title(page_url)
        return URLResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract URLs: {str(e)}")


@router.get("/multiple-pages", response_model=MultiPageResponse)
async def extract_multiple_pages(base_url: str, max_pages: int = 10):
    """
    Extract URLs from multiple pages with pagination
    
    Args:
        base_url: The base URL of the category page (without page parameter)
        max_pages: Maximum number of pages to scrape (default: 10)
    """
    try:
        if max_pages > 50:
            raise HTTPException(status_code=400, detail="Max pages cannot exceed 50")
        
        collector = WebsiteTopService()
        results = collector.extract_multiple_pages(base_url, max_pages)
        unique_urls = collector.get_all_unique_urls(results)
        
        # Get title from first successful result
        title = None
        for result in results:
            if result.get('success') and result.get('title'):
                title = result['title']
                break
        
        response_data = {
            'success': True,
            'title': title,
            'total_pages_scraped': len([r for r in results if r.get('success')]),
            'total_unique_urls': len(unique_urls),
            'urls': unique_urls
        }
        
        return MultiPageResponse(**response_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to collect URLs from multiple pages: {str(e)}")


@router.get("/categories")
async def get_available_categories():
    """
    Get a list of available categories to scrape
    """
    categories = [
        {
            "name": "PPSC Assistant Past Papers",
            "url": "https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf",
            "description": "PPSC Assistant past papers and syllabus",
            "website": "TestPoint"
        },
        {
            "name": "Pakistan Current Affairs MCQs", 
            "url": "https://pakmcqs.com/category/pakistan-current-affairs-mcqs",
            "description": "Current affairs MCQs related to Pakistan",
            "website": "PakMcqs"
        },
        {
            "name": "General Knowledge MCQs",
            "url": "https://pakmcqs.com/category/general_knowledge_mcqs", 
            "description": "General knowledge multiple choice questions",
            "website": "PakMcqs"
        },
        {
            "name": "Islamic Studies MCQs",
            "url": "https://pakmcqs.com/category/islamic-studies-mcqs",
            "description": "Islamic studies MCQs for competitive exams",
            "website": "PakMcqs"
        },
        {
            "name": "Pak Study MCQs",
            "url": "https://pakmcqs.com/category/pak-study-mcqs",
            "description": "Pakistan studies MCQs and questions",
            "website": "PakMcqs"
        }
    ]
    
    return {
        "success": True,
        "total_categories": len(categories),
        "categories": categories
    }


# Example usage:
"""
# To use these endpoints in your FastAPI app, add this to your main.py:

from app.routes.url_collector import router as url_collector_router
app.include_router(url_collector_router)

# Then you can access:
# GET /api/collector/ppsc-assistant - Get PPSC Assistant URLs
# GET /api/collector/extract?page_url=https://testpointpk.com/... - Extract from any page
# GET /api/collector/multiple-pages?base_url=https://testpointpk.com/...&max_pages=5 - Extract from multiple pages
# GET /api/collector/categories - Get available categories
"""
