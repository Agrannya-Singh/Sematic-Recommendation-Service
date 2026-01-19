import os
import sys
import asyncio
import json

# Ensure app can be imported
sys.path.append(os.getcwd())

from main import recommend_movies, RecommendationRequest

async def test_recommendation_flow():
    print("Testing /recommend endpoint with enhanced logic...")
    
    # Create valid request
    req = RecommendationRequest(
        query="Mind bending sci-fi movies",
        selected_movie_ids=["27205"] # Inception ID usually, or any valid ID from DB
    )
    
    try:
         # Call function directly
         response = await recommend_movies(req)
         
         movies = response.get("movies", [])
         ai_reasoning = response.get("ai_reasoning")
         
         print(f"✅ Received {len(movies)} recommendations.")
         print(f"🧠 AI Reasoning Context: {ai_reasoning}")
         
         if len(movies) >= 10:
             print("✅ Success: Returned 10 or more movies.")
         else:
             print(f"⚠️ Warning: Returned only {len(movies)} movies (Expected ~10).")

         for i, m in enumerate(movies[:3]): # Show first 3 details
            print(f"\nMovie {i+1}: {m.get('title')}")
            print(f"  Poster: {m.get('poster_url')}")
            print(f"  Year: {m.get('year')}")
            print(f"  IMDb: {m.get('imdb_rating')}")
            print(f"  Reasoning: {m.get('reasoning')}")
            
            if m.get('reasoning') and m.get('reasoning') != "Recommended based on your preferences.":
                print("  -> Custom reasoning detected.")
            else:
                 print("  -> Default reasoning used (Check LLM response).")
            
            if m.get('year'):
                print("  -> OMDB Enrichment working.")
            else:
                print("  -> No OMDB data.")

    except Exception as e:
        print(f"❌ Error during recommendation test: {e}")

if __name__ == "__main__":
    if not os.getenv("OMDB_API_KEY"):
         print("⚠️ OMDB_API_KEY not set. Please set it to run this test properly.")
    
    # We also need keys for Pinecone/Gemini strictly speaking, assuming they are in env.
    if not os.getenv("PINECONE_KEY") or not os.getenv("GEMINI_KEY"):
        print("❌ Missing PINECONE_KEY or GEMINI_KEY. Test will likely fail.")

    asyncio.run(test_recommendation_flow())
