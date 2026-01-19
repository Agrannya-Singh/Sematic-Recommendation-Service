import sqlite3
import os
from contextlib import contextmanager
from typing import List
from app.config import DB_PATH

@contextmanager
def get_db_connection():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def get_titles_from_ids(movie_ids: List[str]):
    """Fetches movie titles from SQLite for the selected IDs."""
    if not movie_ids or not os.path.exists(DB_PATH):
        return []
    try:
        with get_db_connection() as conn:
            placeholders = ', '.join('?' for _ in movie_ids)
            query = f"SELECT title FROM movies WHERE id IN ({placeholders})"
            cursor = conn.execute(query, movie_ids)
            return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"SQLite Error: {e}")
        return []

def secure_poster_url(m: dict) -> dict:
    """Standardizes poster URL handling for both TMDB paths and full URLs."""
    raw_path = str(m.get('poster_path', '') or m.get('poster_url', ''))
    
    if raw_path and raw_path.lower() != 'nan' and raw_path.strip():
        raw_path = raw_path.strip()
        if raw_path.startswith('http'): 
            m['poster_url'] = raw_path
        elif raw_path.startswith('/'): 
            m['poster_url'] = f"https://image.tmdb.org/t/p/w500{raw_path}"
        else: 
            # Handle cases where it might be a relative path without leading slash
            m['poster_url'] = f"https://image.tmdb.org/t/p/w500/{raw_path}"
    else:
        m['poster_url'] = None
    
    # Cleanup DB specific field
    if 'poster_path' in m: 
        del m['poster_path']
    return m
