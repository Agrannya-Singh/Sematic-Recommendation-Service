from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
import google.generativeai as genai
import os

app = FastAPI()

# --- CORS  ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # mr gippity told me so allows origin of requests from all sites
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIG ---
# On Render, these come from Environment Variables
PINECONE_KEY = os.getenv("PINECONE_KEY")
GEMINI_KEY = os.getenv("GEMINI_KEY")

if not PINECONE_KEY or not GEMINI_KEY:
    raise RuntimeError("Missing API Keys in Environment Variables")

# --- INIT SERVICES ---
# Optimization: Load model outside handler to avoid reloading per request wish i was rich enough for the 16GB VM :(
print("Loading Model...") 
embed_model = SentenceTransformer('all-MiniLM-L6-v2') 
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("screenscout-v2")

genai.configure(api_key=GEMINI_KEY)
chat_model = genai.GenerativeModel('gemini-1.5-flash')

class SearchRequest(BaseModel):
    query: str

@app.get("/")
def health_check():
    return {"status": "ScreenScout Intelligence Online"}

@app.post("/search")
async def search_movies(req: SearchRequest):
    try:
        # 1. Embed Query
        query_vec = embed_model.encode(req.query).tolist()
        
        # 2. Search Pinecone
        results = index.query(vector=query_vec, top_k=6, include_metadata=True)
        
        movies = []
        context_text = ""
        
        for match in results['matches']:
            m = match['metadata']
            # Ensure poster path is full URL for frontend convenience
            poster = f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}" if m.get('poster_path') else None
            
            movie_data = {
                "id": match['id'],
                "title": m.get('title'),
                "overview": m.get('overview'),
                "poster_url": poster,
                "score": match['score']
            }
            movies.append(movie_data)
            context_text += f"Title: {m.get('title')}. Plot: {m.get('overview')}\n"

        # 3. AI Analysis (RAG)
        prompt = f"""
        User Query: "{req.query}"
        Movie Matches: {context_text}
        
        Act as a movie critic. In one short sentence, tell the user which of these is the absolute best pick and why.
        """
        
        analysis = chat_model.generate_content(prompt).text
        
        return {
            "ai_agent_response": analysis,
            "results": movies
        }

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Intelligence System Failure")
