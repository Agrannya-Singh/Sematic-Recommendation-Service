from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import movies, recommend

# --- APP CONFIGURATION ---
app = FastAPI(title="ScreenScout Intelligence Engine", version="PRODUCTION")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROUTERS ---
app.include_router(movies.router)
app.include_router(recommend.router)

@app.get("/")
def health_check():
    return {"status": "online", "mode": "Secure Production"}
