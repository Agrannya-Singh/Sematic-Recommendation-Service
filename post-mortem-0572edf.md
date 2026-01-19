# Post-Mortem: OOM Error in Semantic-Recommendation-Service

**Incident ID:** OOM-2026-01-19
**Date:** 2026-01-19
**Repository Hash:** `0572edf`
**Impact:** Service crashed due to Out Of Memory (OOM) error on 512MB instances.

## 1. Issue Description
The application process was killed by the kernel for exceeding the 512MB memory limit. This occurred primarily during requests to the `/movies` endpoint.

## 2. Root Cause Analysis
Investigating the code revealed two main contributors:

### A. Excessive HTTP Client Creation (Primary Cause)
The `/movies` endpoint fetches 1000 movies from SQLite and then enriches them *concurrently* with data from OMDB.
The original code in `main.py` was:
```python
async def enrich_movie(row):
    # ...
    async with httpx.AsyncClient() as client: # <--- NEW CLIENT PER MOVIE
        await client.get(...)
```
With `limit=1000` (default), this spawned **1000 concurrent `httpx.AsyncClient` instances**.
Each client maintains its own connection pool, SSL context, and buffers. This massive overhead easily exceeded the 512MB RAM limit.

### B. Unused Heavy Dependency (Secondary Cause)
The `requirements.txt` included `sentence-transformers`. Although the code had already migrated to Google Gemini Embeddings (API-based), this heavy library (PyTorch based) was still being installed. While Python imports are lazy, its presence in the container bloats the image size significantly (~500MB+ for PyTorch) and risks importing heavy shared libraries.

## 3. Resolution
We have applied the following fixes:

1.  **Shared HTTP Client:** Refactored `main.py` to create a *single* `httpx.AsyncClient` context manager per request and pass it to all concurrent enrichment tasks.
    ```python
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(enrich_movie(client, row) for row in rows))
    ```
    This reduces overhead from 1000 clients to 1 client, drastically reducing memory footprint.

2.  **Dependency Cleanup:** Removed `sentence-transformers` from `requirements.txt`.

## 4. Verification
- **Code Audit:** Verified `main.py` ensures a single client is shared.
- **Dependency Check:** Verified `requirements.txt` is clean.

## 5. Lessons Learned
- **Resource Management:** Always reuse heavy objects like HTTP clients and Database connections in high-concurrency loops.
- **Dependency Hygiene:** Regularly prune `requirements.txt` after refactoring code (e.g., removing local ML libraries after switching to APIs).
