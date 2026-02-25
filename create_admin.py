#!/usr/bin/env python
"""
create_admin.py — Standalone script to create or reset the admin user.

Usage:
    python create_admin.py

Reads ADMIN_USERNAME, ADMIN_PASSWORD, and ADMIN_EMAIL from .env.
If the admin already exists, updates their password and role.
"""
import os
import sys

# Make sure app package is importable from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# ── Load DB engine and models ──────────────────────────────────────────────
from app.database import engine
from app.models.user import User, UserRole
from app.security import hash_password, ADMIN_USERNAME, ADMIN_PASSWORD

from sqlmodel import Session, select


def main():
    admin_email = os.getenv("ADMIN_EMAIL", f"{ADMIN_USERNAME}@admin.local")

    print(f"🔑 Admin credentials from .env:")
    print(f"   Username : {ADMIN_USERNAME}")
    print(f"   Email    : {admin_email}")

    with Session(engine) as session:
        existing = session.exec(
            select(User).where(
                (User.username == ADMIN_USERNAME) | (User.email == admin_email)
            )
        ).one_or_none()

        if existing:
            print(f"\n⚠️  User '{ADMIN_USERNAME}' already exists (id={existing.id}).")
            answer = input("Reset password and force admin role? [y/N]: ").strip().lower()
            if answer != "y":
                print("Aborted.")
                return
            existing.hashed_password = hash_password(ADMIN_PASSWORD)
            existing.role = UserRole.admin
            existing.credits = 999
            existing.is_active = True
            session.add(existing)
            session.commit()
            print(f"✅ Admin user '{ADMIN_USERNAME}' updated successfully.")
        else:
            admin_user = User(
                username=ADMIN_USERNAME,
                email=admin_email,
                hashed_password=hash_password(ADMIN_PASSWORD),
                display_name="Admin",
                role=UserRole.admin,
                credits=999,
                is_active=True,
            )
            session.add(admin_user)
            session.commit()
            print(f"✅ Admin user '{ADMIN_USERNAME}' created successfully.")

    print("\nDone! You can now login with:")
    print(f"   POST /auth/login")
    print(f"   {{\"username\": \"{ADMIN_USERNAME}\", \"password\": \"<from .env>\"}}")


if __name__ == "__main__":
    main()
