from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pinecone import Pinecone
import google.generativeai as genai
import os

# --- APP INITIALIZATION ---
app = FastAPI(title="ScreenScout Intelligence Engine", version="2.0.0")

# --- CORS (Crucial for Next.js) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  #
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURATION ---
PINECONE_KEY = os.getenv("PINECONE_KEY")
GEMINI_KEY = os.getenv("GEMINI_KEY")

if not PINECONE_KEY or not GEMINI_KEY:
    # Fail fast if keys are missing (helps debugging on Render)
    raise RuntimeError("CRITICAL: Missing API Keys in Environment Variables.")

# --- SERVICE SETUP ---
# 1. Pinecone (Vector Database)
pc = Pinecone(api_key=PINECONE_KEY)
index_name = "screenscout-production-v1" 
index = pc.Index(index_name)

# 2. Google Gemini (The Brain)
genai.configure(api_key=GEMINI_KEY)
chat_model = genai.GenerativeModel('gemini-1.5-flash')

# --- DATA MODELS ---
class SearchRequest(BaseModel):
    query: str

# --- ENDPOINTS ---

@app.get("/")
def health_check():
    """Keep-alive endpoint for Render"""
    return {"status": "online", "engine": "Google-Native RAG"}

@app.post("/search")
async def search_movies(req: SearchRequest):
    try:
        # STEP 1: EMBED THE USER QUERY
        # We use the same model as ingestion, but with 'retrieval_query' task type
        # to optimize the vector for searching.
        emb_response = genai.embed_content(
            model="models/text-embedding-005",
            content=req.query,
            task_type="retrieval_query"
        )
        query_vec = emb_response['embedding']
        
        # STEP 2: SEMANTIC SEARCH (HNSW)
        # We ask Pinecone for the 6 nearest neighbors
        results = index.query(
            vector=query_vec, 
            top_k=6, 
            include_metadata=True
        )
        
        movies = []
        context_text = ""
        
        # STEP 3: PARSE RESULTS
        for match in results['matches']:
            m = match['metadata']
            
            # Format Poster URL for Frontend
            # Check if poster_path exists and isn't 'nan'
            poster_path = m.get('poster_path')
            if poster_path and str(poster_path).lower() != 'nan':
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            else:
                poster_url = None # Frontend should show placeholder

            movie_data = {
                "id": match['id'],
                "title": m.get('title'),
                "overview": m.get('overview'),
                "release_date": m.get('release_date'),
                "poster_url": poster_url,
                "score": match['score'] # How close is the match?
            }
            movies.append(movie_data)
            
            # Build context for the AI Agent
            context_text += f"Movie: {m.get('title')}\nPlot: {m.get('overview')}\n---\n"

        # STEP 4: RAG GENERATION 
        prompt = f"""
        User Query: "{req.query}"
        
        Here are the top movie matches based on semantic search:
        {context_text}
        
        Task:
        Act as a witty, knowledgeable movie critic. 
        Select the ONE best movie from this list that fits the user's query perfectly.
        Write a short, engaging 2-sentence recommendation explaining WHY it's the right choice.
        Do not list all movies. Just pick the winner.
        """
        
        analysis = chat_model.generate_content(prompt).text
        
        return {
            "ai_agent_response": analysis,
            "results": movies
        }

    except Exception as e:
        print(f"Server Error: {e}")
        raise HTTPException(status_code=500, detail="Intelligence Engine Failure")
