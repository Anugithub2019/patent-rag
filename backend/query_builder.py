"""Build the structured novelty-analysis prompt sent to Hashtag AI."""


def build_query(user_text: str) -> str:
    """
    Wrap a non-empty technology disclosure in the required Schema v2 prompt.

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
