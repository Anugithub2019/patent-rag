#!/bin/bash
# Quick test of Hashtag retrieval.

set -euo pipefail

# Config
API_KEY=${HASHTAG_API_KEY:-}
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CONFIG_FILE="$SCRIPT_DIR/query_config.json"
CONFIGURED_NAMESPACE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["namespace"])' "$CONFIG_FILE")
CONFIGURED_PROJECT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["corpus_name"])' "$CONFIG_FILE")
NAMESPACE=${QUERY_HASHTAG_NAMESPACE:-$CONFIGURED_NAMESPACE}
PROJECT=${QUERY_HASHTAG_CORPUS_NAME:-$CONFIGURED_PROJECT}
API_BASE=${HASHTAG_BASE_URL:-https://kg-api.hashtag.ai}
API_URL="${API_BASE%/}/${NAMESPACE}/${PROJECT}/query"
MODE="graph_vector_fulltext"
QUESTION="Find patents that include this technology and give me its PATENT_ID. List all features of this technology. If equavalent feature exists in found patents, list it too. Finally, evaluate if there is any novelty in this technology:"
TECHNOLOGY_DESCRIPTION="A battery disconnect assembly for an electric vehicle comprises a first power contact arranged in a low-voltage supply line and configurable between a conductive state and a non-conductive state. A second power contact is provided in the supply circuit and is movable between a normally closed condition and an open condition. The assembly further includes an interlock contact connected to a high-voltage interlock loop (HVIL), the interlock contact being movable between an enabled state that maintains the HVIL circuit and a disabled state that breaks the HVIL circuit, thereby causing shutdown of the vehicle's high-voltage propulsion system. A manually operable disconnect handle is coupled to the interlock contact and is configured to disable the HVIL circuit before isolation of the battery. A control and monitoring module detects interruption of the HVIL circuit and, in response, commands the first and second power contacts to transition to their open states, electrically isolating the onboard battery from vehicle loads."
#QUESTION="Summarize patent US20250378614A1"
#QUESTION="Summarize the technology in patent with PATENT_ID US20250376069A1."
#QUESTION="Is there any novelty in this technology? Technology draft: A battery disconnect assembly for an electric vehicle comprises a first power contact arranged in a low-voltage supply line and configurable between a conductive state and a non-conductive state. A second power contact is provided in the supply circuit and is movable between a normally closed condition and an open condition. The assembly further includes an interlock contact connected to a high-voltage interlock loop (HVIL), the interlock contact being movable between an enabled state that maintains the HVIL circuit and a disabled state that breaks the HVIL circuit, thereby causing shutdown of the vehicle's high-voltage propulsion system. A manually operable disconnect handle is coupled to the interlock contact and is configured to disable the HVIL circuit before isolation of the battery. A control and monitoring module detects interruption of the HVIL circuit and, in response, commands the first and second power contacts to transition to their open states, electrically isolating the onboard battery from vehicle loads."

OUTPUT_MODE="readable"
REQUEST_QUESTION="$QUESTION $TECHNOLOGY_DESCRIPTION"

usage() {
  echo "Usage: $0 [--question \"QUESTION\"] [--raw]"
  echo "  -q, --question  Send a free-form question instead of the default novelty query."
  echo "  --raw           Print the complete API response as formatted JSON."
}

while (($#)); do
  case "$1" in
    -q|--question)
      if (($# < 2)) || [[ -z "$2" ]]; then
        echo "--question requires a non-empty value." >&2
        usage >&2
        exit 2
      fi
      REQUEST_QUESTION=$2
      shift 2
      ;;
    --raw)
      OUTPUT_MODE="raw"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$API_KEY" ]]; then
  echo "HASHTAG_API_KEY is not set." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to build and format the JSON response." >&2
  exit 1
fi

REQUEST_BODY=$(jq -n \
  --arg question "$REQUEST_QUESTION" \
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
