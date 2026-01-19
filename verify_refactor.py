try:
    print("Checking imports...")
    from app.main import app
    from app.config import DB_PATH
    from app.database import get_db_connection
    from app.schemas import RecommendationRequest
    from app.routers import movies, recommend
    
    print(f"✅ App instantiated: {app.title}")
    print(f"✅ DB Path: {DB_PATH}")
    
    import os
    if os.path.exists(DB_PATH):
        print("✅ DB File found.")
    else:
        print("❌ DB File NOT found at expected path.")

    print("Checking instantiation of models...")
    req = RecommendationRequest(query="test")
    print("✅ Schema instantiated.")

    print("Refactor verification SUCCESS.")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"❌ Verification FAILED: {e}")
