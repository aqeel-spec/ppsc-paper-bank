#!/usr/bin/env python3
"""
Scraping State Model for Resume Functionality

This model tracks the progress of scraping operations to allow for resuming
interrupted scraping sessions.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import String
import json


class ScrapingStatus(str, Enum):
    """Status of scraping operation"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class ScrapingState(SQLModel, table=True):
    """Model to track scraping operation state for resume functionality"""
    
    __tablename__ = "scraping_states"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Basic info
    base_url: str = Field(
        max_length=2048,
        sa_column=Column(String(2048), index=True, nullable=False),
        description="Original URL being scraped",
    )
    paper_id: Optional[int] = Field(default=None, description="Associated paper ID")
    website_id: int = Field(description="Website ID from validation")
    
    # Status tracking
    status: ScrapingStatus = Field(default=ScrapingStatus.PENDING)
    
    # Progress tracking
    total_pages_discovered: int = Field(default=0, description="Total pages found during discovery")
    pages_processed: int = Field(default=0, description="Number of pages processed")
    current_page_index: int = Field(default=0, description="Current page being processed")
    
    # Page tracking
    discovered_pages: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    processed_pages: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    failed_pages: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    
    # MCQ tracking
    total_mcqs_found: int = Field(default=0)
    total_mcqs_saved: int = Field(default=0)
    new_mcqs_created: int = Field(default=0)
    
    # Metadata
    category_name: Optional[str] = Field(default=None)
    category_slug: Optional[str] = Field(default=None)
    paper_title: Optional[str] = Field(default=None)
    
    # Error tracking
    error_message: Optional[str] = Field(default=None)
    error_count: int = Field(default=0)
    last_error_at: Optional[datetime] = Field(default=None)
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(default=None)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    
    # Configuration
    max_pages_limit: Optional[int] = Field(default=None, description="User-specified page limit")
    resume_from_page: int = Field(default=0, description="Page index to resume from")
    
    # Additional metadata
    validation_source: Optional[str] = Field(default=None, description="Source table from validation")
    extra_data: Optional[Dict[str, Any]] = Field(default_factory=dict, sa_column=Column(JSON))
    
    def mark_as_started(self):
        """Mark scraping as started"""
        self.status = ScrapingStatus.IN_PROGRESS
        self.started_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
    
    def mark_as_completed(self):
        """Mark scraping as completed"""
        self.status = ScrapingStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
    
    def mark_as_failed(self, error_message: str):
        """Mark scraping as failed"""
        self.status = ScrapingStatus.FAILED
        self.error_message = error_message
        self.error_count += 1
        self.last_error_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
    
    def mark_as_paused(self):
        """Mark scraping as paused (for resume later)"""
        self.status = ScrapingStatus.PAUSED
        self.updated_at = datetime.now(timezone.utc)
    
    def add_discovered_page(self, page_url: str):
        """Add a newly discovered page"""
        if page_url not in self.discovered_pages:
            self.discovered_pages.append(page_url)
            self.total_pages_discovered = len(self.discovered_pages)
            self.updated_at = datetime.now(timezone.utc)
    
    def mark_page_as_processed(self, page_url: str, mcqs_found: int = 0, mcqs_saved: int = 0, new_mcqs: int = 0):
        """Mark a page as successfully processed"""
        if page_url not in self.processed_pages:
            self.processed_pages.append(page_url)
            self.pages_processed = len(self.processed_pages)
        
        self.total_mcqs_found += mcqs_found
        self.total_mcqs_saved += mcqs_saved
        self.new_mcqs_created += new_mcqs
        self.updated_at = datetime.now(timezone.utc)
    
    def mark_page_as_failed(self, page_url: str, error_message: str):
        """Mark a page as failed"""
        failure_info = {
            "url": page_url,
            "error": error_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "attempt_count": 1
        }
        
        # Check if this page already failed before
        existing_failure = None
        for i, failure in enumerate(self.failed_pages):
            if failure.get("url") == page_url:
                existing_failure = i
                break
        
        if existing_failure is not None:
            # Update existing failure
            self.failed_pages[existing_failure]["attempt_count"] += 1
            self.failed_pages[existing_failure]["error"] = error_message
            self.failed_pages[existing_failure]["timestamp"] = failure_info["timestamp"]
        else:
            # Add new failure
            self.failed_pages.append(failure_info)
        
        self.updated_at = datetime.now(timezone.utc)
    
    def get_next_page_to_process(self) -> Optional[str]:
        """Get the next page that needs to be processed"""
        if self.current_page_index < len(self.discovered_pages):
            return self.discovered_pages[self.current_page_index]
        return None
    
    def advance_to_next_page(self):
        """Move to the next page"""
        self.current_page_index += 1
        self.updated_at = datetime.now(timezone.utc)
    
    def get_progress_percentage(self) -> float:
        """Get progress as percentage"""
        if self.total_pages_discovered == 0:
            return 0.0
        return (self.pages_processed / self.total_pages_discovered) * 100
    
    def can_resume(self) -> bool:
        """Check if this scraping session can be resumed"""
        return self.status in [ScrapingStatus.PAUSED, ScrapingStatus.FAILED] and self.current_page_index < self.total_pages_discovered
    
    def get_resume_info(self) -> Dict[str, Any]:
        """Get information about resuming this session"""
        return {
            "can_resume": self.can_resume(),
            "progress_percentage": self.get_progress_percentage(),
            "pages_remaining": max(0, self.total_pages_discovered - self.pages_processed),
            "total_pages": self.total_pages_discovered,
            "processed_pages": self.pages_processed,
            "failed_pages": len(self.failed_pages),
            "mcqs_collected": self.total_mcqs_saved,
            "new_mcqs": self.new_mcqs_created
        }
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert to summary dictionary for display"""
        return {
            "id": self.id,
            "base_url": self.base_url,
            "status": self.status.value,
            "progress": f"{self.pages_processed}/{self.total_pages_discovered} pages",
            "progress_percentage": self.get_progress_percentage(),
            "mcqs_collected": self.total_mcqs_saved,
            "new_mcqs": self.new_mcqs_created,
            "paper_title": self.paper_title,
            "category": self.category_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "can_resume": self.can_resume()
        }
