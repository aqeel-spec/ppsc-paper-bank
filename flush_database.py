from app.database import get_session
from sqlalchemy import text

def flush_database():
    """
    Drop all tables and recreate them with the new schema.
    """
    session = next(get_session())
    
    try:
        print("🗑️  Dropping all existing tables...")
        
        # Drop tables in order (considering foreign key dependencies)
        tables_to_drop = [
            'top_bar',
            'side_bar', 
            'website',
            'websites'
        ]
        
        for table in tables_to_drop:
            try:
                session.execute(text(f'DROP TABLE IF EXISTS {table}'))
                print(f"   ✅ Dropped table: {table}")
            except Exception as e:
                print(f"   ⚠️  Could not drop {table}: {str(e)}")
        
        session.commit()
        print("\n🔄 All tables dropped successfully!")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error during table drop: {str(e)}")
    finally:
        session.close()

def recreate_tables():
    """
    Recreate all tables using SQLModel.
    """
    print("\n🏗️  Recreating tables with new schema...")
    
    try:
        # Import all models to ensure they're registered
        from app.models.websites import Websites
        from app.models.website import Website
        from app.models.top_bar import TopBar
        from app.models.side_bar import SideBar
        from app.database import engine
        from sqlmodel import SQLModel
        
        # Create all tables
        SQLModel.metadata.create_all(engine)
        print("   ✅ All tables recreated successfully!")
        
        # Verify table creation
        from app.database import get_session
        session = next(get_session())
        
        # Check table structures
        print("\n📋 Verifying new table structures:")
        
        # Check top_bar structure
        result = session.execute(text('DESCRIBE top_bar'))
        print("\n   TOP_BAR TABLE:")
        for row in result.fetchall():
            print(f"      {row[0]} - {row[1]}")
        
        # Check side_bar structure  
        result = session.execute(text('DESCRIBE side_bar'))
        print("\n   SIDE_BAR TABLE:")
        for row in result.fetchall():
            print(f"      {row[0]} - {row[1]}")
            
        session.close()
        
    except Exception as e:
        print(f"❌ Error during table recreation: {str(e)}")

if __name__ == "__main__":
    print("🚀 Starting database flush and schema update...")
    print("="*60)
    
    # Step 1: Drop all tables
    flush_database()
    
    # Step 2: Recreate tables with new schema
    recreate_tables()
    
    print("\n" + "="*60)
    print("✅ Database flush and schema update completed!")
    print("🔧 Ready for fresh testing with individual record schema.")
