from sqlalchemy import create_engine
import sys

URL = "mysql+pymysql://aqeel:aqeel123@localhost:3307/th_back_test"

def test_connection():
    try:
        engine = create_engine(URL)
        with engine.connect() as conn:
            print("Successfully connected to the database!")
            return True
    except Exception as e:
        print("Failed to connect to the database:", e)
        return False

if __name__ == "__main__":
    if test_connection():
        sys.exit(0)
    else:
        sys.exit(1)
