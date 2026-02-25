"""
app/models/user.py — User account, session, and OAuth models.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class UserRole(str, Enum):
    admin = "admin"
    user = "user"


class OAuthProvider(str, Enum):
    local = "local"
    google = "google"
    github = "github"


# ---------------------------------------------------------------------------
# User — main account record
# ---------------------------------------------------------------------------
class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(String(36), primary_key=True, default=lambda: str(uuid4())),
    )
    username: str = Field(sa_column=Column(String(80), unique=True, nullable=False, index=True))
    email: str = Field(sa_column=Column(String(255), unique=True, nullable=False, index=True))
    hashed_password: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))

    # Profile
    display_name: Optional[str] = Field(default=None, sa_column=Column(String(120)))
    city: Optional[str] = Field(default=None, sa_column=Column(String(80)))
    bio: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Role & status
    role: str = Field(default=UserRole.user, sa_column=Column(String(20), default="user", nullable=False))
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)

    # Credits (for mock sessions)
    credits: int = Field(default=1)

    # OAuth support (nullable for local-only accounts)
    oauth_provider: Optional[str] = Field(default=OAuthProvider.local, sa_column=Column(String(20)))
    oauth_id: Optional[str] = Field(default=None, sa_column=Column(String(255)))

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: Optional[datetime] = Field(default=None)


# ---------------------------------------------------------------------------
# UserSession — refresh token tracking / session invalidation
# ---------------------------------------------------------------------------
class UserSession(SQLModel, table=True):
    __tablename__ = "user_sessions"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(String(36), primary_key=True),
    )
    user_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    token_hash: str = Field(sa_column=Column(String(255), nullable=False, unique=True))
    ip_address: Optional[str] = Field(default=None, sa_column=Column(String(45)))
    user_agent: Optional[str] = Field(default=None, sa_column=Column(String(512)))
    expires_at: datetime = Field()
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revoked: bool = Field(default=False)


# ---------------------------------------------------------------------------
# Pydantic schemas (request/response)
# ---------------------------------------------------------------------------
class UserRegister(SQLModel):
    username: str
    email: str
    password: str
    display_name: Optional[str] = None
    city: Optional[str] = None


class UserLogin(SQLModel):
    """Accepts username OR email in the `username` field."""
    username: str   # can be a username or email address
    password: str


class UserRead(SQLModel):
    id: str
    username: str
    email: str
    display_name: Optional[str]
    city: Optional[str]
    bio: Optional[str]
    role: str
    is_active: bool
    credits: int
    created_at: datetime


class UserUpdate(SQLModel):
    display_name: Optional[str] = None
    city: Optional[str] = None
    bio: Optional[str] = None


class TokenResponse(SQLModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead
