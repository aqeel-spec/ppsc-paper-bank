from typing import Optional, List
from datetime import datetime

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import DateTime, JSON
from sqlalchemy.sql import func


class Websites(SQLModel, table=True):
    __tablename__ = "websites"

    id: Optional[int] = Field(default=None, primary_key=True)
    websites_urls: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    website_names: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    current_page_url: Optional[str] = None
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


class WebsitesCreate(SQLModel):
    websites_urls: Optional[List[str]] = None
    website_names: Optional[List[str]] = None
    current_page_url: Optional[str] = None


class WebsitesUpdate(SQLModel):
    websites_urls: Optional[List[str]] = None
    website_names: Optional[List[str]] = None
    current_page_url: Optional[str] = None


class WebsitesRead(SQLModel):
    id: int
    websites_urls: Optional[List[str]] = None
    website_names: Optional[List[str]] = None
    current_page_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
