import sqlite3
import os

DB_PATH = "movies.db"

def simulate_get_movies(page, limit):
    print(f"\n--- Simulating GET /movies?page={page}&limit={limit} ---")
    offset = (page - 1) * limit
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            # Use 'vote_average' as confirmed by schema check
            cursor = conn.execute("SELECT * FROM movies ORDER BY vote_average DESC LIMIT ? OFFSET ?", (limit, offset))
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                m = dict(row)
                # Logic from main.py
                if 'vote_average' in m:
                    m['score'] = m['vote_average']
                
                if m['poster_path'] and str(m['poster_path']).lower() != 'nan':
                    m['poster_url'] = f"https://image.tmdb.org/t/p/w500{m['poster_path']}"
                else:
                    m['poster_url'] = None
                
                results.append(m)

            total = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
            
            print(f"✅ Extracted {len(results)} movies.")
            print(f"✅ Total Movies in DB: {total}")
            print(f"✅ Sample Movie 1: {results[0]['title']} (Score: {results[0].get('score')})")
            
    except Exception as e:
        print(f" Error: {e}")

if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        simulate_get_movies(page=1, limit=5)
        simulate_get_movies(page=2, limit=5)
    else:
        print(" DB not found")
