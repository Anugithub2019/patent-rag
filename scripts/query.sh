#!/bin/bash
# Quick test of Hashtag retrieval.

set -euo pipefail

# Config
API_KEY=${HASHTAG_API_KEY:-}
#PROJECT="patentrag"
PROJECT="test_two_patents"
API_URL="https://kg-api.hashtag.ai/${PROJECT}/query"
MODE="graph_vector_fulltext"
QUESTION="Find patents that include this technology and give me its PATENT_ID. List all features of this technology. If equavalent feature exists in found patents, list it too. Finally, evaluate if there is any novelty in this technology:"
TECHNOLOGY_DESCRIPTION="A battery disconnect assembly for an electric vehicle comprises a first power contact arranged in a low-voltage supply line and configurable between a conductive state and a non-conductive state. A second power contact is provided in the supply circuit and is movable between a normally closed condition and an open condition. The assembly further includes an interlock contact connected to a high-voltage interlock loop (HVIL), the interlock contact being movable between an enabled state that maintains the HVIL circuit and a disabled state that breaks the HVIL circuit, thereby causing shutdown of the vehicle's high-voltage propulsion system. A manually operable disconnect handle is coupled to the interlock contact and is configured to disable the HVIL circuit before isolation of the battery. A control and monitoring module detects interruption of the HVIL circuit and, in response, commands the first and second power contacts to transition to their open states, electrically isolating the onboard battery from vehicle loads."
#QUESTION="Summarize patent US20250378614A1"
#QUESTION="Summarize the technology in patent with PATENT_ID US20250376069A1."
#QUESTION="Is there any novelty in this technology? Technology draft: A battery disconnect assembly for an electric vehicle comprises a first power contact arranged in a low-voltage supply line and configurable between a conductive state and a non-conductive state. A second power contact is provided in the supply circuit and is movable between a normally closed condition and an open condition. The assembly further includes an interlock contact connected to a high-voltage interlock loop (HVIL), the interlock contact being movable between an enabled state that maintains the HVIL circuit and a disabled state that breaks the HVIL circuit, thereby causing shutdown of the vehicle's high-voltage propulsion system. A manually operable disconnect handle is coupled to the interlock contact and is configured to disable the HVIL circuit before isolation of the battery. A control and monitoring module detects interruption of the HVIL circuit and, in response, commands the first and second power contacts to transition to their open states, electrically isolating the onboard battery from vehicle loads."

OUTPUT_MODE="readable"

case "${1:-}" in
  "") ;;
  --raw) OUTPUT_MODE="raw" ;;
  -h|--help)
    echo "Usage: $0 [--raw]"
    echo "  --raw  Print the complete API response as formatted JSON."
    exit 0
    ;;
  *)
    echo "Unknown option: $1" >&2
    echo "Usage: $0 [--raw]" >&2
    exit 2
    ;;
esac

if [[ -z "$API_KEY" ]]; then
  echo "HASHTAG_API_KEY is not set." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to build and format the JSON response." >&2
  exit 1
fi

REQUEST_BODY=$(jq -n \
  --arg question "$QUESTION $TECHNOLOGY_DESCRIPTION" \
  '{question: $question}')

# Make the request. Keep the response so curl failures are reported before jq runs.
RESPONSE=$(curl -sS --fail-with-body -X POST "$API_URL" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -H "mode: $MODE" \
  -d "$REQUEST_BODY")

if [[ "$OUTPUT_MODE" == "raw" ]]; then
  jq . <<<"$RESPONSE"
  exit 0
fi

echo "ANSWER"
echo "======"
jq -r '.answer' <<<"$RESPONSE"

echo
echo "INFO"
echo "===="
jq '.info' <<<"$RESPONSE"
