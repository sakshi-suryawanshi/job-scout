# test_db.py - Alternative version
import os
from dotenv import load_dotenv

# Force reload of modules
import sys
modules_to_remove = [k for k in sys.modules.keys() if 'supabase' in k]
for m in modules_to_remove:
    del sys.modules[m]

from supabase._sync.client import SyncClient as Client

load_dotenv()

def test_connection():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("❌ Missing SUPABASE_URL or SUPABASE_KEY in .env")
        return False
    
    print(f"🔗 Connecting to: {url[:30]}...")
    
    try:
        # Direct client creation without proxy
        client = Client(url, key)
        print("✅ Client created")
        
        # Test insert
        print("\n📝 Test 1: INSERT")
        test_company = {
            "name": "Test Company DB Connection",
            "career_url": "https://example.com/careers",
            "ats_type": "greenhouse",
            "source": "manual"
        }
        
        result = client.table("companies").insert(test_company).execute()
        
        if not result.data:
            print("❌ Insert failed")
            return False
            
        inserted_id = result.data[0]['id']
        print(f"✅ INSERT successful, ID: {inserted_id}")
        
        # Cleanup
        client.table("companies").delete().eq("id", inserted_id).execute()
        print("✅ DELETE successful")
        
        print("\n🎉 DATABASE CONNECTION WORKING!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_connection()
    exit(0 if success else 1)