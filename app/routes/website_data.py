from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Optional
from pydantic import BaseModel

from app.services.website_data_service import WebsiteDataService, setup_all_predefined_websites
from app.models.websites import WebsitesCreate, WebsitesUpdate, WebsitesRead

router = APIRouter(prefix="/api/website-data", tags=["Website Data Management"])


class WebsiteSetupRequest(BaseModel):
    website_url: str
    website_name: str
    create_categories: bool = True
    create_top_bar: bool = True


class WebsiteSetupResponse(BaseModel):
    success: bool
    website_id: Optional[int]
    website_name: str
    setup_results: Dict
    error: Optional[str] = None


@router.post("/setup", response_model=WebsiteSetupResponse)
async def setup_website_data(request: WebsiteSetupRequest):
    """
    Setup complete website data: collect URLs, create categories, and top bar records.
    """
    try:
        service = WebsiteDataService()
        result = service.setup_complete_website_data(
            website_url=request.website_url,
            website_name=request.website_name,
            create_categories=request.create_categories,
            create_top_bar=request.create_top_bar
        )
        
        return WebsiteSetupResponse(
            success=result['success'],
            website_id=result.get('website_id'),
            website_name=result.get('website_name', request.website_name),
            setup_results=result.get('setup_results', {}),
            error=result.get('error')
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to setup website data: {str(e)}")


@router.post("/setup-predefined")
async def setup_predefined_websites():
    """
    Setup data for all predefined websites (TestPoint, PakMcqs categories).
    """
    try:
        result = setup_all_predefined_websites()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to setup predefined websites: {str(e)}")


@router.post("/collect-only")
async def collect_website_data_only(website_url: str, website_name: str):
    """
    Only collect and store website data without creating categories or top bar.
    """
    try:
        service = WebsiteDataService()
        result = service.collect_and_store_website_data(website_url, website_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to collect website data: {str(e)}")


@router.post("/create-categories/{website_id}")
async def create_categories_from_website(website_id: int):
    """
    Create category records from existing website data.
    """
    try:
        service = WebsiteDataService()
        categories = service.create_categories_from_website_data(website_id)
        return {
            'success': True,
            'website_id': website_id,
            'categories_created': len(categories),
            'categories': categories
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create categories: {str(e)}")


@router.post("/create-top-bar/{website_id}")
async def create_top_bar_from_website(website_id: int, title: Optional[str] = None):
    """
    Create top bar record from existing website data.
    """
    try:
        service = WebsiteDataService()
        result = service.create_top_bar_from_website_data(website_id, title)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create top bar: {str(e)}")


@router.get("/websites", response_model=List[WebsitesRead])
async def get_all_websites():
    """
    Get all stored website entries.
    """
    try:
        service = WebsiteDataService()
        websites = service.get_all_websites()
        return websites
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get websites: {str(e)}")


@router.get("/websites/{website_id}", response_model=WebsitesRead)
async def get_website_by_id(website_id: int):
    """
    Get website by ID.
    """
    try:
        service = WebsiteDataService()
        website = service.get_website_by_id(website_id)
        if not website:
            raise HTTPException(status_code=404, detail=f"Website with ID {website_id} not found")
        return website
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get website: {str(e)}")


@router.put("/websites/{website_id}", response_model=WebsitesRead)
async def update_website(website_id: int, update_data: WebsitesUpdate):
    """
    Update website entry.
    """
    try:
        service = WebsiteDataService()
        updated_website = service.update_website_entry(website_id, update_data)
        return updated_website
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update website: {str(e)}")


@router.post("/websites", response_model=WebsitesRead)
async def create_website(website_data: WebsitesCreate):
    """
    Create new website entry manually.
    """
    try:
        service = WebsiteDataService()
        created_website = service.create_website_entry(website_data)
        return created_website
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create website: {str(e)}")


# Example usage endpoints
@router.get("/examples/available-sites")
async def get_available_sites():
    """
    Get list of predefined sites that can be setup.
    """
    return {
        "predefined_sites": [
            {
                "name": "TestPoint PPSC Assistant",
                "url": "https://testpointpk.com/past-papers-mcqs/ppsc-assistant-past-papers-pdf",
                "description": "PPSC Assistant past papers and syllabus",
                "website_type": "testpoint"
            },
            {
                "name": "PakMcqs Pakistan Current Affairs",
                "url": "https://pakmcqs.com/category/pakistan-current-affairs-mcqs",
                "description": "Current affairs MCQs related to Pakistan",
                "website_type": "pakmcqs"
            },
            {
                "name": "PakMcqs English MCQs",
                "url": "https://pakmcqs.com/category/english-mcqs",
                "description": "English language MCQs",
                "website_type": "pakmcqs"
            },
            {
                "name": "PakMcqs General Knowledge",
                "url": "https://pakmcqs.com/category/general_knowledge_mcqs",
                "description": "General knowledge MCQs",
                "website_type": "pakmcqs"
            }
        ]
    }


# Usage documentation
"""
# API Usage Examples:

## 1. Setup a single website with categories and top bar:
POST /api/website-data/setup
{
    "website_url": "https://pakmcqs.com/category/english-mcqs",
    "website_name": "English MCQs",
    "create_categories": true,
    "create_top_bar": true
}

## 2. Setup all predefined websites:
POST /api/website-data/setup-predefined

## 3. Only collect website data (no categories/top bar):
POST /api/website-data/collect-only?website_url=https://pakmcqs.com/category/english-mcqs&website_name=English

## 4. Create categories from existing website data:
POST /api/website-data/create-categories/1

## 5. Create top bar from existing website data:
POST /api/website-data/create-top-bar/1?title=My Top Bar

## 6. Get all websites:
GET /api/website-data/websites

## 7. Get specific website:
GET /api/website-data/websites/1

## 8. Update website:
PUT /api/website-data/websites/1
{
    "website_names": ["Updated Name 1", "Updated Name 2"],
    "websites_urls": ["http://example1.com", "http://example2.com"]
}
"""
