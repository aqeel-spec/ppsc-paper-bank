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
    CategoryService,
    CategoryDetailResponse,
    PaginatedResponse
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


@router.get("/", response_model=PaginatedResponse[CategoryDetailResponse] | PaginatedResponse[CategoryResponse])
def get_all_categories(
    include_subcategories: bool = Query(default=False, description="Include nested subcategories"),
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=10, ge=1, le=100, description="Items per page"),
    session: Session = Depends(get_session)
):
    """
    Get all categories. By default, returns root categories. 
    Use `include_subcategories=True` to also return children hierarchically.
    """
    categories = CategoryService.get_all_categories(session)
    
    if not include_subcategories:
        # Return only the flat root categories without subcategories lists
        # Now that every category starts with "subjectwise/", root nodes are the ones with exactly 1 slash in slug
        root_categories = [cat for cat in categories if cat.slug.count("/") == 1]
        total_items = len(root_categories)
        total_pages = (total_items + limit - 1) // limit if total_items > 0 else 1
        offset = (page - 1) * limit
        paginated_data = root_categories[offset:offset + limit]

        return PaginatedResponse(
            message="success",
            data=[CategoryResponse.model_validate(cat) for cat in paginated_data],
            page=page,
            limit=limit,
            total_pages=total_pages,
            total_items=total_items,
            has_next=page < total_pages,
            has_previous=page > 1
        )

    # Hierarchical map
    root_categories_map = {}
    
    # First pass: map all root categories (exactly 1 slash in slug, typically subjectwise/category-name)
    for cat in categories:
        if cat.slug.count("/") == 1:
            root_categories_map[cat.slug] = CategoryDetailResponse.model_validate(cat)
            root_categories_map[cat.slug].subcategories = []
            
    # Second pass: attach subcategories to their roots
    for cat in categories:
        if cat.slug.count("/") > 1:
            # We want to group by "subjectwise/category-name", which is the first TWO segments
            parts = cat.slug.split("/")
            root_slug = f"{parts[0]}/{parts[1]}"
            if root_slug in root_categories_map:
                sub_cat = CategoryDetailResponse.model_validate(cat)
                sub_cat.subcategories = None
                sub_cat.mcqs = None  # Ensure MCQs are explicitly excluded in hierarchy
                root_categories_map[root_slug].subcategories.append(sub_cat)
            else:
                # If root doesn't exist for some reason, just treat it as a root
                root_categories_map[cat.slug] = CategoryDetailResponse.model_validate(cat)
                root_categories_map[cat.slug].mcqs = None
                
    root_list = list(root_categories_map.values())
    
    total_items = len(root_list)
    total_pages = (total_items + limit - 1) // limit if total_items > 0 else 1
    
    offset = (page - 1) * limit
    paginated_data = root_list[offset:offset + limit]
    
    has_next = page < total_pages
    has_previous = page > 1
    
    return PaginatedResponse(
        message="success",
        data=paginated_data,
        page=page,
        limit=limit,
        total_pages=total_pages,
        total_items=total_items,
        has_next=has_next,
        has_previous=has_previous
    )


@router.get("/{slug:path}/subcategories", response_model=PaginatedResponse[CategoryResponse], response_model_exclude_none=True)
def get_subcategories(
    slug: str,
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=10, ge=1, le=100, description="Items per page"),
    session: Session = Depends(get_session)
):
    """
    Get all subcategories for a given root category slug, with pagination.
    Avoids injecting empty 'subcategories' arrays into the output payload.
    """
    category = CategoryService.get_category_by_slug(slug, session)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
        
    # Subcategories of this parent will begin with the parent's generated path plus one more slash.
    # We want direct subcategories, so they should have exactly one more slash than the parent.
    parent_slash_count = category.slug.count("/")
    prefix = f"{category.slug}/"
    statement = select(Category).where(
        Category.slug.startswith(prefix)
    )
    
    # Optional logic: if you only want DIRECT subcategories (not nested lower), filter in Python:
    all_children = session.exec(statement).all()
    subcategories = [c for c in all_children if c.slug.count("/") == parent_slash_count + 1]
    
    total_items = len(subcategories)
    total_pages = (total_items + limit - 1) // limit if total_items > 0 else 1
    
    offset = (page - 1) * limit
    paginated_data = [CategoryResponse.model_validate(sub) for sub in subcategories[offset:offset + limit]]
    
    has_next = page < total_pages
    has_previous = page > 1
    
    return PaginatedResponse(
        message="success",
        data=paginated_data,
        page=page,
        limit=limit,
        total_pages=total_pages,
        total_items=total_items,
        has_next=has_next,
        has_previous=has_previous
    )


