from typing import Optional, TYPE_CHECKING, Dict, List
from datetime import datetime
import re

from sqlmodel import SQLModel, Field, Relationship, Column, Session, select
from sqlalchemy import DateTime
from sqlalchemy.sql import func

if TYPE_CHECKING:
    from .mcqs_bank import MCQ


def create_slug(name: str) -> str:
    """
    Create a URL-friendly slug from a category name.
    
    Examples:
        "PPSC All MCQs 2025" -> "ppsc_all_mcqs_2025"
        "Urdu Language" -> "urdu_language"
        "Computer Science" -> "computer_science"
    """
    # Convert to lowercase
    slug = name.lower()
    # Replace spaces and special characters with underscores
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '_', slug)
    # Remove leading/trailing underscores
    slug = slug.strip('_')
    return slug


class CategorySlugManager:
    """
    Dynamic category slug manager that generates slugs from database categories.
    """
    
    @staticmethod
    def get_all_slugs(session: Session) -> Dict[str, str]:
        """
        Get all category slugs from database.
        Returns dict of {slug: name}
        """
        statement = select(Category)
        categories = session.exec(statement).all()
        return {cat.slug: cat.name for cat in categories}
    
    @staticmethod
    def get_slug_choices(session: Session) -> List[str]:
        """
        Get list of all available category slugs.
        """
        statement = select(Category.slug)
        slugs = session.exec(statement).all()
        return list(slugs)
    
    @staticmethod
    def is_valid_slug(slug: str, session: Session) -> bool:
        """
        Check if a slug exists in the database.
        """
        statement = select(Category).where(Category.slug == slug)
        category = session.exec(statement).first()
        return category is not None
    
    @staticmethod
    def get_category_by_slug(slug: str, session: Session) -> Optional["Category"]:
        """
        Get category by its slug.
        """
        statement = select(Category).where(Category.slug == slug)
        return session.exec(statement).first()


class Category(SQLModel, table=True):
    __tablename__ = "category"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(
        index=True,
        unique=True,
        description="machine‐safe key, e.g. 'ppsc_all_mcqs_2025'"
    )
    name: str = Field(
        description="human‐readable, e.g. 'PPSC All MCQs 2025'"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime,
            server_default=func.now(),
            nullable=False
        ),
        description="when this category was first created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime,
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False
        ),
        description="last time this category record was modified"
    )

    # Relationship with MCQs
    mcqs: list["MCQ"] = Relationship(back_populates="category")

    @classmethod
    def create_with_auto_slug(cls, name: str, session: Session) -> "Category":
        """
        Create a category with automatically generated slug.
        """
        slug = create_slug(name)
        
        # Ensure slug is unique
        base_slug = slug
        counter = 1
        while cls.slug_exists(slug, session):
            slug = f"{base_slug}_{counter}"
            counter += 1
        
        category = cls(name=name, slug=slug)
        session.add(category)
        session.commit()
        session.refresh(category)
        return category
    
    @staticmethod
    def slug_exists(slug: str, session: Session) -> bool:
        """
        Check if slug already exists in database.
        """
        statement = select(Category).where(Category.slug == slug)
        return session.exec(statement).first() is not None


class CategoryCreate(SQLModel):
    name: str = Field(description="human‐readable, e.g. 'PPSC All MCQs 2025'")
    slug: Optional[str] = Field(
        default=None, 
        description="machine‐safe key (auto-generated if not provided)"
    )
    
    def get_or_create_slug(self) -> str:
        """
        Get the provided slug or generate one from the name.
        """
        if self.slug:
            return self.slug
        return create_slug(self.name)


class CategoryUpdate(SQLModel):
    name: Optional[str] = Field(default=None, description="Updated name")
    slug: Optional[str] = Field(default=None, description="Updated slug")


class CategoryResponse(SQLModel):
    id: Optional[int] = None
    name: str
    slug: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class CategoryWithMCQs(CategoryResponse):
    mcqs: list = []  # Will be populated with MCQ objects

    class Config:
        from_attributes = True


# CRUD operations
class CategoryService:
    @staticmethod
    def create_category(category_data: CategoryCreate, session: Session) -> Category:
        """
        Create a new category with auto-generated slug if not provided.
        """
        slug = category_data.get_or_create_slug()
        
        # Ensure slug is unique
        base_slug = slug
        counter = 1
        while Category.slug_exists(slug, session):
            slug = f"{base_slug}_{counter}"
            counter += 1
        
        category = Category(name=category_data.name, slug=slug)
        session.add(category)
        session.commit()
        session.refresh(category)
        return category
    
    @staticmethod
    def get_category_by_id(category_id: int, session: Session) -> Optional[Category]:
        """
        Get category by ID.
        """
        return session.get(Category, category_id)
    
    @staticmethod
    def get_category_by_slug(slug: str, session: Session) -> Optional[Category]:
        """
        Get category by slug.
        """
        statement = select(Category).where(Category.slug == slug)
        return session.exec(statement).first()
    
    @staticmethod
    def get_all_categories(session: Session) -> list[Category]:
        """
        Get all categories.
        """
        statement = select(Category)
        return list(session.exec(statement).all())
    
    @staticmethod
    def update_category(
        category_id: int, 
        category_data: CategoryUpdate, 
        session: Session
    ) -> Optional[Category]:
        """
        Update an existing category.
        """
        category = session.get(Category, category_id)
        if not category:
            return None
        
        update_data = category_data.model_dump(exclude_unset=True)
        
        # Handle slug update
        if "name" in update_data and "slug" not in update_data:
            # Auto-generate slug from new name
            update_data["slug"] = create_slug(update_data["name"])
        
        # Ensure new slug is unique
        if "slug" in update_data:
            new_slug = update_data["slug"]
            base_slug = new_slug
            counter = 1
            while (Category.slug_exists(new_slug, session) and 
                   new_slug != category.slug):
                new_slug = f"{base_slug}_{counter}"
                counter += 1
            update_data["slug"] = new_slug
        
        for field, value in update_data.items():
            setattr(category, field, value)
        
        session.add(category)
        session.commit()
        session.refresh(category)
        return category
    
    @staticmethod
    def delete_category(category_id: int, session: Session) -> bool:
        """
        Delete a category by ID.
        Returns True if successful, False if category not found.
        """
        category = session.get(Category, category_id)
        if not category:
            return False
        
        session.delete(category)
        session.commit()
        return True
