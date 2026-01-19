from pydantic import BaseModel
from typing import List, Optional

class RecommendationRequest(BaseModel):
    query: str 
    selected_movie_ids: List[str] = []
