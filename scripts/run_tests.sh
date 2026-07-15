#!/bin/bash
# Workflow: test multiple Hashtag AI projects against the same set of questions
#
# USAGE:
#   1. Edit the PROJECTS and QUESTIONS arrays below.
#   2. Run: bash run_tests.sh
#   3. Results are saved under ./tests/<project>/q<N>.json
#      and a combined summary is printed to stdout + saved to ./tests/summary.txt
#
# Requires: HASHTAG_API_KEY to be set in your environment
#   export HASHTAG_API_KEY="your-key-here"

set -uo pipefail

# ---------- CONFIG: edit these ----------
PROJECTS=(
  "fivepatents"
  "patentrag"
)

QUESTIONS=(
  "How many patents are there in the knowledge database?"
  "Summarize patent US20250378614A1"
  "Summarize patent US20250376069A1"
  "Summarize the technology in patent US20250376069A1"
  "Find patents in your knowledge database that include these and give me its identification: A battery disconnect assembly for an electric vehicle comprises a first power contact arranged in a low-voltage supply line and configurable between a conductive state and a non-conductive state. A second power contact is provided in the supply circuit and is movable between a normally closed condition and an open condition. The assembly further includes an interlock contact connected to a high-voltage interlock loop (HVIL), the interlock contact being movable between an enabled state that maintains the HVIL circuit and a disabled state that breaks the HVIL circuit, thereby causing shutdown of the vehicle's high-voltage propulsion system. A manually operable disconnect handle is coupled to the interlock contact and is configured to disable the HVIL circuit before isolation of the battery. A control and monitoring module detects interruption of the HVIL circuit and, in response, commands the first and second power contacts to transition to their open states, electrically isolating the onboard battery from vehicle loads."
)

MODE="graph_vector_fulltext"
API_BASE="https://kg-api.hashtag.ai"
# -----------------------------------------

API_KEY="${HASHTAG_API_KEY:-}"
if [[ -z "$API_KEY" ]]; then
  echo "ERROR: HASHTAG_API_KEY is not set. Run: export HASHTAG_API_KEY=your-key" >&2
  exit 1
fi

OUT_DIR="./tests"
SUMMARY_FILE="$OUT_DIR/summary.txt"
mkdir -p "$OUT_DIR"
: > "$SUMMARY_FILE"

# Helper to JSON-escape the question for the request body
json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"
}

for PROJECT in "${PROJECTS[@]}"; do
  PROJECT_DIR="$OUT_DIR/$PROJECT"
  mkdir -p "$PROJECT_DIR"
  API_URL="${API_BASE}/${PROJECT}/query"

  echo "=== Project: $PROJECT ===" | tee -a "$SUMMARY_FILE"

  for i in "${!QUESTIONS[@]}"; do
    QUESTION="${QUESTIONS[$i]}"
    QNUM=$((i + 1))
    OUT_FILE="$PROJECT_DIR/q${QNUM}.json"

    ESCAPED_Q=$(json_escape "$QUESTION")
    BODY="{\"question\": ${ESCAPED_Q}}"

    echo "--- Q${QNUM}: $QUESTION" | tee -a "$SUMMARY_FILE"

    RESPONSE=$(curl -s -X POST "$API_URL" \
      -H "x-api-key: $API_KEY" \
      -H "Content-Type: application/json" \
      -H "mode: $MODE" \
      -d "$BODY")

    echo "$RESPONSE" > "$OUT_FILE"
    echo "$RESPONSE" | tee -a "$SUMMARY_FILE"
    echo "" | tee -a "$SUMMARY_FILE"
  done
  echo "" | tee -a "$SUMMARY_FILE"
done

echo "Done. Individual responses in $OUT_DIR/<project>/qN.json, full log in $SUMMARY_FILE"