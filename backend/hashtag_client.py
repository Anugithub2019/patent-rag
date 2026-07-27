"""
Hashtag AI API client for PatentRAG.

Provides a thin wrapper around the Hashtag /query endpoint,
handling authentication, request formatting, and error handling.
"""

import requests
from backend.config import API_KEY, BASE_URL
from backend.query_builder import build_query

HEADERS = {
    "x-api-key": API_KEY,
    "Content-Type": "application/json"
}


def query_hashtag(text: str) -> dict:
    """
    Send a query to the Hashtag AI /query API and return the raw JSON response.

    Args:
        text: The technical document text to search against.

    Returns:
        The parsed JSON response from the API.

    Raises:
        requests.exceptions.Timeout: If the request times out.
        requests.exceptions.ConnectionError: If the connection fails.
        Exception: If the API returns a non-200 status code.
    """
    # Build a complete query from the raw user input
    query = build_query(text)
    payload = {"question": query}
    resp = requests.post(
        f"{BASE_URL}/query",
        headers=HEADERS,
        json=payload,
        timeout=120
    )

    if resp.status_code != 200:
        raise Exception(
            f"Backend API returned status {resp.status_code}: {resp.text}"
        )

    return resp.json()