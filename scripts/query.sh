#!/bin/bash
# This is to quick test retrivial of hashtag
# Config
API_KEY=$HASHTAG_API_KEY
#PROJECT="patentrag"
PROJECT="test_two_patents"
API_URL="https://kg-api.hashtag.ai/${PROJECT}/query"
MODE="graph_vector_fulltext"
QUESTION="Find patents that include this technology and give me its PATENT_ID: A battery disconnect assembly for an electric vehicle comprises a first power contact arranged in a low-voltage supply line and configurable between a conductive state and a non-conductive state. A second power contact is provided in the supply circuit and is movable between a normally closed condition and an open condition. The assembly further includes an interlock contact connected to a high-voltage interlock loop (HVIL), the interlock contact being movable between an enabled state that maintains the HVIL circuit and a disabled state that breaks the HVIL circuit, thereby causing shutdown of the vehicle's high-voltage propulsion system. A manually operable disconnect handle is coupled to the interlock contact and is configured to disable the HVIL circuit before isolation of the battery. A control and monitoring module detects interruption of the HVIL circuit and, in response, commands the first and second power contacts to transition to their open states, electrically isolating the onboard battery from vehicle loads."
#QUESTION="Summarize patent US20250378614A1"
#QUESTION="Summarize the technology in patent with PATENT_ID US20250376069A1."
#QUESTION="Is there any novelty in this technology? Technology draft: A battery disconnect assembly for an electric vehicle comprises a first power contact arranged in a low-voltage supply line and configurable between a conductive state and a non-conductive state. A second power contact is provided in the supply circuit and is movable between a normally closed condition and an open condition. The assembly further includes an interlock contact connected to a high-voltage interlock loop (HVIL), the interlock contact being movable between an enabled state that maintains the HVIL circuit and a disabled state that breaks the HVIL circuit, thereby causing shutdown of the vehicle's high-voltage propulsion system. A manually operable disconnect handle is coupled to the interlock contact and is configured to disable the HVIL circuit before isolation of the battery. A control and monitoring module detects interruption of the HVIL circuit and, in response, commands the first and second power contacts to transition to their open states, electrically isolating the onboard battery from vehicle loads."

# Make the request
curl -s -X POST "$API_URL" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -H "mode: $MODE" \
  -d "{\"question\": \"$QUESTION\"}"
