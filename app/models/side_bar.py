from typing import Optional
from datetime import datetime

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import DateTime
from sqlalchemy.sql import func


class SideBar(SQLModel, table=True):
    __tablename__ = "side_bar"

    id: Optional[int] = Field(default=None, primary_key=True)
    section_title: Optional[str] = None  # Section title (e.g., "MCQs Categories")
    name: Optional[str] = None           # Single name field
    url: Optional[str] = None            # Single URL field
    website_id: Optional[int] = None     # Reference to websites table
    is_already_exists: bool = Field(default=False)


class SideBarCreate(SQLModel):
    section_title: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    website_id: Optional[int] = None
    is_already_exists: bool = False


class SideBarUpdate(SQLModel):
    section_title: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    website_id: Optional[int] = None
    is_already_exists: Optional[bool] = None


class SideBarRead(SQLModel):
    id: int
    section_title: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    website_id: Optional[int] = None
    is_already_exists: bool
