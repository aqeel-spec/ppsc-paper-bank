from typing import Optional, List
from datetime import datetime

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import DateTime, JSON
from sqlalchemy.sql import func


class SideBar(SQLModel, table=True):
    __tablename__ = "side_bar"

    id: Optional[int] = Field(default=None, primary_key=True)
    tile: Optional[str] = None
    names: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    urls: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    is_already_exists: bool = Field(default=False)


class SideBarCreate(SQLModel):
    tile: Optional[str] = None
    names: Optional[List[str]] = None
    urls: Optional[List[str]] = None
    is_already_exists: bool = False


class SideBarUpdate(SQLModel):
    tile: Optional[str] = None
    names: Optional[List[str]] = None
    urls: Optional[List[str]] = None
    is_already_exists: Optional[bool] = None


class SideBarRead(SQLModel):
    id: int
    tile: Optional[str] = None
    names: Optional[List[str]] = None
    urls: Optional[List[str]] = None
    is_already_exists: bool
