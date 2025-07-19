from typing import Optional
from datetime import datetime

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import DateTime
from sqlalchemy.sql import func


class TopBar(SQLModel, table=True):
    __tablename__ = "top_bar"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: Optional[str] = None
    name: Optional[str] = None  # Single name field
    url: Optional[str] = None   # Single URL field
    website_id: Optional[int] = None  # Reference to websites table


class TopBarCreate(SQLModel):
    title: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    website_id: Optional[int] = None


class TopBarUpdate(SQLModel):
    title: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    website_id: Optional[int] = None


class TopBarRead(SQLModel):
    id: int
    title: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    website_id: Optional[int] = None
