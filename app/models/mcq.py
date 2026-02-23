"""
Legacy compatibility module for MCQ models.
This file is kept for backward compatibility. Please use the specific model files instead.
"""

# Import all models from the new modular structure
from .category import (
    Category, 
    CategoryCreate, 
    CategoryUpdate, 
    CategoryResponse,
    CategoryService,
    CategoryDetailResponse,
    CategorySlugManager,
    create_slug
)
from .mcqs_bank import (
    MCQ, MCQBase, MCQCreate, MCQUpdate, MCQBulkCreate, MCQRead, AnswerOption
)
from .paper import PaperModel, PaperMCQ, PaperCreate, PaperUpdate, PaperResponse

# For backward compatibility, expose all the classes that were previously in this file
__all__ = [
    # Enums
    "AnswerOption",
    
    # Category models
    "Category",
    "CategoryCreate",
    "CategoryUpdate", 
    "CategoryResponse",
    "CategoryService",
    "CategoryDetailResponse",
    "CategorySlugManager",
    "create_slug",
    "CategoryRead",
    
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
]

