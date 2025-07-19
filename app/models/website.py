from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import DateTime, JSON
from sqlalchemy.sql import func


class Website(SQLModel, table=True):
    __tablename__ = "website"

    web_id: Optional[int] = Field(default=None, primary_key=True)
    is_top_bar: bool = Field(default=False)
    is_paper_exit: bool = Field(default=False)
    is_side_bar: bool = Field(default=False)
    website_name: Optional[int] = None
    paper_urls: Optional[List[Dict[str, Any]]] = Field(default=None, sa_column=Column(JSON))
    pages_count: Optional[int] = None
    current_page_url: Optional[str] = None
    last_scrapped_url: Optional[int] = None
    is_last_completed: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime,
            server_default=func.now(),
            nullable=False
        )
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime,
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False
        )
    )
    ul_config: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    current_page: Optional[int] = None
    total_pages: Optional[int] = None


class WebsiteCreate(SQLModel):
    is_top_bar: bool = False
    is_paper_exit: bool = False
    is_side_bar: bool = False
    website_name: Optional[int] = None
    paper_urls: Optional[List[Dict[str, Any]]] = None
    pages_count: Optional[int] = None
    current_page_url: Optional[str] = None
    last_scrapped_url: Optional[int] = None
    is_last_completed: bool = False
    ul_config: Optional[dict] = None
    current_page: Optional[int] = None
    total_pages: Optional[int] = None


class WebsiteUpdate(SQLModel):
    is_top_bar: Optional[bool] = None
    is_paper_exit: Optional[bool] = None
    is_side_bar: Optional[bool] = None
    website_name: Optional[int] = None
    paper_urls: Optional[List[Dict[str, Any]]] = None
    pages_count: Optional[int] = None
    current_page_url: Optional[str] = None
    last_scrapped_url: Optional[int] = None
    is_last_completed: Optional[bool] = None
    ul_config: Optional[dict] = None
    current_page: Optional[int] = None
    total_pages: Optional[int] = None


class WebsiteRead(SQLModel):
    web_id: int
    is_top_bar: bool
    is_paper_exit: bool
    is_side_bar: bool
    website_name: Optional[int] = None
    paper_urls: Optional[List[Dict[str, Any]]] = None
    pages_count: Optional[int] = None
    current_page_url: Optional[str] = None
    last_scrapped_url: Optional[int] = None
    is_last_completed: bool
    created_at: datetime
    updated_at: datetime
    ul_config: Optional[dict] = None
    current_page: Optional[int] = None
    total_pages: Optional[int] = None
