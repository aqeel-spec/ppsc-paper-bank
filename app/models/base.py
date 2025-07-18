from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import DateTime
from sqlalchemy.sql import func


class TimestampMixin(SQLModel):
    """Mixin for timestamp fields"""
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


class BaseModel(TimestampMixin, table=False):
    """Base model with common fields"""
    id: Optional[int] = Field(default=None, primary_key=True)
