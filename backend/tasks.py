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
from backend.celery_app import app
from backend.config import BASE_URL, CACHE_TTL, DEBUG_INVALID_REPORTS
from backend.hashtag_client import query_hashtag
from backend.similarity import process_query_response
from backend.contract import ContractError, make_job_result, validate_analysis
import redis as redis_lib
from backend.config import REDIS_URL

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
    # Include the Hashtag destination so switching corpora cannot return a
    # cached report produced from a different knowledge base.
    cache_material = f"{BASE_URL}\0{text}"
    query_hash = hashlib.sha256(cache_material.encode("utf-8")).hexdigest()
    # Version the cache namespace so reports produced by older prompt or
    # contract semantics cannot be returned as current Schema v2 reports.
    cache_key = f"query_cache:v5:{query_hash}"

    # Check if we already have a cached result for this exact query
    cached = redis_client.get(cache_key)
    if cached:
        result_data = validate_analysis(json.loads(cached))
        # Store under the job_id so the poller can find it
        redis_client.setex(f"job:{job_id}", CACHE_TTL, json.dumps(
            make_job_result("complete", data=result_data)
        ))
        return result_data

    # Mark as processing in Redis
    redis_client.setex(f"job:{job_id}", CACHE_TTL, json.dumps(make_job_result("pending")))

    raw_data = None
    try:
        # Call the Hashtag AI /query API via the dedicated client
        raw_data = query_hashtag(text)

        # Parse the API response using the existing similarity module
        parsed = process_query_response(raw_data)

        # Store the result in both the job-specific key and the cache
        result_json = json.dumps(parsed)
        redis_client.setex(cache_key, CACHE_TTL, result_json)
        redis_client.setex(f"job:{job_id}", CACHE_TTL, json.dumps(
            make_job_result("complete", data=parsed)
        ))

        return parsed

    except ContractError as exc:
        error_msg = f"Backend returned an invalid report: {exc}"
        debug = None
        if DEBUG_INVALID_REPORTS:
            debug = {
                "validation_error": str(exc),
                "upstream_response": raw_data,
            }
        redis_client.setex(f"job:{job_id}", CACHE_TTL, json.dumps(
            make_job_result("failed", error=error_msg, debug=debug)
        ))
        raise Exception(error_msg) from exc

    except Exception as exc:
        # Check if this is a timeout/connection error from the requests library
        # (raised by hashtag_client) and treat them as non-retriable failures
        exc_name = type(exc).__name__
        if exc_name == "Timeout":
            error_msg = "Request to backend API timed out"
        elif exc_name == "ConnectionError":
            error_msg = "Could not connect to backend API"
        else:
            # For other errors, retry up to max_retries
            redis_client.setex(f"job:{job_id}", CACHE_TTL, json.dumps(
                make_job_result("failed", error=str(exc))
            ))
            raise self.retry(exc=exc)

        redis_client.setex(f"job:{job_id}", CACHE_TTL, json.dumps(
            make_job_result("failed", error=error_msg)
        ))
        raise Exception(error_msg)
