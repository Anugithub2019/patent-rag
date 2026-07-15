"""
Celery tasks for PatentRAG async query processing.

Defines the background task that:
1. Receives a job_id and query text
2. Calls the Hashtag AI /query API
3. Parses the response via similarity.py
4. Stores the result in Redis so the HTTP server can serve it
"""
import json
import hashlib
import requests
from backend.celery_app import app
from backend.config import API_KEY, BASE_URL, CACHE_TTL
from backend.similarity import process_query_response
import redis as redis_lib
from backend.config import REDIS_URL

HEADERS = {
    "x-api-key": API_KEY,
    "Content-Type": "application/json"
}

# Redis client for storing results
redis_client = redis_lib.from_url(REDIS_URL)


@app.task(bind=True, max_retries=3, default_retry_delay=10)
def process_query(self, job_id: str, text: str):
    """
    Process a patent novelty search query in the background.

    Args:
        job_id: Unique identifier for this query job.
        text: The technical document text to search against.

    Returns:
        The parsed response dict with results, answer, sources, etc.
    """
    # Compute a cache key based on the query text for deduplication
    query_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cache_key = f"query_cache:{query_hash}"

    # Check if we already have a cached result for this exact query
    cached = redis_client.get(cache_key)
    if cached:
        result_data = json.loads(cached)
        # Store under the job_id so the poller can find it
        redis_client.setex(f"job:{job_id}", CACHE_TTL, json.dumps({
            "status": "complete",
            "data": result_data
        }))
        return result_data

    # Mark as processing in Redis
    redis_client.setex(f"job:{job_id}", CACHE_TTL, json.dumps({
        "status": "pending"
    }))

    try:
        # Call the Hashtag AI /query API
        payload = {"question": text}
        resp = requests.post(
            f"{BASE_URL}/query",
            headers=HEADERS,
            json=payload,
            timeout=120
        )

        if resp.status_code != 200:
            error_msg = f"Backend API returned status {resp.status_code}: {resp.text}"
            # Store the error
            redis_client.setex(f"job:{job_id}", CACHE_TTL, json.dumps({
                "status": "failed",
                "error": error_msg
            }))
            raise Exception(error_msg)

        # Parse the API response using the existing similarity module
        raw_data = resp.json()
        parsed = process_query_response(raw_data)

        # Store the result in both the job-specific key and the cache
        result_json = json.dumps(parsed)
        redis_client.setex(cache_key, CACHE_TTL, result_json)
        redis_client.setex(f"job:{job_id}", CACHE_TTL, json.dumps({
            "status": "complete",
            "data": parsed
        }))

        return parsed

    except requests.exceptions.Timeout:
        error_msg = "Request to backend API timed out"
        redis_client.setex(f"job:{job_id}", CACHE_TTL, json.dumps({
            "status": "failed",
            "error": error_msg
        }))
        raise Exception(error_msg)

    except requests.exceptions.ConnectionError:
        error_msg = "Could not connect to backend API"
        redis_client.setex(f"job:{job_id}", CACHE_TTL, json.dumps({
            "status": "failed",
            "error": error_msg
        }))
        raise Exception(error_msg)

    except Exception as exc:
        # For other errors, retry up to max_retries
        redis_client.setex(f"job:{job_id}", CACHE_TTL, json.dumps({
            "status": "failed",
            "error": str(exc)
        }))
        raise self.retry(exc=exc)