@router.get("/slug/{slug:path}", response_model=CategoryResponse)
def get_category_by_slug(
    slug: str,
    session: Session = Depends(get_session)
):
    """
    Get a simple category by slug without hierarchy metadata.
    """
    category = CategoryService.get_category_by_slug(slug, session)
    if not category:
        raise HTTPException(status_code=404, detail=f"Category with slug '{slug}' not found")
    return CategoryResponse.model_validate(category)


@router.get("/{slug:path}/with-mcqs/{mcq_id}")
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


@router.get("/{slug:path}/with-mcqs", response_model=PaginatedResponse[CategoryDetailResponse], response_model_exclude_none=True)
def get_category_with_mcqs(
    slug: str,
    explanation: bool = False,
    with_mcq: bool = True,
    include_subcategories: bool = Query(default=True, description="Include MCQs from nested subcategories"),
    limit: int = Query(default=10, ge=1, le=100, description="Number of MCQs to return"),
    offset: int = Query(default=0, ge=0, description="Number of MCQs to skip"),
    session: Session = Depends(get_session)
):
    """
    Get a category with its MCQs, with optional filtering and pagination.
    
    Query Parameters:
    - explanation: If True, include/focus on explanations
    - with_mcq: If False with explanation=True, return only ID and explanation for each MCQ
    - include_subcategories: If True (default), include MCQs from all nested subcategories recursively.
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
    from urllib.parse import unquote
    from ..models.mcq import MCQ
    
    # The client might send doubly-encoded slashes (%252F instead of /)
    # Ensure the slug is fully decoded.
    decoded_slug = unquote(unquote(slug))
    
    # Get category first
    category = session.exec(select(Category).where(Category.slug == decoded_slug)).first()
    
    if not category:
        raise HTTPException(status_code=404, detail=f"Category '{decoded_slug}' not found")
        
    if include_subcategories:
        # Get all category IDs for this category and its sub-categories
        prefix_slug = f"{decoded_slug}/"
        category_ids = session.exec(
            select(Category.id).where(
                (Category.slug == decoded_slug) | (Category.slug.startswith(prefix_slug))
            )
        ).all()
    else:
        # Only the exact category requested
        category_ids = [category.id]

    
    # Get total count of MCQs in this category and all sub-categories
    total_mcqs = session.exec(
        select(func.count(MCQ.id)).where(MCQ.category_id.in_(category_ids))
    ).one()
    
    # Get paginated MCQs
    mcqs_query = (
        select(MCQ)
        .where(MCQ.category_id.in_(category_ids))
        .order_by(MCQ.id)
        .offset(offset)
        .limit(limit)
    )
    mcqs = session.exec(mcqs_query).all()
    
    total_pages = (total_mcqs + limit - 1) // limit if total_mcqs > 0 else 1
    page = (offset // limit) + 1 if limit > 0 else 1
    
    # Fetch subcategories if requested
    subcategories_list = None
    if include_subcategories:
        parent_slash_count = category.slug.count("/")
        all_children = session.exec(
            select(Category).where(Category.slug.startswith(f"{category.slug}/"))
        ).all()
        direct_subs = [c for c in all_children if c.slug.count("/") == parent_slash_count + 1]
        subcategories_list = [CategoryDetailResponse.model_validate(sub) for sub in direct_subs]
        for sub in subcategories_list:
            sub.subcategories = None
            sub.mcqs = None

    # Build response based on parameters
    if explanation and not with_mcq:
        # Return only IDs and explanations for each MCQ
        mcqs_minimal = [
            {"id": mcq.id, "explanation": mcq.explanation}
            for mcq in mcqs
        ]
        
        root_val = CategoryDetailResponse.model_validate(category)
        root_val.id = category.id
        # Sanitize name
        raw_name = category.name.split("/")[-1]
        root_val.name = raw_name.replace("-", " ").replace(" Mcqs", " MCQs").title().replace(" Mcqs", " MCQs")

        root_val.slug = category.slug
        root_val.mcqs = mcqs_minimal
        root_val.subcategories = subcategories_list
    else:
        # Return full category with paginated MCQ details (default)
        root_val = CategoryDetailResponse.model_validate(category)
        root_val.id = category.id
        
        # Sanitize name
        raw_name = category.name.split("/")[-1]
        root_val.name = raw_name.replace("-", " ").replace(" Mcqs", " MCQs").title().replace(" Mcqs", " MCQs")
        
        root_val.slug = category.slug
        root_val.mcqs = [mcq.model_dump() for mcq in mcqs]
        root_val.subcategories = subcategories_list
        
    return PaginatedResponse(
        message="success",
        data=[root_val],
        page=page,
        limit=limit,
        total_pages=total_pages,
        total_items=total_mcqs,
        has_next=page < total_pages,
        has_previous=page > 1
    )


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


@router.get("/validate-slug/{slug:path}")
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


@router.get("/{slug:path}", response_model=PaginatedResponse[CategoryDetailResponse], response_model_exclude_none=True)
def get_category_by_id(
    slug: str,
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=10, ge=1, le=100, description="Items per page"),
    session: Session = Depends(get_session)
):
    """
    Get a category by ID (slug), including its hierarchical paginated subcategories by default.
    If the category has no subcategories (i.e. it is a leaf node), it will instead return
    the actual paginated MCQs belonging to this category.
    """
    category = CategoryService.get_category_by_slug(slug, session)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
        
    # Get all direct subcategories for this exact parent
    parent_slash_count = category.slug.count("/")
    prefix = f"{category.slug}/"
    statement = select(Category).where(Category.slug.startswith(prefix))
    all_children = session.exec(statement).all()
    
    # Keep only direct children (exactly 1 deeper in the slash hierarchy)
    subcategories = [c for c in all_children if c.slug.count("/") == parent_slash_count + 1]
    
    # If this category has subcategories, return the hierarchy response
    if subcategories:
        total_items = len(subcategories)
        total_pages = (total_items + limit - 1) // limit if total_items > 0 else 1
        
        offset = (page - 1) * limit
        paginated_subs = [CategoryDetailResponse.model_validate(sub) for sub in subcategories[offset:offset + limit]]
        
        # Strip nested arrays from these subcategories so the tree doesn't recurse infinitely
        for sub in paginated_subs:
            sub.subcategories = None
            sub.mcqs = None
            
        root_val = CategoryDetailResponse.model_validate(category)
        root_val.subcategories = paginated_subs
        # Explicitly strip MCQs from the root category since we are paginating subcategories here
        root_val.mcqs = None

        return PaginatedResponse(
            message="success",
            data=[root_val],
            page=page,
            limit=limit,
            total_pages=total_pages,
            total_items=total_items,
            has_next=page < total_pages,
            has_previous=page > 1
        )
    
    # If no subcategories exist, fetch paginated MCQs for this category instead
    from ..models.mcq import MCQ
    
    total_mcqs = session.exec(
        select(func.count(MCQ.id)).where(MCQ.category_id == category.id)
    ).one()
    
    offset = (page - 1) * limit
    mcqs_query = (
        select(MCQ)
        .where(MCQ.category_id == category.id)
        .order_by(MCQ.id)
        .offset(offset)
        .limit(limit)
    )
    mcqs = session.exec(mcqs_query).all()
    
    total_pages = (total_mcqs + limit - 1) // limit if total_mcqs > 0 else 1
    
    root_val = CategoryDetailResponse.model_validate(category)
    root_val.mcqs = [mcq.model_dump() for mcq in mcqs]

    return PaginatedResponse(
        message="success",
        data=[root_val],
        page=page,
        limit=limit,
        total_pages=total_pages,
        total_items=total_mcqs,
        has_next=page < total_pages,
        has_previous=page > 1
    )
