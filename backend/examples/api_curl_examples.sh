#!/bin/bash
#
# BRD Generator API - cURL Examples
#
# This script demonstrates the four-phase BRD generation workflow using cURL.
#
# Prerequisites:
# - Start the API server: brd-api or uvicorn brd_generator.api.app:app --reload
# - API available at: http://localhost:8000
#
# Usage:
# - Run each phase separately and review output before proceeding
# - Save intermediate results to JSON files for the next phase

BASE_URL="http://localhost:8000/api/v1"

echo "============================================================"
echo " BRD Generator API - cURL Examples"
echo "============================================================"

# ==============================================================================
# Health Check
# ==============================================================================
echo ""
echo "=== Health Check ==="
curl -s "${BASE_URL}/health" | jq .

# ==============================================================================
# PHASE 1: Generate BRD (with Multi-Agent Verification)
# ==============================================================================
echo ""
echo "============================================================"
echo " PHASE 1: Generate BRD (Multi-Agent Verification)"
echo "============================================================"

# Note: Replace {repository_id} with an actual repository ID
REPOSITORY_ID="${REPOSITORY_ID:-your-repository-id}"

# Request with verification settings
cat > /tmp/brd_request.json << 'EOF'
{
  "feature_description": "Add a caching layer to improve API response times for frequently accessed data",
  "affected_components": ["api-service", "cache-service", "database"],
  "include_similar_features": true,
  "max_iterations": 3,
  "min_confidence": 0.7,
  "show_evidence": false,
  "template_config": {
    "organization_name": "Acme Corp",
    "document_prefix": "ACME-BRD",
    "require_approvals": true,
    "approval_roles": ["Product Owner", "Tech Lead", "Architect"],
    "include_risk_matrix": true,
    "custom_sections": ["Security Review"]
  }
}
EOF

echo "Request:"
cat /tmp/brd_request.json | jq .

echo ""
echo "Sending request to POST /brd/generate/${REPOSITORY_ID}..."
echo "Note: This endpoint streams via SSE. Using curl to capture complete response..."

# Stream the SSE response and capture the complete event
curl -s -N -X POST "${BASE_URL}/brd/generate/${REPOSITORY_ID}" \
  -H "Content-Type: application/json" \
  -d @/tmp/brd_request.json 2>/dev/null | while IFS= read -r line; do
    if [[ "$line" == data:* ]]; then
      data="${line#data: }"
      event_type=$(echo "$data" | jq -r '.type // empty' 2>/dev/null)
      if [[ "$event_type" == "complete" ]]; then
        echo "$data" | jq '.data' > /tmp/brd_response.json
        echo "Complete response captured!"
      elif [[ "$event_type" == "thinking" ]]; then
        content=$(echo "$data" | jq -r '.content // empty' 2>/dev/null)
        echo "  $content"
      fi
    fi
done

echo ""
echo "Response saved to /tmp/brd_response.json"
echo ""
echo "BRD Summary:"
cat /tmp/brd_response.json | jq '{
  id: .brd.id,
  title: .brd.title,
  is_verified: .is_verified,
  confidence_score: .confidence_score,
  hallucination_risk: .hallucination_risk,
  iterations_used: .iterations_used,
  functional_requirements: (.brd.functional_requirements | length),
  technical_requirements: (.brd.technical_requirements | length),
  risks: (.brd.risks | length)
}'

echo ""
echo "⏸️  USER REVIEW: Review /tmp/brd_response.json and approve to continue"
echo "   View BRD markdown: cat /tmp/brd_response.json | jq -r '.brd.markdown'"

# ==============================================================================
# PHASE 2: Generate Epics
# ==============================================================================
echo ""
echo "============================================================"
echo " PHASE 2: Generate Epics from BRD"
echo "============================================================"

# Extract BRD from response for next phase
cat /tmp/brd_response.json | jq '{brd: .brd, use_skill: true}' > /tmp/epics_request.json

echo "Request (using BRD from Phase 1):"
cat /tmp/epics_request.json | jq '{brd_id: .brd.id, brd_title: .brd.title}'

echo ""
echo "Sending request..."
curl -s -X POST "${BASE_URL}/epics/generate" \
  -H "Content-Type: application/json" \
  -d @/tmp/epics_request.json > /tmp/epics_response.json

