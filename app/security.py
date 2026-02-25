"""
app/security.py — JWT, password hashing, and auth dependencies.
"""
import os
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlmodel import Session, select

from app.database import get_session

# ---------------------------------------------------------------------------
# Configuration (read from environment)
# ---------------------------------------------------------------------------
SECRET_KEY: str = os.getenv("SECRET_KEY", "changeme-use-a-real-random-secret-in-prod")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

# Admin credentials (stored in .env, never in DB for safety)
ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin1234")  # Change in .env!

# ---------------------------------------------------------------------------
# Password hashing — using bcrypt directly (passlib 1.7.4 breaks with bcrypt>=4.0)
# Pre-hash with SHA-256 to bypass bcrypt's 72-byte password limit safely.
# ---------------------------------------------------------------------------
def _prehash(plain: str) -> bytes:
    """SHA-256 prehash to 64 hex chars, safe within bcrypt 72-byte limit."""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(plain: str) -> str:
    hashed = bcrypt.hashpw(_prehash(plain), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    to_encode["type"] = "access"
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode["exp"] = expire
    to_encode["type"] = "refresh"
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises JWTError on failure."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# ---------------------------------------------------------------------------
# FastAPI auth dependencies
# ---------------------------------------------------------------------------
def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
):
    """Return the authenticated User or raise 401."""
    from app.models.user import User  # local import to avoid circular deps

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = session.exec(select(User).where(User.id == user_id)).one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
):
    """Return the current user or None (for optional-auth endpoints)."""
    if token is None:
        return None
    try:
        return get_current_user(token=token, session=session)
    except HTTPException:
        return None


def require_admin(current_user=Depends(get_current_user)):
    """Raise 403 if current user is not admin."""
    from app.models.user import UserRole
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
