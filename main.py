from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pinecone import Pinecone
import google.generativeai as genai
import os
import sqlite3
from typing import List, Optional
import traceback 
import httpx
import asyncio
from app.database import secure_poster_url

# --- APP CONFIGURATION ---
app = FastAPI(title="ScreenScout Intelligence Engine", version="PRODUCTION")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 🔒 SECURE CREDENTIALS ---
# We read strictly from the Environment.
PINECONE_KEY = os.getenv("PINECONE_KEY")
GEMINI_KEY = os.getenv("GEMINI_KEY")
OMDB_API_KEY = os.getenv("OMDB_API_KEY") # 🔑 Get this from environment

# Database Path
DB_PATH = os.path.join(os.path.dirname(__file__), "movies.db")

# --- SERVICE INITIALIZATION ---
if not PINECONE_KEY:
    print("❌ CRITICAL: PINECONE_KEY not found in Environment Variables!")
if not GEMINI_KEY:
    print("❌ CRITICAL: GEMINI_KEY not found in Environment Variables!")

try:
    if PINECONE_KEY:
        pc = Pinecone(api_key=PINECONE_KEY)
        index = pc.Index("screenscout-google-v1") 
        print("✅ Connected to Pinecone.")
    
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
        chat_model = genai.GenerativeModel('gemini-1.5-flash')
        print("✅ Connected to Gemini.")

except Exception as e:
    print(f"❌ Startup Error: {e}")

# --- DATA MODELS ---
class RecommendationRequest(BaseModel):
    query: str 
    selected_movie_ids: List[str] = []

# --- HELPER FUNCTIONS ---
def get_titles_from_ids(movie_ids: List[str]):
    """Fetches movie titles from SQLite for the selected IDs."""
    if not movie_ids or not os.path.exists(DB_PATH):
        return []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            placeholders = ', '.join('?' for _ in movie_ids)
            query = f"SELECT title FROM movies WHERE id IN ({placeholders})"
            cursor = conn.execute(query, movie_ids)
            return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"SQLite Error: {e}")
        return []

async def fetch_omdb_metadata(title: str) -> dict:
    """Fetches the latest movie metadata (like high-res posters) from OMDB."""
    if not OMDB_API_KEY:
        return {}
    
    try:
        async with httpx.AsyncClient() as client:
            url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                if data.get("Response") == "True":
                    return {
                        "poster_url": data.get("Poster"),
                        "year": data.get("Year"),
                        "rating": data.get("imdbRating")
                    }
    except Exception as e:
        print(f"⚠️ OMDB Error for '{title}': {e}")
    return {}

# --- ENDPOINTS ---

@app.get("/")
def health_check():
    return {"status": "online", "mode": "Secure Production"}

@app.get("/movies")
async def get_movies(page: int = Query(1, ge=1), limit: int = Query(1000, ge=1, le=2000)):
    """Reads directly from the movies.db file for the homepage."""
    offset = (page - 1) * limit
    if not os.path.exists(DB_PATH):
        return {"data": [], "error": "Database file not found."}

    try:
        # Use asyncio.to_thread for blocking DB call to avoid blocking the event loop
        # Although sqlite3 is fast, for high concurrency or long queries it's better.
        # But here valid for logic separation.
        def read_db():
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM movies ORDER BY vote_average DESC LIMIT ? OFFSET ?", (limit, offset))
                rows = cursor.fetchall()
                total = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
                return rows, total
        
        rows, total = await asyncio.to_thread(read_db)
        
        # Prepare for async OMDB fetching
        async def enrich_movie(row):
            m = secure_poster_url(dict(row))
            if 'vote_average' in m:
                m['score'] = m['vote_average']
            
            # Fetch OMDB data concurrently
            title = m.get('title')
            omdb_data = await fetch_omdb_metadata(title)
            
            # Enrich
            if omdb_data:
                m['poster_url'] = omdb_data.get('poster_url') or m.get('poster_url')
                m['year'] = omdb_data.get('year')
                m['imdb_rating'] = omdb_data.get('rating')
            
            return m

        # Execute enrichment concurrently
        results = await asyncio.gather(*(enrich_movie(row) for row in rows))

        return {
            "data": results,
            "meta": {
                "current_page": page,
                "limit": limit,
                "total_items": total,
                "total_pages": (total + limit - 1) // limit
            }
        }
    except Exception as e:
        print(f"DB Error: {e}")
        # traceback.print_exc() # detailed logs if needed
        raise HTTPException(status_code=500, detail="Database Read Error")

