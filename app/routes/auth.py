"""
app/routes/auth.py — Authentication endpoints.
Register, local login, social login (Google), refresh, logout, and /me.
"""
import os
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, SQLModel, select

from app.database import get_session
from app.models.user import (
    OAuthProvider, TokenResponse, User, UserLogin, UserRead, UserRegister, UserRole,
)
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

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


class GoogleSocialLoginRequest(SQLModel):
    id_token: str


def _slugify_username(value: str) -> str:
    candidate = re.sub(r"[^a-zA-Z0-9._]", "_", value).strip("._")
    if not candidate:
        candidate = "user"
    return candidate[:30]


def _ensure_unique_username(session: Session, base_username: str) -> str:
    base = _slugify_username(base_username)
    attempt = base
    idx = 1
    while session.exec(select(User).where(User.username == attempt)).one_or_none() is not None:
        suffix = f"_{idx}"
        attempt = f"{base[: max(1, 30 - len(suffix))]}{suffix}"
        idx += 1
    return attempt


def _issue_social_login(
    *,
    session: Session,
    provider: OAuthProvider,
    provider_user_id: str,
    email: str,
    display_name: Optional[str],
    email_verified: bool,
) -> TokenResponse:
    now = datetime.now(timezone.utc)
    email = email.strip().lower()

    user = session.exec(
        select(User).where(
            (User.oauth_provider == provider.value) & (User.oauth_id == provider_user_id)
        )
    ).one_or_none()

    if user is None:
        user = session.exec(select(User).where(User.email == email)).one_or_none()
        if user is not None:
            existing_provider = (user.oauth_provider or OAuthProvider.local.value)
            if existing_provider not in {OAuthProvider.local.value, provider.value}:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Email already linked to a different social provider. "
                        "Use the original provider to login."
                    ),
                )

            user.oauth_provider = provider.value
            user.oauth_id = provider_user_id
            if display_name and not user.display_name:
                user.display_name = display_name
        else:
            preferred_username = display_name or email.split("@", 1)[0] or f"{provider.value}_user"
            username = _ensure_unique_username(session, preferred_username)
            user = User(
                username=username,
                email=email,
                hashed_password=None,
                display_name=display_name,
                role=UserRole.user,
                credits=1,
                oauth_provider=provider.value,
                oauth_id=provider_user_id,
                is_verified=email_verified,
            )
            session.add(user)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    user.last_login_at = now
    if email_verified and not user.is_verified:
        user.is_verified = True

    session.add(user)
    session.commit()
    session.refresh(user)

    tokens = _issue_tokens(user)
    return TokenResponse(**tokens, user=_make_user_read(user))


def _verify_google_id_token(id_token: str) -> tuple[str, str, Optional[str], bool]:
    google_client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(GOOGLE_TOKENINFO_URL, params={"id_token": id_token})

    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")

    payload = resp.json()
    token_aud = (payload.get("aud") or "").strip()
    token_iss = (payload.get("iss") or "").strip()
    provider_user_id = payload.get("sub")
    email = (payload.get("email") or "").strip().lower()
    name = payload.get("name")
    email_verified = str(payload.get("email_verified", "false")).lower() == "true"

    if google_client_id and token_aud != google_client_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google token audience mismatch")

    if token_iss not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token issuer")

    if not provider_user_id or not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google token missing required claims")

    return provider_user_id, email, name, email_verified




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
# Social login (Google)
# ---------------------------------------------------------------------------
@router.post("/social/google", response_model=TokenResponse)
def social_login_google(body: GoogleSocialLoginRequest, session: Session = Depends(get_session)):
    provider_user_id, email, name, email_verified = _verify_google_id_token(body.id_token)
    return _issue_social_login(
        session=session,
        provider=OAuthProvider.google,
        provider_user_id=provider_user_id,
        email=email,
        display_name=name,
        email_verified=email_verified,
    )




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