echo "Response saved to /tmp/epics_response.json"
echo ""
echo "Epics Summary:"
cat /tmp/epics_response.json | jq '{
  brd_id: .brd_id,
  total_epics: (.epics | length),
  implementation_order: .implementation_order,
  epics: [.epics[] | {id, title, priority, effort: .estimated_effort}]
}'

echo ""
echo "⏸️  USER REVIEW: Review /tmp/epics_response.json and approve to continue"

# ==============================================================================
# PHASE 3: Generate Backlogs
# ==============================================================================
echo ""
echo "============================================================"
echo " PHASE 3: Generate Backlogs from Epics"
echo "============================================================"

# Combine BRD and Epics for next phase
jq -s '{brd: .[0].brd, epics: .[1].epics, use_skill: true}' \
  /tmp/brd_response.json /tmp/epics_response.json > /tmp/backlogs_request.json

echo "Request (using BRD and Epics from previous phases):"
cat /tmp/backlogs_request.json | jq '{
  brd_id: .brd.id,
  epic_count: (.epics | length)
}'

echo ""
echo "Sending request..."
curl -s -X POST "${BASE_URL}/backlogs/generate" \
  -H "Content-Type: application/json" \
  -d @/tmp/backlogs_request.json > /tmp/backlogs_response.json

echo "Response saved to /tmp/backlogs_response.json"
echo ""
echo "Backlogs Summary:"
cat /tmp/backlogs_response.json | jq '{
  total_stories: (.stories | length),
  total_story_points: .total_story_points,
  implementation_order: (.implementation_order | .[0:5]),
  stories_by_epic: [.epics[] | {
    epic: .id,
    story_count: ([.id as $eid | $ARGS.named.stories[] | select(.epic_id == $eid)] | length)
  }]
}' --argjson stories "$(cat /tmp/backlogs_response.json | jq '.stories')"

echo ""
echo "⏸️  USER REVIEW: Review /tmp/backlogs_response.json and approve to continue"

# ==============================================================================
# PHASE 4: Create JIRA Issues
# ==============================================================================
echo ""
echo "============================================================"
echo " PHASE 4: Create JIRA Issues"
echo "============================================================"

# Combine Epics and Stories for JIRA creation
jq -s '{
  project_key: "DEMO",
  epics: .[0].epics,
  stories: .[0].stories,
  use_skill: true,
  labels: ["brd-generated", "api-caching"]
}' /tmp/backlogs_response.json > /tmp/jira_request.json

echo "Request:"
cat /tmp/jira_request.json | jq '{
  project_key: .project_key,
  epic_count: (.epics | length),
  story_count: (.stories | length),
  labels: .labels
}'

echo ""
echo "Sending request..."
curl -s -X POST "${BASE_URL}/jira/create" \
  -H "Content-Type: application/json" \
  -d @/tmp/jira_request.json > /tmp/jira_response.json

echo "Response saved to /tmp/jira_response.json"
echo ""
echo "JIRA Summary:"
cat /tmp/jira_response.json | jq '{
  success: .success,
  project_key: .project_key,
  total_created: .total_created,
  total_failed: .total_failed,
  errors: .errors
}'

# ==============================================================================
# Summary
# ==============================================================================
echo ""
echo "============================================================"
echo " WORKFLOW COMPLETE"
echo "============================================================"
echo ""
echo "Files created:"
echo "  - /tmp/brd_request.json      (Phase 1 request)"
echo "  - /tmp/brd_response.json     (Phase 1 response - BRD)"
echo "  - /tmp/epics_request.json    (Phase 2 request)"
echo "  - /tmp/epics_response.json   (Phase 2 response - Epics)"
echo "  - /tmp/backlogs_request.json (Phase 3 request)"
echo "  - /tmp/backlogs_response.json (Phase 3 response - Stories)"
echo "  - /tmp/jira_request.json     (Phase 4 request)"
echo "  - /tmp/jira_response.json    (Phase 4 response - JIRA)"
echo ""
echo "View BRD markdown:"
echo "  cat /tmp/brd_response.json | jq -r '.brd.markdown'"
echo ""
echo "View all stories:"
echo "  cat /tmp/backlogs_response.json | jq '.stories[] | {id, title, points: .estimated_points}'"
