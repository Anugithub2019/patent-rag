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

    return f"""Analyze the following technology disclosure against the retrieved patent context.
Return ONLY valid JSON (no Markdown) with exactly this structure:
{{
  "schema_version": 2,
  "overall_assessment": {{
    "status": "no_single_reference_match" | "potentially_anticipated" | "inconclusive",
    "summary": "non-empty assessment"
  }},
  "features": [
    {{
      "feature_id": 1,
      "feature_text": "non-empty technology feature",
      "matches": [
        {{
          "reference_id": "stable identifier reused for the same patent",
          "patent_id": "patent publication identifier",
          "title": "patent title",
          "status": "disclosed" | "partially_disclosed",
          "disclosure_summary": "non-empty comparison",
          "evidence": [{{"passage": "verbatim supporting passage", "location": "optional claim or paragraph"}}],
          "source_url": "optional http(s) URL"
        }}
      ]
    }}
  ]
}}
Number feature_id values as unique positive JSON integers: 1, 2, 3, and so on. Never return feature_id as a quoted string such as "F1". Never output null. Omit optional location and source_url fields when unavailable. Include a match only when every required match field has a non-empty value; otherwise omit the entire match. Include every material feature from the disclosure and use an empty matches array when no complete, citable match remains. Do not invent evidence, patent identifiers, titles, or URLs. Use inconclusive when the retrieved context is insufficient.

Technology disclosure:
{text}"""
