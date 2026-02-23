from sqlalchemy import create_engine
import sys

URL_BACK = "mysql+pymysql://aqeel:aqeel123@localhost:3307/th_back"
URL_TEST = "mysql+pymysql://aqeel:aqeel123@localhost:3307/th_back_test"

def test_connection(url, db_name):
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            print(f"✅ Successfully connected to '{db_name}'!")
            return True
    except Exception as e:
        print(f"❌ Failed to connect to '{db_name}'. Error: {e}")
        return False

if __name__ == "__main__":
    print("Testing connection to th_back...")
    backend_ok = test_connection(URL_BACK, "th_back")
    print("-" * 40)
    print("Testing connection to th_back_test...")
    test_ok = test_connection(URL_TEST, "th_back_test")
    
    if backend_ok and not test_ok:
        print("\nRecommendation: Change your DATABASE_URL to use 'th_back' instead of 'th_back_test', or create the 'th_back_test' database manually.")
    elif not backend_ok and not test_ok:
        print("\nRecommendation: Your user 'aqeel' might not have permissions to access any of these databases, or the databases don't exist.")
    
