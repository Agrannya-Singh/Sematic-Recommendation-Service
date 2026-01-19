from fastapi import APIRouter, Query, HTTPException
from app.database import get_db_connection, secure_poster_url
import sqlite3

router = APIRouter()

@router.get("/movies")
def get_movies(page: int = Query(1, ge=1), limit: int = Query(24, ge=1, le=100)):
    """Reads directly from the movies.db file for the homepage."""
    offset = (page - 1) * limit

    try:
        with get_db_connection() as conn:
            # Use 'vote_average' as confirmed by schema check, mapping to 'score'
            cursor = conn.execute("SELECT * FROM movies ORDER BY vote_average DESC LIMIT ? OFFSET ?", (limit, offset))
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                m = dict(row)
                
                # Map DB column 'vote_average' to API field 'score'
                if 'vote_average' in m:
                    m['score'] = m['vote_average']
                
                # Secure Poster Handling using helper
                m = secure_poster_url(m)
                
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
