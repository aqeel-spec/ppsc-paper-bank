from starlette.config import Config
from starlette.datastructures import Secret

# 🌐 Load environment configuration
try:
    # Attempting to load configuration from .env file 📂
    config = Config(".env")
    print("✅ Configuration loaded from .env file.")
except FileNotFoundError:
    # If .env is not found, fallback to default configuration 🛠️
    config = Config()
    print("⚠️ .env file not found. Using default configuration.")
    
    



# 🔒 Fetching sensitive data securely
DATABASE_URL = config("DATABASE_URL", cast=Secret)
TEST_DATABASE_URL = config("TEST_DATABASE_URL", cast=str)