import sqlite3
import os
import sys

# Add the current directory to sys.path to import from app
sys.path.append(os.getcwd())

from app.database import secure_poster_url

def test_secure_poster_url():
    print("Testing secure_poster_url...")
    
    # Test 1: TMDB relative path with leading slash
    m1 = {"poster_path": "/path/to/poster.jpg"}
    secure_poster_url(m1)
    assert m1["poster_url"] == "https://image.tmdb.org/t/p/w500/path/to/poster.jpg"
    print("Test 1 Passed: TMDB relative path with leading slash")
    
    # Test 2: TMDB relative path without leading slash
    m2 = {"poster_path": "another/path.jpg"}
    secure_poster_url(m2)
    assert m2["poster_url"] == "https://image.tmdb.org/t/p/w500/another/path.jpg"
    print("Test 2 Passed: TMDB relative path without leading slash")
    
    # Test 3: Full URL (Amazon S3 style)
    m3 = {"poster_path": "https://m.media-amazon.com/images/M/photo.jpg"}
    secure_poster_url(m3)
    assert m3["poster_url"] == "https://m.media-amazon.com/images/M/photo.jpg"
    print("Test 3 Passed: Full URL (Amazon S3 style)")
    
    # Test 4: Full URL (already in poster_url field)
    m4 = {"poster_url": "https://s3.bucket/movie.png"}
    secure_poster_url(m4)
    assert m4["poster_url"] == "https://s3.bucket/movie.png"
    print("Test 4 Passed: Full URL (already in poster_url field)")
    
    # Test 5: Empty or NaN
    m5 = {"poster_path": "NaN"}
    secure_poster_url(m5)
    assert m5["poster_url"] is None
    print("Test 5 Passed: Empty or NaN")

if __name__ == "__main__":
    try:
        test_secure_poster_url()
        print("\nAll internal logic tests passed!")
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {e}")
