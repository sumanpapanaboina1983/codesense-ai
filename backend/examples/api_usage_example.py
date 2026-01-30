#!/usr/bin/env python3
"""
Example: Using the BRD Generator REST API

This example demonstrates how to use the four-phase BRD Generator API
to generate BRDs, Epics, Backlogs, and create JIRA issues.

Prerequisites:
- Start the API server: `brd-api` or `uvicorn brd_generator.api.app:app --reload`
- API available at: http://localhost:8000

API Documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
"""

import httpx
import json
from typing import Any


BASE_URL = "http://localhost:8000/api/v1"


def print_json(data: Any, title: str = "") -> None:
    """Pretty print JSON data."""
    if title:
        print(f"\n{'=' * 60}")
        print(f" {title}")
        print('=' * 60)
    print(json.dumps(data, indent=2, default=str))


async def main():
    """Demonstrate the four-phase API workflow."""

    async with httpx.AsyncClient(timeout=300.0) as client:

        # ======================================================================
        # Health Check
        # ======================================================================
        print("\n" + "=" * 60)
        print(" Health Check")
        print("=" * 60)

        response = await client.get(f"{BASE_URL}/health")
        print_json(response.json())

        # ======================================================================
        # PHASE 1: Generate BRD (with Multi-Agent Verification)
        # ======================================================================
        print("\n" + "=" * 60)
        print(" PHASE 1: Generate BRD (Multi-Agent Verification)")
        print("=" * 60)

        # First, get a repository ID (you'll need an onboarded repository)
        repos_response = await client.get(f"{BASE_URL}/repositories", params={"analysis_status": "completed", "limit": 1})
        repos = repos_response.json().get("data", [])

        if not repos:
            print("\nNo repositories with completed analysis found.")
            print("Please onboard and analyze a repository first.")
            return

        repository_id = repos[0]["id"]
        repository_name = repos[0]["name"]
        print(f"\nUsing repository: {repository_name} ({repository_id})")

        brd_request = {
            "feature_description": "Add a caching layer to improve API response times for frequently accessed data",
            "affected_components": ["api-service", "cache-service", "database"],
            "include_similar_features": True,
            "max_iterations": 3,
            "min_confidence": 0.7,
            "show_evidence": False,
            "template_config": {
                "organization_name": "Acme Corp",
                "document_prefix": "ACME-BRD",
                "require_approvals": True,
                "approval_roles": ["Product Owner", "Tech Lead", "Architect"],
                "include_risk_matrix": True,
                "custom_sections": ["Security Review", "Performance Baseline"]
            }
        }

        print("\nRequest:")
        print_json(brd_request)

        # Stream the BRD generation (SSE endpoint)
        print("\nStreaming BRD generation...")
        brd_response = None

        async with client.stream(
            "POST",
            f"{BASE_URL}/brd/generate/{repository_id}",
            json=brd_request,
            timeout=300.0
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data.get("type") == "thinking":
                        print(f"  {data.get('content', '')}")
                    elif data.get("type") == "complete":
                        brd_response = data.get("data", {})
                        print("\n  Generation complete!")

        if not brd_response:
            print("Failed to generate BRD")
            return

        print("\nResponse (BRD):")
        print(f"  Title: {brd_response['brd']['title']}")
        print(f"  ID: {brd_response['brd']['id']}")
        print(f"  Is Verified: {brd_response.get('is_verified', False)}")
        print(f"  Confidence Score: {brd_response.get('confidence_score', 0):.2%}")
        print(f"  Hallucination Risk: {brd_response.get('hallucination_risk', 'unknown')}")
        print(f"  Iterations Used: {brd_response.get('iterations_used', 0)}")
        print(f"  Functional Requirements: {len(brd_response['brd']['functional_requirements'])}")
        print(f"  Technical Requirements: {len(brd_response['brd']['technical_requirements'])}")
        print(f"  Risks: {len(brd_response['brd']['risks'])}")

        # Store BRD for next phase
        approved_brd = brd_response["brd"]

        print("\n⏸️  USER REVIEW: Review the BRD above and approve to continue")
        # In real usage, user would review and potentially modify

        # ======================================================================
        # PHASE 2: Generate Epics
        # ======================================================================
        print("\n" + "=" * 60)
        print(" PHASE 2: Generate Epics from BRD")
        print("=" * 60)

        epics_request = {
            "brd": approved_brd,
            "use_skill": True
        }

        response = await client.post(f"{BASE_URL}/epics/generate", json=epics_request)
        epics_response = response.json()

        print("\nResponse (Epics):")
        print(f"  BRD ID: {epics_response['brd_id']}")
        print(f"  Total Epics: {len(epics_response['epics'])}")
        print(f"  Implementation Order: {epics_response['implementation_order']}")

        for epic in epics_response["epics"]:
            print(f"\n  {epic['id']}: {epic['title']}")
            print(f"    Priority: {epic['priority']} | Effort: {epic['estimated_effort']}")
            print(f"    Components: {', '.join(epic['components']) or 'N/A'}")
            print(f"    Blocked by: {', '.join(epic['blocked_by']) or 'None'}")

        # Store Epics for next phase
        approved_epics = epics_response["epics"]

        print("\n⏸️  USER REVIEW: Review the Epics above and approve to continue")

        # ======================================================================
        # PHASE 3: Generate Backlogs
        # ======================================================================
        print("\n" + "=" * 60)
        print(" PHASE 3: Generate Backlogs from Epics")
        print("=" * 60)

        backlogs_request = {
            "brd": approved_brd,
            "epics": approved_epics,
            "use_skill": True
        }

        response = await client.post(f"{BASE_URL}/backlogs/generate", json=backlogs_request)
        backlogs_response = response.json()

        print("\nResponse (Backlogs):")
        print(f"  Total Stories: {len(backlogs_response['stories'])}")
        print(f"  Total Story Points: {backlogs_response['total_story_points']}")
        print(f"  Implementation Order: {backlogs_response['implementation_order'][:5]}...")

        # Group by epic
        for epic in backlogs_response["epics"]:
            stories = [s for s in backlogs_response["stories"] if s["epic_id"] == epic["id"]]
            print(f"\n  {epic['id']}: {epic['title']} ({len(stories)} stories)")
            for story in stories:
                points = story.get("estimated_points", "?")
                blocked = f" [blocked by {', '.join(story['blocked_by'])}]" if story["blocked_by"] else ""
                print(f"    📌 {story['id']}: {story['title']} ({points} pts){blocked}")

        # Store Backlogs for next phase
        approved_stories = backlogs_response["stories"]

        print("\n⏸️  USER REVIEW: Review the Stories above and approve to continue")

        # ======================================================================
        # PHASE 4: Create JIRA Issues (Optional)
        # ======================================================================
        print("\n" + "=" * 60)
        print(" PHASE 4: Create JIRA Issues")
        print("=" * 60)

        jira_request = {
            "project_key": "DEMO",
            "epics": approved_epics,
            "stories": approved_stories,
            "use_skill": True,
            "labels": ["brd-generated", "api-caching"]
        }

        print("\nRequest:")
        print(f"  Project: {jira_request['project_key']}")
        print(f"  Epics: {len(jira_request['epics'])}")
        print(f"  Stories: {len(jira_request['stories'])}")

        # Note: This will fail if Atlassian MCP is not configured
        try:
            response = await client.post(f"{BASE_URL}/jira/create", json=jira_request)
            jira_response = response.json()

            if jira_response.get("success"):
                print("\nResponse (JIRA):")
                print(f"  Created: {jira_response['total_created']}")
                print(f"  Failed: {jira_response['total_failed']}")

                for epic in jira_response.get("epics_created", []):
                    print(f"  Epic: {epic['local_id']} → {epic.get('jira_key', 'N/A')}")

                for story in jira_response.get("stories_created", [])[:5]:
                    print(f"  Story: {story['local_id']} → {story.get('jira_key', 'N/A')}")
            else:
                print(f"\n⚠️  JIRA creation not available: {jira_response.get('errors', [])}")

        except Exception as e:
            print(f"\n⚠️  JIRA creation failed: {e}")
            print("    Ensure MCP_ATLASSIAN_ENABLED=true and credentials are configured")

        # ======================================================================
        # Summary
        # ======================================================================
        print("\n" + "=" * 60)
        print(" WORKFLOW COMPLETE")
        print("=" * 60)

        print(f"""
Summary:
- Phase 1: Generated BRD with {len(approved_brd['functional_requirements'])} requirements
- Phase 2: Generated {len(approved_epics)} Epics
- Phase 3: Generated {len(approved_stories)} User Stories ({backlogs_response['total_story_points']} points)
- Phase 4: JIRA creation (requires Atlassian MCP configuration)

API Endpoints Used:
- POST /api/v1/brd/generate
- POST /api/v1/epics/generate
- POST /api/v1/backlogs/generate
- POST /api/v1/jira/create
""")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
