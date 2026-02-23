import sys
import os

# Ensure the root directory is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlmodel import Session, select
from app.database import engine
from app.models.category import Category

def ensure_subjectwise_root():
    """
    Creates the root 'Subjectwise' category if it doesn't exist yet.
    """
    with Session(engine) as session:
        statement = select(Category).where(Category.slug == "subjectwise")
        existing = session.exec(statement).first()
        
        if existing:
            print(f"Root category '{existing.name}' already exists.")
            return

        new_category = Category(
            name="Subjectwise",
            slug="subjectwise"
        )
        session.add(new_category)
        session.commit()
        session.refresh(new_category)
        print(f"Successfully created root category: {new_category.name} ({new_category.slug})")

if __name__ == "__main__":
    ensure_subjectwise_root()
