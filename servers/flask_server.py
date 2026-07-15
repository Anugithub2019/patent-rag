"""
Flask server for PatentRAG with Redis + Celery async query processing.

Endpoints:
  GET  /               - Serve the frontend HTML
  GET  /api/health     - Health check
  POST /api/query      - Submit a query, returns a job_id immediately (HTTP 202)
  GET  /api/result/<job_id> - Poll for job result status
"""
import os
import json
import uuid
import redis as redis_lib
from flask import Flask, request, jsonify, send_from_directory

from backend.config import REDIS_URL, CACHE_TTL

# The Flask app file is in the servers/ directory; serve frontend from ../frontend
frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

app = Flask(__name__, static_folder=frontend_dir)

# Redis client for job status/results
redis_client = redis_lib.from_url(REDIS_URL)


@app.route("/")
def index():
    """Serve the main frontend page."""
    return send_from_directory(frontend_dir, "index.html")


@app.route("/api/query", methods=["POST"])
def submit_query():
    """
    Submit a patent novelty search query asynchronously.

    Accepts JSON: { "text": "the document content" }
    Returns immediately with a job_id for polling.

    A Celery worker picks up the task in the background and stores
    the result in Redis when complete.
    """
    try:
        data = request.get_json()
        if not data or "text" not in data:
            return jsonify({"error": "Missing 'text' field in request body"}), 400

        text = data["text"].strip()
        if not text:
            return jsonify({"error": "'text' field cannot be empty"}), 400

        # Generate a unique job ID
        job_id = str(uuid.uuid4())

        # Store initial pending status in Redis
        job_data = json.dumps({"status": "pending"})
        redis_client.setex(f"job:{job_id}", CACHE_TTL, job_data)

        # Enqueue the Celery task (lazy import to avoid import issues at module level)
        from backend.tasks import process_query
        process_query.delay(job_id, text)

        return jsonify({"job_id": job_id}), 202

    except Exception as e:
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route("/api/result/<job_id>", methods=["GET"])
def get_result(job_id):
    """
    Poll for the result of a previously submitted query.

    Returns:
      - 200 with { "status": "pending" } if still processing
      - 200 with { "status": "complete", "data": {...} } when done
      - 200 with { "status": "failed", "error": "..." } if failed
      - 404 if job_id not found
    """
    try:
        raw = redis_client.get(f"job:{job_id}")
        if raw is None:
            return jsonify({"error": "Job not found"}), 404

        return jsonify(json.loads(raw)), 200

    except Exception as e:
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route("/api/search", methods=["POST"])
def search_prior_art():
    """
    Legacy synchronous search endpoint (kept for backward compatibility).

    Calls the Hashtag AI /query API synchronously and returns the result.
    New clients should use POST /api/query + GET /api/result/<job_id> instead.
    """
    import requests
    from backend.similarity import process_query_response

    try:
        data = request.get_json()
        if not data or "text" not in data:
            return jsonify({"error": "Missing 'text' field in request body"}), 400

        document_text = data["text"]

        from backend.config import API_KEY, BASE_URL
        HEADERS = {
            "x-api-key": API_KEY,
            "Content-Type": "application/json"
        }

        payload = {"question": document_text}

        resp = requests.post(
            f"{BASE_URL}/query",
            headers=HEADERS,
            json=payload,
            timeout=120
        )

        if resp.status_code != 200:
            return jsonify({
                "error": f"Backend API returned status {resp.status_code}",
                "detail": resp.text
            }), resp.status_code

        result_data = resp.json()
        parsed = process_query_response(result_data)

        return jsonify(parsed)

    except requests.exceptions.Timeout:
        return jsonify({"error": "Request to backend API timed out"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to backend API"}), 502
    except Exception as e:
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint that also verifies Redis connectivity."""
    redis_ok = False
    try:
        redis_client.ping()
        redis_ok = True
    except Exception:
        pass

    return jsonify({
        "status": "ok",
        "redis": redis_ok
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print(f"Starting PatentRAG server on http://localhost:{port}")
    print(f"Redis: {REDIS_URL}")
    app.run(host="0.0.0.0", port=port, debug=True)