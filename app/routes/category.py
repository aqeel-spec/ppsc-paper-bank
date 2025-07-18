"""
Category API Routes
Handles CRUD operations for dynamic categories.
"""
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session

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


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category_by_id(
    category_id: int,
    session: Session = Depends(get_session)
):
    """
    Get a category by ID.
    """
    category = CategoryService.get_category_by_id(category_id, session)
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


@router.get("/{category_id}/with-mcqs", response_model=CategoryWithMCQs)
def get_category_with_mcqs(
    category_id: int,
    session: Session = Depends(get_session)
):
    """
    Get a category with all its MCQs.
    """
    category = CategoryService.get_category_by_id(category_id, session)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Load the relationship
    return CategoryWithMCQs.model_validate(category)


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
