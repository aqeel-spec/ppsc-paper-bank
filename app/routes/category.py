"""
Category API Routes
Handles CRUD operations for dynamic categories.
"""
from typing import List
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlmodel import Session, select, func

from ..database import get_session
from ..models.category import (
    Category,
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    CategoryWithMCQs,
    CategoryService
)

router = APIRouter(prefix="/categories", tags=["categories"])


@router.post("/", response_model=CategoryResponse)
def create_category(
    category_data: CategoryCreate,
    session: Session = Depends(get_session)
):
    """
    Create a new category with auto-generated slug if not provided.
    """
    try:
        category = CategoryService.create_category(category_data, session)
        return CategoryResponse.model_validate(category)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=List[CategoryResponse])
def get_all_categories(session: Session = Depends(get_session)):
    """
    Get all categories.
    """
    categories = CategoryService.get_all_categories(session)
    return [CategoryResponse.model_validate(cat) for cat in categories]


@router.get("/{slug}", response_model=CategoryResponse)
def get_category_by_id(
    slug: str,
    session: Session = Depends(get_session)
):
    """
    Get a category by ID.
    """
    # category = CategoryService.get_category_by_id(category_id, session)
    category = CategoryService.get_category_by_slug(slug, session)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return CategoryResponse.model_validate(category)


@router.get("/slug/{slug}", response_model=CategoryResponse)
def get_category_by_slug(
    slug: str,
    session: Session = Depends(get_session)
):
    """
    Get a category by slug.
    """
    category = CategoryService.get_category_by_slug(slug, session)
    if not category:
        raise HTTPException(status_code=404, detail=f"Category with slug '{slug}' not found")
    return CategoryResponse.model_validate(category)


@router.get("/{slug}/with-mcqs/{mcq_id}")
def get_category_single_mcq(
    slug: str,
    mcq_id: int,
    explanation: bool = False,
    with_mcq: bool = True,
    session: Session = Depends(get_session)
):
    """
    Get a single MCQ from a category with optional filtering.
    
    Query Parameters:
    - explanation: If True, include/focus on explanation
    - with_mcq: If False with explanation=True, return only ID and explanation
    
    Examples:
    - /{slug}/with-mcqs/{id} - Full MCQ details (default)
    - /{slug}/with-mcqs/{id}?explanation=True - Full MCQ with explanation
    - /{slug}/with-mcqs/{id}?explanation=True&with_mcq=False - Only ID and explanation
    """
    from ..models.mcq import MCQ
    
    # Get the MCQ and verify it belongs to this category
    category = CategoryService.get_category_by_slug(slug, session)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    mcq = session.get(MCQ, mcq_id)
    if not mcq:
        raise HTTPException(status_code=404, detail="MCQ not found")
    
    if mcq.category_id != category.id:
        raise HTTPException(status_code=404, detail="MCQ not found in this category")
    
    # Build response based on parameters
    if explanation and not with_mcq:
        # Return only ID and explanation
        return {
            "id": mcq.id,
            "explanation": mcq.explanation
        }
    else:
        # Return full MCQ
        return mcq


@router.get("/{slug}/with-mcqs")
def get_category_with_mcqs(
    slug: str,
    explanation: bool = False,
    with_mcq: bool = True,
    limit: int = Query(default=10, ge=1, le=100, description="Number of MCQs to return"),
    offset: int = Query(default=0, ge=0, description="Number of MCQs to skip"),
    session: Session = Depends(get_session)
):
    """
    Get a category with its MCQs, with optional filtering and pagination.
    
    Query Parameters:
    - explanation: If True, include/focus on explanations
    - with_mcq: If False with explanation=True, return only ID and explanation for each MCQ
    - limit: Maximum number of MCQs to return (default: 10, max: 100)
    - offset: Number of MCQs to skip for pagination (default: 0)
    
    Examples:
    - /{slug}/with-mcqs - First 10 MCQs with full details (default)
    - /{slug}/with-mcqs?limit=20 - First 20 MCQs
    - /{slug}/with-mcqs?limit=10&offset=10 - MCQs 11-20
    - /{slug}/with-mcqs?explanation=True - Full MCQs (explanations included in model)
    - /{slug}/with-mcqs?explanation=True&with_mcq=False - Only MCQ IDs and explanations
    """
    from sqlalchemy.orm import selectinload
    from sqlmodel import select
    from ..models.mcq import MCQ
    
    # Get category first
    category = session.exec(select(Category).where(Category.slug == slug)).first()
    
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Get total count of MCQs in this category
    total_mcqs = session.exec(
        select(func.count(MCQ.id)).where(MCQ.category_id == category.id)
    ).one()
    
    # Get paginated MCQs
    mcqs_query = (
        select(MCQ)
        .where(MCQ.category_id == category.id)
        .order_by(MCQ.id)
        .offset(offset)
        .limit(limit)
    )
    mcqs = session.exec(mcqs_query).all()
    
    # Build response based on parameters
    if explanation and not with_mcq:
        # Return only IDs and explanations for each MCQ
        mcqs_minimal = [
            {"id": mcq.id, "explanation": mcq.explanation}
            for mcq in mcqs
        ]
        return {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
            "created_at": category.created_at,
            "updated_at": category.updated_at,
            "total_mcqs": total_mcqs,
            "limit": limit,
            "offset": offset,
            "mcqs": mcqs_minimal
        }
    else:
        # Return full category with paginated MCQ details (default)
        return {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
            "created_at": category.created_at,
            "updated_at": category.updated_at,
            "total_mcqs": total_mcqs,
            "limit": limit,
            "offset": offset,
            "mcqs": [mcq.model_dump() for mcq in mcqs]
        }


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    category_data: CategoryUpdate,
    session: Session = Depends(get_session)
):
    """
    Update an existing category.
    """
    category = CategoryService.update_category(category_id, category_data, session)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return CategoryResponse.model_validate(category)


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    session: Session = Depends(get_session)
):
    """
    Delete a category by ID.
    """
    success = CategoryService.delete_category(category_id, session)
    if not success:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"message": "Category deleted successfully"}


@router.get("/slugs/all", response_model=List[str])
def get_all_slugs(session: Session = Depends(get_session)):
    """
    Get all available category slugs for validation.
    """
    from ..models.category import CategorySlugManager
    return CategorySlugManager.get_all_slugs(session)


@router.get("/validate-slug/{slug}")
def validate_slug(slug: str, session: Session = Depends(get_session)):
    """
    Check if a slug is valid (exists in database).
    """
    from ..models.category import CategorySlugManager
    is_valid = CategorySlugManager.is_valid_slug(slug, session)
    return {
        "slug": slug,
        "is_valid": is_valid,
        "message": f"Slug '{slug}' {'exists' if is_valid else 'does not exist'} in database"
    }
