import traceback
import json
from pinecone import Pinecone
import google.generativeai as genai
from app.config import PINECONE_KEY, GEMINI_KEY
from app.database import get_titles_from_ids, secure_poster_url
from app.schemas import RecommendationRequest

class RecommendationService:
    def __init__(self):
        self.pc = None
        self.index = None
        self.chat_model = None
        self.init_ai_services()

    def init_ai_services(self):
        try:
            if PINECONE_KEY:
                self.pc = Pinecone(api_key=PINECONE_KEY)
                self.index = self.pc.Index("screenscout-google-v1") 
                print(" [Service] Connected to Pinecone.")
            
            if GEMINI_KEY:
                genai.configure(api_key=GEMINI_KEY)
                self.chat_model = genai.GenerativeModel('gemini-1.5-flash')
                print(" [Service] Connected to Gemini.")
        except Exception as e:
            print(f" [Service] Discovery Error: {e}")

    async def generate_recommendations(self, req: RecommendationRequest):
        try:
            # 1. SETUP
            selected_titles = get_titles_from_ids(req.selected_movie_ids)
            augmented_query = f"Movies similar to {', '.join(selected_titles)}. Context: {req.query}" if selected_titles else req.query
            print(f" DEBUG: Embedding Query -> {augmented_query[:50]}...")

            # 2. EMBED
            try:
                emb_response = genai.embed_content(
                    model="models/text-embedding-004",
                    content=augmented_query,
                    task_type="retrieval_query"
                )
                query_vec = emb_response['embedding']
            except Exception as embed_err:
                return {"error": f"GOOGLE EMBEDDING FAILED: {str(embed_err)}", "movies": []}
            
            # 3. SEARCH PINECONE
            try:
                results = self.index.query(
                    vector=query_vec, 
                    top_k=40,
                    include_metadata=True
                )
            except Exception as pinecone_err:
                 return {"error": f"PINECONE SEARCH FAILED: {str(pinecone_err)}", "movies": []}

            # 4. CHECK RESULTS
            if not results['matches']:
                 return {"ai_reasoning": "I couldn't find any matches. Try a broader search.", "movies": []}

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
            
            ai_data = {}
            try:
                response = self.chat_model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                ai_data = json.loads(response.text)
            except Exception as ai_err:
                 print(f"⚠️ AI Brain Freeze: {ai_err}")
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
                    # Use helper for consistent poster logic
                    m = secure_poster_url(m)
                    
                    final_movies.append({
                        "id": match['id'],
                        "title": m.get('title'),
                        "overview": m.get('overview'),
                        "poster_url": m.get('poster_url'),
                        "score": match['score']
                    })
            
            return {
                "ai_reasoning": ai_data.get("reasoning"),
                "movies": final_movies
            }

        except Exception as e:
            traceback.print_exc()
            return {"error": f"SERVER ERROR: {str(e)}", "movies": []}

# Singleton instance
recommendation_service = RecommendationService()
