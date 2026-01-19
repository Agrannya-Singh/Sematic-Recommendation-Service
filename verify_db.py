import sqlite3
import os

try:
    conn = sqlite3.connect("movies.db")
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(movies);")
    rows = cursor.fetchall()
    print("COLUMNS:")
    for r in rows:
        print(f"- {r[1]}")
    conn.close()
except Exception as e:
    print(e)
