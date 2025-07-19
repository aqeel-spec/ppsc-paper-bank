from typing import Optional
from datetime import datetime

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import DateTime
from sqlalchemy.sql import func


class Websites(SQLModel, table=True):
    __tablename__ = "websites"

    id: Optional[int] = Field(default=None, primary_key=True)
    website_name: str = Field(description="Name of the website, e.g., 'PakMcqs', 'TestPoint'")
    base_url: str = Field(description="Base URL of the website, e.g., 'https://pakmcqs.com'")
    website_type: Optional[str] = Field(default=None, description="Type of website: 'pakmcqs', 'testpoint', etc.")
    description: Optional[str] = Field(default=None, description="Description of the website")
    is_active: bool = Field(default=True, description="Whether the website is active for scraping")
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
    website_name: str = Field(description="Name of the website")
    base_url: str = Field(description="Base URL of the website")
    website_type: Optional[str] = Field(default=None, description="Type of website")
    description: Optional[str] = Field(default=None, description="Description of the website")
    is_active: bool = Field(default=True, description="Whether the website is active")


class WebsitesUpdate(SQLModel):
    website_name: Optional[str] = Field(default=None, description="Updated website name")
    base_url: Optional[str] = Field(default=None, description="Updated base URL")
    website_type: Optional[str] = Field(default=None, description="Updated website type")
    description: Optional[str] = Field(default=None, description="Updated description")
    is_active: Optional[bool] = Field(default=None, description="Updated active status")


class WebsitesRead(SQLModel):
    id: int
    website_name: str
    base_url: str
    website_type: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
