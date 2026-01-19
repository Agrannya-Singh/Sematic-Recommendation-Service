import os

# --- 🔒 SECURE CREDENTIALS ---
PINECONE_KEY = os.getenv("PINECONE_KEY")
GEMINI_KEY = os.getenv("GEMINI_KEY")

# --- PATHS ---
# Assumes this config.py is inside app/, so we go up one level to root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "movies.db")
