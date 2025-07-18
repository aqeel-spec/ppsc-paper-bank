"""
Models package for PPSC Paper Bank application.
"""

from .base import TimestampMixin, BaseModel
from .category import (
    Category, 
    CategoryCreate, 
    CategoryUpdate, 
    CategoryResponse,
    CategoryWithMCQs,
    CategoryService,
    CategorySlugManager,
    create_slug
)
from .mcqs_bank import (
    MCQ, MCQBase, MCQCreate, MCQUpdate, MCQBulkCreate, MCQRead, AnswerOption
)
from .paper import PaperModel, PaperMCQ, PaperCreate, PaperUpdate, PaperResponse
from .website import Website, WebsiteCreate, WebsiteUpdate, WebsiteRead
from .websites import Websites, WebsitesCreate, WebsitesUpdate, WebsitesRead
from .top_bar import TopBar, TopBarCreate, TopBarUpdate, TopBarRead
from .side_bar import SideBar, SideBarCreate, SideBarUpdate, SideBarRead

__all__ = [
    # Base models
    "TimestampMixin",
    "BaseModel",
    
    # Enums
    "AnswerOption",
    
    # Category models
    "Category",
    "CategoryCreate",
    "CategoryUpdate", 
    "CategoryResponse",
    "CategoryWithMCQs",
    "CategoryService",
    "CategorySlugManager",
    "create_slug",
    
    # MCQ models
    "MCQ",
    "MCQBase", 
    "MCQCreate",
    "MCQUpdate",
    "MCQBulkCreate",
    "MCQRead",
    
    # Paper models
    "PaperModel",
    "PaperMCQ", 
    "PaperCreate",
    "PaperUpdate",
    "PaperResponse",
    
    # Website models
    "Website",
    "WebsiteCreate",
    "WebsiteUpdate",
    "WebsiteRead",
    
    # Websites models
    "Websites",
    "WebsitesCreate", 
    "WebsitesUpdate",
    "WebsitesRead",
    
    # Navigation models
    "TopBar",
    "TopBarCreate",
    "TopBarUpdate",
    "TopBarRead",
    "SideBar", 
    "SideBarCreate",
    "SideBarUpdate",
    "SideBarRead",
]
