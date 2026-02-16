#!/usr/bin/env python3

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("1. Testing basic imports...")
    from app.database import get_engine
    print("✅ Database import successful")
    
    from app.models.websites import Websites
    print("✅ Websites model import successful")
    
    from app.services.scrapper.top_urls import WebsiteTopService
    print("✅ URL service import successful")
    
    print("\n2. Testing service import...")
    import app.services.website_data_service as wds_module
    print("✅ Website data service module loaded")
    
    service_class = getattr(wds_module, 'WebsiteDataService', None)
    if service_class:
        print("✅ WebsiteDataService class found")
        service = service_class()
        print("✅ Service instance created")
    else:
        print("❌ WebsiteDataService class not found in module")
        print("Available attributes:", dir(wds_module))
    
    print("\n3. Testing simple database operation...")
    from sqlmodel import Session
    engine = get_engine()
    with Session(engine) as session:
        print("✅ Database session created successfully")
    
    print("\n🎉 All basic tests passed!")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"❌ Other error: {e}")
    import traceback
    traceback.print_exc()
