#!/bin/bash

# Config
API_KEY=$HASHTAG_API_KEY
API_URL="https://kg-api.hashtag.ai/fivepatents/query"
QUESTION="Summarize the technology in the patent with ID US20250376069A1"

# Make the request
curl -s -X POST "$API_URL" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"$QUESTION\"}"
