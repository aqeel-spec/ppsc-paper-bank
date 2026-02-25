"""
app/routes/auth.py — Authentication endpoints.
Register, login (username or email), refresh, logout, and /me.
"""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.database import get_session
from app.models.user import (
    TokenResponse, User, UserLogin, UserRead, UserRegister, UserRole, UserSession,
)
from app.security import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        city=user.city,
        bio=user.bio,
        role=user.role,
        is_active=user.is_active,
        credits=user.credits,
        created_at=user.created_at,
    )


def _issue_tokens(user: User) -> dict:
    access_token = create_access_token({"sub": user.id})
    refresh_token = create_refresh_token({"sub": user.id})
    return {"access_token": access_token, "refresh_token": refresh_token}


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------
@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: UserRegister, session: Session = Depends(get_session)):
    from app.security import ADMIN_USERNAME, ADMIN_PASSWORD
    # Check uniqueness
    existing_user = session.exec(
        select(User).where((User.username == body.username) | (User.email == body.email))
    ).one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    # Auto-promote to admin if username + password match the env-defined admin credentials
    # Use plain string comparison (NOT re-hashing) to avoid bcrypt random-salt trap
    is_admin = (
        body.username.strip() == ADMIN_USERNAME
        and body.password == ADMIN_PASSWORD
    )

    user = User(
        username=body.username.strip(),
        email=body.email.strip().lower(),
        hashed_password=hash_password(body.password),
        display_name=body.display_name,
        role=UserRole.admin if is_admin else UserRole.user,
        credits=999 if is_admin else 1,  # admins get unlimited effectively
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    tokens = _issue_tokens(user)
    return TokenResponse(**tokens, user=_make_user_read(user))


# ---------------------------------------------------------------------------
# Login (username OR email)
# ---------------------------------------------------------------------------
@router.post("/login", response_model=TokenResponse)
def login(body: UserLogin, session: Session = Depends(get_session)):
    # Find by username or email
    user = session.exec(
        select(User).where(
            (User.username == body.username) | (User.email == body.username.lower())
        )
    ).one_or_none()

    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()

    tokens = _issue_tokens(user)
    return TokenResponse(**tokens, user=_make_user_read(user))


# ---------------------------------------------------------------------------
# OAuth2 form-compatible login (for swagger /docs)
# ---------------------------------------------------------------------------
@router.post("/login/form", response_model=TokenResponse, include_in_schema=False)
def login_form(form: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    """Compatible with OAuth2PasswordBearer for Swagger UI."""
    return login(UserLogin(username=form.username, password=form.password), session=session)


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------
@router.post("/refresh", response_model=TokenResponse)
def refresh_token(refresh_token_str: str, session: Session = Depends(get_session)):
    from jose import JWTError
    try:
        payload = decode_token(refresh_token_str)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = session.exec(select(User).where(User.id == user_id)).one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    tokens = _issue_tokens(user)
    return TokenResponse(**tokens, user=_make_user_read(user))


# ---------------------------------------------------------------------------
# Get current user
# ---------------------------------------------------------------------------
@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return _make_user_read(current_user)


# ---------------------------------------------------------------------------
# Logout (invalidate session by token hash — optional, for strict revocation)
# ---------------------------------------------------------------------------
@router.post("/logout", status_code=200)
def logout(current_user: User = Depends(get_current_user)):
    # JWT is stateless, so logout is simply a client-side affair.
    # This endpoint exists for completeness and future refresh-token revocation.
    return {"detail": "Logged out successfully"}
