"""Parse Hashtag AI responses into the public Schema v2 analysis contract."""

from typing import Any, Dict

from backend.contract import parse_analysis_response


def process_query_response(response_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and validate the Schema v2 analysis returned by Hashtag AI.

    Args:
        response_data: The raw JSON response from the Hashtag AI /query endpoint.

    Returns:
        A validated Schema v2 report containing overall_assessment and features.
    """
    return parse_analysis_response(response_data)
