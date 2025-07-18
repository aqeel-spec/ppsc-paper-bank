"""
Test script for dynamic category system.
"""
import requests
import json

BASE_URL = "http://127.0.0.1:8000"


def test_dynamic_categories():
    """Test the dynamic category system end-to-end."""
    print("🧪 Testing Dynamic Category System")
    print("=" * 50)
    
    # Test 1: Create categories
    print("\n1. Creating categories...")
    categories_to_create = [
        {"name": "PPSC Test Series 2025"},
        {"name": "Federal Public Service Commission"},
        {"name": "Provincial Service Commission"}
    ]
    
    created_categories = []
    for cat_data in categories_to_create:
        response = requests.post(f"{BASE_URL}/categories/", json=cat_data)
        if response.status_code == 200:
            category = response.json()
            created_categories.append(category)
            print(f"   ✅ Created: {category['name']} -> {category['slug']}")
        else:
            print(f"   ❌ Failed to create: {cat_data['name']}")
    
    # Test 2: Get all categories
    print("\n2. Getting all categories...")
    response = requests.get(f"{BASE_URL}/categories/")
    if response.status_code == 200:
        all_categories = response.json()
        print(f"   ✅ Found {len(all_categories)} categories")
        for cat in all_categories:
            print(f"      - {cat['name']} ({cat['slug']})")
    
    # Test 3: Test slug validation
    print("\n3. Testing slug validation...")
    if created_categories:
        first_slug = created_categories[0]['slug']
        response = requests.get(f"{BASE_URL}/categories/validate-slug/{first_slug}")
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Slug '{first_slug}' is valid: {result['is_valid']}")
    
    # Test 4: Create MCQs with existing category
    print("\n4. Creating MCQs with existing category...")
    if created_categories:
        mcq_data = {
            "question_text": "Who is the founder of Pakistan?",
            "option_a": "Allama Iqbal",
            "option_b": "Quaid-e-Azam Muhammad Ali Jinnah",
            "option_c": "Liaquat Ali Khan",
            "option_d": "Sir Syed Ahmad Khan",
            "correct_answer": "option_b",
            "explanation": "Quaid-e-Azam Muhammad Ali Jinnah is known as the founder of Pakistan",
            "category_slug": created_categories[0]['slug']
        }
        
        response = requests.post(f"{BASE_URL}/mcqs/", json=mcq_data)
        if response.status_code == 200:
            mcq = response.json()
            print(f"   ✅ Created MCQ with ID: {mcq['id']}")
    
    # Test 5: Create MCQ with new category
    print("\n5. Creating MCQ with new category...")
    mcq_with_new_cat = {
        "question_text": "What is the highest peak in Pakistan?",
        "option_a": "Nanga Parbat",
        "option_b": "K2",
        "option_c": "Rakaposhi",
        "option_d": "Tirich Mir",
        "correct_answer": "option_b",
        "explanation": "K2 is the highest peak in Pakistan and the second highest in the world",
        "new_category_slug": "mountains_of_pakistan",
        "new_category_name": "Mountains of Pakistan"
    }
    
    response = requests.post(f"{BASE_URL}/mcqs/", json=mcq_with_new_cat)
    if response.status_code == 200:
        mcq = response.json()
        print(f"   ✅ Created MCQ with new category, MCQ ID: {mcq['id']}")
    
    # Test 6: Verify new category was created
    print("\n6. Verifying new category creation...")
    response = requests.get(f"{BASE_URL}/categories/slug/mountains_of_pakistan")
    if response.status_code == 200:
        category = response.json()
        print(f"   ✅ New category verified: {category['name']} ({category['slug']})")
    
    # Test 7: Get category with MCQs
    print("\n7. Getting category with MCQs...")
    if created_categories:
        cat_id = created_categories[0]['id']
        response = requests.get(f"{BASE_URL}/categories/{cat_id}/with-mcqs")
        if response.status_code == 200:
            category_with_mcqs = response.json()
            mcq_count = len(category_with_mcqs.get('mcqs', []))
            print(f"   ✅ Category '{category_with_mcqs['name']}' has {mcq_count} MCQs")
    
    print("\n🎉 Dynamic Category System Test Complete!")
    print("=" * 50)


if __name__ == "__main__":
    try:
        test_dynamic_categories()
    except Exception as e:
        print(f"❌ Test failed: {e}")
