"""
Query builder for PatentRAG.

Wraps raw user input into a well-formed question for the Hashtag AI API.
If the user only provides a technology description, it is automatically
prepended with a novelty analysis prompt.
"""

# Prefixes that indicate the user input is already a complete question
_QUESTION_PREFIXES = (
    "is there", "what", "find", "summarize",
    "does", "can", "how", "why", "which", "who",
    "list", "tell", "show", "give", "identify",
    "describe", "explain", "compare", "evaluate",
    "search", "retrieve", "do", "are", "will"
)


def build_query(user_text: str) -> str:
    """
    Build a complete query string from raw user input.

    If the input already looks like a question (starts with a known
    question prefix), it is returned unchanged. Otherwise the input
    is treated as a technology description and wrapped in a novelty
    analysis prompt.

    Args:
        user_text: The raw text entered by the user.

    Returns:
        A complete query string ready to send to the Hashtag API.
    """
    text = user_text.strip()
    if not text:
        return ""

    # Check if the input already starts with a question word
    first_word = text.split()[0].lower().rstrip("?,.;:!")
    if first_word in _QUESTION_PREFIXES:
        return text

    # Treat as a technology description and wrap in a novelty question
    return f"Is there any novelty in this technology? Technology draft: {text}"