@app.post("/recommend")
async def recommend_movies(req: RecommendationRequest):
    try:
        # 1. SETUP
        selected_titles = get_titles_from_ids(req.selected_movie_ids)
        augmented_query = f"Movies similar to {', '.join(selected_titles)}. Context: {req.query}" if selected_titles else req.query

        print(f"🔎 DEBUG: Embedding Query with 004 -> {augmented_query[:50]}...")

        # 2. EMBED (STRICTLY MODEL 004)
        try:
            emb_response = genai.embed_content(
                model="models/text-embedding-004", # Correct Model
                content=augmented_query,
                task_type="retrieval_query"
            )
            query_vec = emb_response['embedding']
        except Exception as embed_err:
            return {"error": f"GOOGLE EMBEDDING FAILED: {str(embed_err)}", "movies": []}
        
        # 3. SEARCH PINECONE
        try:
            results = index.query(
                vector=query_vec, 
                top_k=50, # Higher fetch to allow filtering
                include_metadata=True
            )
        except Exception as pinecone_err:
             return {"error": f"PINECONE SEARCH FAILED: {str(pinecone_err)}", "movies": []}

        # 4. CHECK RESULTS
        if not results['matches']:
             return {"ai_reasoning": "I couldn't find any matches in the database. Try a broader search.", "movies": []}

        # 5. PREPARE AI CONTEXT (TOP 20 for AI to pick from, excluding selected)
        context_text = ""
        
        # Filter out movies the user already selected
        input_ids = set(req.selected_movie_ids)
        candidates = [m for m in results['matches'] if m['id'] not in input_ids]
        
        # Take Top 20 from refined list
        candidates = candidates[:20]
        
        for match in candidates:
            m = match['metadata']
            context_text += f"ID: {match['id']} | Title: {m.get('title')} | Overview: {m.get('overview')}\n"

        # 6. ASK GEMINI (RAG)
        prompt = f"""
        User Query: "{req.query}"
        User Likes: {", ".join(selected_titles)}
        
        Candidates:
        {context_text}
        
        Task:
        1. Select the Top 15 movies that best match the user's query and taste.
        2. Provide a specific, unique reason for why THIS user would like EACH movie. Do not use generic descriptions like "A great movie". Use the context of the user's query and likes.
        
        Return JSON:
        {{
            "movie_ids": ["id1", "id2", ...],
            "reasoning": {{
                "id1": "Custom reason 1...",
                "id2": "Custom reason 2..."
            }}
        }}
        """
        
        try:
            response = chat_model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            import json
            ai_data = json.loads(response.text)
        except Exception as ai_err:
             print(f" AI Brain Freeze: {ai_err}")
             # Graceful Fallback
             ai_data = {
                 "movie_ids": [m['id'] for m in candidates[:10]],
                 "reasoning": "Here are the most relevant movies from our database." 
                 # Note: reasoning is a string here in fallback, but dict in success. Frontend handles? 
                 # Let's align structure. If frontend expects generic string, we might need a change.
                 # Assuming we send per-movie reasoning, let's keep it dict or handle it.
                 # For now, fallback returns generic string for 'ai_reasoning' key in response if global.
                 # But we changed the prompt to return a dict of reasonings.
                 # Let's adjust response construction below.
             }

        # 7. ASSEMBLE RESPONSE
        final_movies = []
        target_ids = ai_data.get("movie_ids", [])
        if not target_ids: target_ids = [m['id'] for m in candidates[:10]]
        
        ai_reasonings = ai_data.get("reasoning", {})
        
        # Async enrichment for recommendations
        async def process_recommendation(match):
            m = match['metadata']
            title = m.get('title')
            
            # Enrich with OMDB metadata
            omdb_data = await fetch_omdb_metadata(title)
            
            # Update poster logic with OMDB fallback
            movie_dict = {
                "poster_path": omdb_data.get("poster_url") or m.get('poster_path')
            }
            movie_dict = secure_poster_url(movie_dict)
            
            # Get reasoning
            reasoning = ""
            if isinstance(ai_reasonings, dict):
                reasoning = ai_reasonings.get(match['id'], "Recommended based on your preferences.")
            else:
                reasoning = str(ai_reasonings)

            return {
                "id": match['id'],
                "title": title,
                "overview": m.get('overview'),
                "poster_url": movie_dict.get("poster_url"),
                "score": match['score'],
                "year": omdb_data.get("year"),
                "imdb_rating": omdb_data.get("rating"),
                "reasoning": reasoning
            }

        # We need to filter results based on target_ids first
        selected_matches = [m for m in results['matches'] if m['id'] in target_ids]
        
        # Execute concurrently
        final_movies = await asyncio.gather(*(process_recommendation(m) for m in selected_matches))
        
        return {
            "ai_reasoning": "Here are my top selections for you.", # Global context
            "movies": final_movies
        }

    except Exception as e:
        traceback.print_exc()
        return {"error": f"SERVER ERROR: {str(e)}", "movies": []}
