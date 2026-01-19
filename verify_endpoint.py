import os
import sys
import asyncio
import json

# Ensure app can be imported
sys.path.append(os.getcwd())

from main import app
from starlette.testclient import TestClient



from main import get_movies

async def test_movies_endpoint():
    print("Testing get_movies function directly...")
    try:
         # Need to mock the request context or just call the function if it doesn't depend on request
         # get_movies depends on nothing but params.
         response = await get_movies(page=1, limit=5)
         
         data = response.get("data", [])
         print(f"✅ Picked up {len(data)} movies.")
         
         for m in data:
            print(f"Title: {m.get('title')}")
            print(f"  Poster: {m.get('poster_url')}")
            print(f"  Year: {m.get('year')}")
            print(f"  IMDb: {m.get('imdb_rating')}")
            
            if m.get('year') or m.get('imdb_rating'):
                print("  -> OMDB Enrichment seems to be working.")
            else:
                print("  -> No OMDB data found (Check API Key or Movie Title).")
            print("-" * 30)

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    if not os.getenv("OMDB_API_KEY"):
         print("⚠️ OMDB_API_KEY not set. Please set it to run this test.")
         # sys.exit(1) # Optional: exit if critical, or let it run to see failure.
    
    asyncio.run(test_movies_endpoint())
            print(f"Title: {m.get('title')}")
            print(f"  Poster: {m.get('poster_url')}")
            print(f"  Year: {m.get('year')}")
            print(f"  IMDb: {m.get('imdb_rating')}")
            
            # Basic validation
            if m.get('year') or m.get('imdb_rating'):
                print("  -> OMDB Enrichment seems to be working.")
            else:
                print("  -> No OMDB data found (Check API Key or Movie Title).")
            print("-" * 30)
    else:
        print(f"❌ Failed to fetch movies. Status: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
   
    if not os.getenv("OMDB_API_KEY"):
        os.environ["OMDB_API_KEY"] = "41e50491"
        print(" Injected OMDB_API_KEY for testing purposes.")
        
    test_movies_endpoint()
