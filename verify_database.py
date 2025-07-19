from sqlmodel import Session, select
from app.database import get_engine
from app.models.websites import Websites
from app.models.category import Category
from app.models.mcqs_bank import MCQ
from app.models.paper import PaperModel

def check_database_state():
    """Check the current state of the database."""
    try:
        with Session(get_engine()) as session:
            # Count records in each table
            websites = session.exec(select(Websites)).all()
            categories = session.exec(select(Category)).all()
            mcqs = session.exec(select(MCQ)).all()
            papers = session.exec(select(PaperModel)).all()
            
            print("📊 DATABASE STATE VERIFICATION")
            print("=" * 50)
            print(f"🌐 Total Websites: {len(websites)}")
            print(f"📂 Total Categories: {len(categories)}")
            print(f"❓ Total MCQs: {len(mcqs)}")
            print(f"📄 Total Papers: {len(papers)}")
            print(f"📊 Total Records: {len(websites) + len(categories) + len(mcqs) + len(papers)}")
            
            print("\n🌐 WEBSITE DETAILS:")
            for website in websites:
                print(f"   ID: {website.id}, Name: {website.website_name}, URL: {website.base_url}")
            
            print("\n📂 CATEGORY DETAILS:")
            for category in categories[:10]:  # Show first 10
                print(f"   ID: {category.id}, Name: {category.name}, Slug: {category.slug}")
            if len(categories) > 10:
                print(f"   ... and {len(categories) - 10} more categories")
            
            print("\n❓ RECENT MCQ DETAILS:")
            recent_mcqs = session.exec(select(MCQ).order_by(MCQ.created_at.desc()).limit(10)).all()
            for mcq in recent_mcqs:
                print(f"   ID: {mcq.id}, Question: {mcq.question_text[:60]}...")
                print(f"      Category ID: {mcq.category_id}, Created: {mcq.created_at}")
            
            # Check for placeholder MCQs
            placeholder_mcqs = session.exec(select(MCQ).where(MCQ.question_text.like('%PLACEHOLDER%'))).all()
            print(f"\n🔍 PLACEHOLDER MCQs FOUND: {len(placeholder_mcqs)}")
            
            if placeholder_mcqs:
                print("   Recent placeholder MCQs:")
                for mcq in placeholder_mcqs[:5]:
                    print(f"   - {mcq.question_text}")
                    print(f"     Explanation: {mcq.explanation[:100]}...")
            
            return {
                'success': True,
                'websites': len(websites),
                'categories': len(categories),
                'mcqs': len(mcqs),
                'papers': len(papers),
                'placeholder_mcqs': len(placeholder_mcqs)
            }
            
    except Exception as e:
        print(f"❌ Error checking database: {str(e)}")
        return {'success': False, 'error': str(e)}

if __name__ == "__main__":
    result = check_database_state()
    
    if result['success']:
        print(f"\n✅ DATABASE VERIFICATION COMPLETE")
        print(f"   📈 Data insertion appears successful!")
        print(f"   🎯 Found {result['placeholder_mcqs']} placeholder MCQs from our collection process")
    else:
        print(f"\n❌ DATABASE VERIFICATION FAILED: {result['error']}")
