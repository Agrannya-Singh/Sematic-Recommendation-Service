from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pinecone import Pinecone
import google.generativeai as genai
import os
import sqlite3
from typing import List, Optional
import traceback 

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

# --- ENDPOINTS ---

@app.get("/")
def health_check():
    return {"status": "online", "mode": "Secure Production"}

@app.get("/movies")
def get_movies(page: int = Query(1, ge=1), limit: int = Query(24, ge=1, le=100)):
    """Reads directly from the movies.db file for the homepage."""
    offset = (page - 1) * limit
    if not os.path.exists(DB_PATH):
        return {"data": [], "error": "Database file not found."}

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM movies ORDER BY vote_average DESC LIMIT ? OFFSET ?", (limit, offset))
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                m = dict(row)
                # Map DB column 'vote_average' to API field 'score'
                if 'vote_average' in m:
                    m['score'] = m['vote_average']
                
                # Secure Poster Handling
                if m['poster_path'] and str(m['poster_path']).lower() != 'nan':
                    m['poster_url'] = f"https://image.tmdb.org/t/p/w500{m['poster_path']}"
                else:
                    m['poster_url'] = None
                if 'poster_path' in m: del m['poster_path'] 
                results.append(m)

            total = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]

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
                model="models/text-embedding-004", # ✅ Correct Model
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
                top_k=40, # High fetch for better filtering
                include_metadata=True
            )
        except Exception as pinecone_err:
             return {"error": f"PINECONE SEARCH FAILED: {str(pinecone_err)}", "movies": []}

        # 4. CHECK RESULTS
        if not results['matches']:
             return {"ai_reasoning": "I couldn't find any matches in the database. Try a broader search.", "movies": []}

        # 5. PREPARE AI CONTEXT
        context_text = ""
        for match in results['matches']:
            m = match['metadata']
            context_text += f"ID: {match['id']} | Title: {m.get('title')} | Overview: {m.get('overview')}\n"

        # 6. ASK GEMINI (RAG)
        prompt = f"""
        User Query: "{req.query}"
        User Likes: {", ".join(selected_titles)}
        
        Candidates:
        {context_text}
        
        Pick top 5. Return JSON:
        {{
            "reasoning": "Short explanation",
            "movie_ids": ["id1", "id2"]
        }}
        """
        
        try:
            response = chat_model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            import json
            ai_data = json.loads(response.text)
        except Exception as ai_err:
             print(f"⚠️ AI Brain Freeze: {ai_err}")
             # Graceful Fallback
             ai_data = {
                 "reasoning": "Here are the most relevant movies from our database.",
                 "movie_ids": [m['id'] for m in results['matches'][:5]]
             }

        # 7. ASSEMBLE RESPONSE
        final_movies = []
        target_ids = ai_data.get("movie_ids", [])
        if not target_ids: target_ids = [m['id'] for m in results['matches'][:5]]

        for match in results['matches']:
            if match['id'] in target_ids:
                m = match['metadata']
                # Robust Poster Logic
                raw_path = str(m.get('poster_path', ''))
                if raw_path and raw_path.lower() != 'nan':
                    if raw_path.startswith('http'): poster_url = raw_path
                    elif not raw_path.startswith('/'): poster_url = f"https://image.tmdb.org/t/p/w500/{raw_path}"
                    else: poster_url = f"https://image.tmdb.org/t/p/w500{raw_path}"
                else:
                    poster_url = None

                final_movies.append({
                    "id": match['id'],
                    "title": m.get('title'),
                    "overview": m.get('overview'),
                    "poster_url": poster_url,
                    "score": match['score']
                })
        
        return {
            "ai_reasoning": ai_data.get("reasoning"),
            "movies": final_movies
        }

    except Exception as e:
        traceback.print_exc()
        return {"error": f"SERVER ERROR: {str(e)}", "movies": []}
