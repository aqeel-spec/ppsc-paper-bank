import sys
import os

# Ensure the root directory is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlmodel import Session, select
from app.database import engine
from app.models.category import Category

def update_categories_prefix():
    """
    Prepends 'Subjectwise/' to category names and 'subjectwise/' to category slugs
    if they are not already present.
    """
    with Session(engine) as session:
        statement = select(Category)
        categories = session.exec(statement).all()
        
        updated_count = 0
        for cat in categories:
            needs_update = False
            
            if not cat.name.startswith("Subjectwise/"):
                cat.name = f"Subjectwise/{cat.name}"
                needs_update = True
                
            if not cat.slug.startswith("subjectwise/"):
                cat.slug = f"subjectwise/{cat.slug}"
                needs_update = True
                
            if needs_update:
                session.add(cat)
                updated_count += 1
                print(f"Updated: {cat.name} ({cat.slug})")
                
        session.commit()
        print(f"\nSuccessfully added 'Subjectwise/' prefix to {updated_count} categories.")

if __name__ == "__main__":
    print("Starting category update...")
    update_categories_prefix()
