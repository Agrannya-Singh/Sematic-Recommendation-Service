# Post-Mortem: OOM Error in Semantic-Recommendation-Service

**Incident ID:** OOM-2026-01-19
**Date:** 2026-01-19
**Repository Hash:** `0572edf`
**Impact:** Service crashed due to Out Of Memory (OOM) error on 512MB instances.

## 1. Issue Description
The application process was killed by the kernel for exceeding the 512MB memory limit. This occurred primarily during requests to the `/movies` endpoint.

## 2. Root Cause Analysis
Investigating the code revealed two main contributors:

### A. Design Flaw: Unnecessary External API Calls (Primary Cause)
The `/movies` endpoint was incorrectly implemented to call the OMDB API for *every single movie* in the list (default limit 1000). The SQLite database already contains the necessary display data (title, genre, poster).
Calling OMDB for 1000 items concurrently caused:
1.  **Network Saturation / OOM:** Creating 1000 SSL connections.
2.  **API Rate Limiting:** Flooding the external provider.

**Correct Logic:**
-   `/movies` (Homepage): Serve purely from local SQLite. Fast, low memory.
-   `/recommend` (AI): Enhance the small result set (top 15-20) with OMDB data if needed.

### B. Unused Heavy Dependency (Secondary Cause)
The `requirements.txt` included `sentence-transformers`. Although the code had already migrated to Google Gemini Embeddings (API-based), this heavy library (PyTorch based) was still being installed. While Python imports are lazy, its presence in the container bloats the image size significantly (~500MB+ for PyTorch) and risks importing heavy shared libraries.

## 3. Resolution
We have applied the following fixes:

1.  **Logic Logic Correction:** Modified `main.py` -> `get_movies` to solely read from the local SQLite database. Removed the concurrent OMDB enrichment loop entirely from this endpoint. This reduces external network calls from 1000 to 0 for the homepage.

2.  **Dependency Cleanup:** Removed `sentence-transformers` from `requirements.txt`.

## 4. Verification
- **Code Audit:** Verified `main.py` ensures a single client is shared.
- **Dependency Check:** Verified `requirements.txt` is clean.

## 5. Lessons Learned
- **Resource Management:** Always reuse heavy objects like HTTP clients and Database connections in high-concurrency loops.
- **Dependency Hygiene:** Regularly prune `requirements.txt` after refactoring code (e.g., removing local ML libraries after switching to APIs).
