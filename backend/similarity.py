"""
Similarity processing utilities for PatentRAG.

Handles extraction and transformation of similarity search results
from the Hashtag AI knowledge graph API response.
"""

from typing import Any, Dict, List, Optional, TypedDict


class SimilarityResult(TypedDict):
    """Represents a single similarity search result."""
    patent_id: str
    title: str
    similarity: float
    snippet: str


class ParsedResponse(TypedDict):
    """Parsed and structured response from the similarity API."""
    results: List[SimilarityResult]
    answer: str
    sources: List[str]
    total_results: int


def extract_chunk_details(response_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract the list of chunk detail objects from the raw API response.

    The Hashtag AI /query endpoint returns results nested under
    info -> nodedetails -> chunkdetails.

    Args:
        response_data: The raw JSON response from the Hashtag AI API.

    Returns:
        A list of chunk detail dictionaries, each containing at least
        'id' and 'score' keys. Returns an empty list if the path
        doesn't exist or is malformed.
    """
    info = response_data.get("info", {})
    nodedetails = info.get("nodedetails", {})
    chunk_details = nodedetails.get("chunkdetails", [])
    return chunk_details if isinstance(chunk_details, list) else []


def extract_sources(response_data: Dict[str, Any]) -> List[str]:
    """
    Extract the list of source document IDs from the raw API response.

    Args:
        response_data: The raw JSON response from the Hashtag AI API.

    Returns:
        A list of source document identifier strings.
    """
    info = response_data.get("info", {})
    sources = info.get("sources", [])
    return sources if isinstance(sources, list) else []


def extract_answer(response_data: Dict[str, Any]) -> str:
    """
    Extract the generated answer text from the raw API response.

    Args:
        response_data: The raw JSON response from the Hashtag AI API.

    Returns:
        The answer string, or an empty string if not present.
    """
    return response_data.get("answer", "") or ""


def build_patent_title(chunk_id: str, max_chars: int = 12) -> str:
    """
    Build a human-readable title for a patent chunk.

    Args:
        chunk_id: The raw chunk identifier hash.
        max_chars: Number of characters to show from the beginning of the ID.

    Returns:
        A formatted title string like "Patent Document (chunk: a1b2c3d4e5f6...)".
    """
    truncated = chunk_id[:max_chars] if chunk_id else "unknown"
    return f"Patent Document (chunk: {truncated}...)"


def parse_similarity_chunk(chunk: Dict[str, Any]) -> SimilarityResult:
    """
    Convert a single raw chunk detail dict into a structured SimilarityResult.

    Args:
        chunk: A dictionary with at least 'id' and 'score' keys.

    Returns:
        A SimilarityResult dict with patent_id, title, similarity, and snippet.
    """
    chunk_id = chunk.get("id", "unknown")
    return SimilarityResult(
        patent_id=chunk_id,
        title=build_patent_title(chunk_id),
        similarity=float(chunk.get("score", 0)),
        snippet=chunk.get("text", "") or ""
    )


def sort_by_similarity_desc(results: List[SimilarityResult]) -> List[SimilarityResult]:
    """
    Sort a list of SimilarityResult objects by similarity score descending
    (highest similarity first).

    Args:
        results: A list of SimilarityResult dicts.

    Returns:
        A new list sorted by similarity in descending order.
    """
    return sorted(results, key=lambda x: x["similarity"], reverse=True)


def process_query_response(response_data: Dict[str, Any]) -> ParsedResponse:
    """
    Process the raw Hashtag AI /query API response into a structured,
    frontend-friendly format.

    This is the main orchestration function that:
    1. Extracts chunk details, sources, and answer from the raw response.
    2. Transforms each chunk into a SimilarityResult.
    3. Sorts results by similarity (highest first).
    4. Packages everything into a ParsedResponse.

    Args:
        response_data: The raw JSON response from the Hashtag AI /query endpoint.

    Returns:
        A ParsedResponse dict containing:
        - results: list of SimilarityResult (sorted by similarity descending)
        - answer: the generated answer text
        - sources: list of source document IDs
        - total_results: number of results found
    """
    chunk_details = extract_chunk_details(response_data)
    sources = extract_sources(response_data)
    answer = extract_answer(response_data)

    # Transform each raw chunk into a structured SimilarityResult
    results = [parse_similarity_chunk(chunk) for chunk in chunk_details]

    # Sort by similarity score descending
    results = sort_by_similarity_desc(results)

    return ParsedResponse(
        results=results,
        answer=answer,
        sources=sources,
        total_results=len(results)
    )