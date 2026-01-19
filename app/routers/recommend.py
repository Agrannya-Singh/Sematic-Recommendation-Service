from fastapi import APIRouter
from app.schemas import RecommendationRequest
from app.services.recommendation import recommendation_service

router = APIRouter()

@router.post("/recommend")
async def recommend_movies(req: RecommendationRequest):
    return await recommendation_service.generate_recommendations(req)
