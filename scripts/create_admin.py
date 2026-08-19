"""Create or promote an admin account.

Usage examples:
  python scripts/create_admin.py
  python scripts/create_admin.py --username Admin --password "strong-pass" --email admin@example.com
  python scripts/create_admin.py --force-reset-password
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path so `app` can be imported
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(_PROJECT_ROOT / ".env")
        load_dotenv()
    except Exception:
        pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or promote admin account")
    parser.add_argument("--username", default=os.getenv("ADMIN_USERNAME", "admin"), help="Admin username")
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD"), help="Admin password")
    parser.add_argument("--email", default=os.getenv("ADMIN_EMAIL"), help="Admin email")
    parser.add_argument("--display-name", default="Admin", help="Display name")
    parser.add_argument(
        "--force-reset-password",
        action="store_true",
        help="Reset password for an existing matching user",
    )
    return parser


def _create_or_promote_admin(
    *,
    username: str,
    password: str,
    email: str,
    display_name: str,
    force_reset_password: bool,
) -> int:
    from sqlmodel import Session, select

    from app.database import get_engine
    from app.models.user import User, UserRole
    from app.security import hash_password

    engine = get_engine()

    with Session(engine) as session:
        existing_by_username = session.exec(select(User).where(User.username == username)).one_or_none()
        existing_by_email = session.exec(select(User).where(User.email == email)).one_or_none()

        existing: Optional[User] = existing_by_username or existing_by_email

        if existing is not None:
            updated = False
            if existing.role != UserRole.admin:
                existing.role = UserRole.admin
                updated = True

            if force_reset_password:
                existing.hashed_password = hash_password(password)
                updated = True

            if existing.email != email:
                existing.email = email
                updated = True

            if existing.display_name != display_name:
                existing.display_name = display_name
                updated = True

            if existing.credits < 999:
                existing.credits = 999
                updated = True

            if not existing.is_active:
                existing.is_active = True
                updated = True

            if updated:
                session.add(existing)
                session.commit()
                print(f"Updated existing user '{existing.username}' as admin (id={existing.id}).")
            else:
                print(f"Admin user '{existing.username}' already up-to-date (id={existing.id}).")
            return 0

        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            display_name=display_name,
            role=UserRole.admin,
            credits=999,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        print(f"Created admin user '{user.username}' (id={user.id}).")
        return 0


def main() -> int:
    _load_env()
    parser = _build_parser()
    args = parser.parse_args()

    username = (args.username or "").strip()
    password = (args.password or "").strip()
    email = (args.email or f"{username}@admin.local").strip().lower()
    display_name = (args.display_name or "Admin").strip()

    if not username:
        print("Error: username is required.", file=sys.stderr)
        return 2
    if not password:
        print("Error: password is required. Set ADMIN_PASSWORD or pass --password.", file=sys.stderr)
        return 2
    if not email:
        print("Error: email is required.", file=sys.stderr)
        return 2

    try:
        return _create_or_promote_admin(
            username=username,
            password=password,
            email=email,
            display_name=display_name,
            force_reset_password=args.force_reset_password,
        )
    except Exception as exc:  # pragma: no cover
        print(f"Failed to create/promote admin: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
