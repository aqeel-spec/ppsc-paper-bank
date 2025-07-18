from typing import Optional, List
from datetime import datetime

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import DateTime, JSON
from sqlalchemy.sql import func


class TopBar(SQLModel, table=True):
    __tablename__ = "top_bar"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: Optional[str] = None
    names: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    urls: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))


class TopBarCreate(SQLModel):
    title: Optional[str] = None
    names: Optional[List[str]] = None
    urls: Optional[List[str]] = None


class TopBarUpdate(SQLModel):
    title: Optional[str] = None
    names: Optional[List[str]] = None
    urls: Optional[List[str]] = None


class TopBarRead(SQLModel):
    id: int
    title: Optional[str] = None
    names: Optional[List[str]] = None
    urls: Optional[List[str]] = None
