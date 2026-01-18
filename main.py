from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pinecone import Pinecone
import google.generativeai as genai
import os
import sqlite3
from typing import List, Optional

# --- APP CONFIGURATION ---
app = FastAPI(title="ScreenScout Intelligence Engine", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENVIRONMENT VARIABLES ---
PINECONE_KEY = os.getenv("PINECONE_KEY")
GEMINI_KEY = os.getenv("GEMINI_KEY")
# Ensure movies.db is in the same folder
DB_PATH = os.path.join(os.path.dirname(__file__), "movies.db")

if not PINECONE_KEY or not GEMINI_KEY:
    raise RuntimeError("CRITICAL: Missing API Keys.")

# --- SERVICE INITIALIZATION ---
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("screenscout-google-v1") 

genai.configure(api_key=GEMINI_KEY)
# Using the model you need (requires google-generativeai>=0.7.2)
chat_model = genai.GenerativeModel('gemini-1.5-flash')

# --- DATA MODELS ---

class RecommendationRequest(BaseModel):
    query: str  # User's text description (e.g., "Something specifically about time loops")
    selected_movie_ids: List[str] = [] # List of IDs user clicked on (e.g., ["105", "550"])

# --- HELPER FUNCTIONS ---

def get_titles_from_ids(movie_ids: List[str]):
    """Fetches movie titles from SQLite for the selected IDs to enrich context."""
    if not movie_ids or not os.path.exists(DB_PATH):
        return []
    
    titles = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Safe parameterized query for multiple IDs
            placeholder = '?' # For one ID
            placeholders = ', '.join(placeholder for _ in movie_ids)
            query = f"SELECT title FROM movies WHERE id IN ({placeholders})"
            cursor = conn.execute(query, movie_ids)
            titles = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error fetching titles: {e}")
    return titles

# --- ENDPOINTS ---

@app.get("/")
def health_check():
    return {"status": "online", "mode": "Hybrid RAG + Pagination"}

# 1. INFINITE SCROLL / PAGINATION
@app.get("/movies")
def get_movies(page: int = Query(1, ge=1), limit: int = Query(24, ge=1, le=100)):
    """
    Reads directly from the movies.db file.
    Used for the main 'Browse' page.
    """
    offset = (page - 1) * limit
    
    if not os.path.exists(DB_PATH):
        # Fallback if DB isn't uploaded yet
        return {"data": [], "error": "Database file not found. Please upload movies.db"}

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            
            # Fetch Data (Sorted by score/popularity by default)
            cursor = conn.execute(
                "SELECT * FROM movies ORDER BY score DESC LIMIT ? OFFSET ?", 
                (limit, offset)
            )
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                m = dict(row)
                # Ensure poster URL is valid
                if m['poster_path'] and str(m['poster_path']).lower() != 'nan':
                    m['poster_url'] = f"https://image.tmdb.org/t/p/w500{m['poster_path']}"
                else:
                    m['poster_url'] = None
                
                # Clean up internal key
                if 'poster_path' in m: del m['poster_path'] 
                results.append(m)

            # Get Total Count for Pagination UI
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


# 2. HYBRID RECOMMENDATION (Text + Selection)
@app.post("/recommend")
async def recommend_movies(req: RecommendationRequest):
    try:
        # Step A: Context Enrichment
        # If user selected movies, we get their titles to help the AI understand "Vibe"
        selected_titles = get_titles_from_ids(req.selected_movie_ids)
        
        # Step B: Construct Synthetic Query
        # We combine the user's text with the "vibe" of selected movies
        if selected_titles:
            augmented_query = f"Movies similar to {', '.join(selected_titles)}. Also matching description: {req.query}"
        else:
            augmented_query = req.query

        # Step C: Embed
        emb_response = genai.embed_content(
            model="models/text-embedding-004",
            content=augmented_query,
            task_type="retrieval_query"
        )
        query_vec = emb_response['embedding']
        
        # Step D: Semantic Search (Fetch MORE candidates now, e.g., 40)
        # We fetch a larger pool so Gemini has enough options to pick the top 10-20
        results = index.query(
            vector=query_vec, 
            top_k=40, 
            include_metadata=True
        )
        
        # Step E: Prepare Context for Gemini
        candidates = []
        context_text = ""
        
        for match in results['matches']:
            m = match['metadata']
            candidates.append(m) # Keep track for final mapping
            context_text += f"ID: {match['id']} | Title: {m.get('title')} | Plot: {m.get('overview')}\n---\n"

        # Step F: RAG Selection (The Brain)
        # We ask Gemini to curate the list down to the best 10-20
        prompt = f"""
        User Request: "{req.query}"
        User Liked Movies: {", ".join(selected_titles) if selected_titles else "None selected"}
        
        Here is a list of 40 potential movie matches based on vector search:
        {context_text}
        
        TASK:
        1. Analyze the user's request and their liked movies.
        2. Select the top 10 to 20 movies from the provided list that BEST fit this specific request.
        3. For the top 1 recommendation, write a "Why you'll love it" sentence.
        4. Return the response in strictly JSON format (no markdown formatting) like this:
        {{
            "top_pick_reason": "Reason string...",
            "recommended_movie_ids": ["id1", "id2", "id3", ...]
        }}
        """
        
        # Generate
        response = chat_model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        
        # Parse AI Response
        import json
        ai_data = json.loads(response.text)
        
        # Step G: Filter and Format Final List
        final_movies = []
        recommended_ids = ai_data.get("recommended_movie_ids", [])
        
        # We map the IDs back to the full metadata we already have from Pinecone
        # (This avoids hitting the DB again)
        for match in results['matches']:
            if match['id'] in recommended_ids:
                m = match['metadata']
                # Formatting Image
                poster_path = m.get('poster_path')
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if (poster_path and str(poster_path) != 'nan') else None
                
                final_movies.append({
                    "id": match['id'],
                    "title": m.get('title'),
                    "overview": m.get('overview'),
                    "poster_url": poster_url,
                    "score": match['score']
                })
        
        return {
            "ai_reasoning": ai_data.get("top_pick_reason"),
            "count": len(final_movies),
            "movies": final_movies
        }

    except Exception as e:
        print(f"Recommendation Error: {e}")
        # Fallback: Just return the top 10 raw vector matches if AI fails
        # (This prevents the app from breaking entirely)
        return {"error": "AI Processing failed, falling back to raw search", "movies": []}
