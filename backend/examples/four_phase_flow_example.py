#!/usr/bin/env python3
"""
Example: Four-Phase BRD Generation Flow

This example demonstrates the separated workflow:
1. PHASE 1: Generate BRD → User reviews
2. PHASE 2: Generate Epics from approved BRD → User reviews
3. PHASE 3: Generate Backlogs from approved Epics → User reviews
4. PHASE 4: Create approved Backlogs in JIRA

This allows users to review and approve at each stage before proceeding.
"""

import asyncio
import os
from pathlib import Path

from brd_generator.core.generator import BRDGenerator
from brd_generator.core.synthesizer import TemplateConfig
from brd_generator.models.request import BRDRequest


async def main():
    """Demonstrate the four-phase workflow."""

    print("=" * 70)
    print("BRD Generator - Four-Phase Workflow")
    print("=" * 70)

    # ==========================================================================
    # CONFIGURATION
    # ==========================================================================

    template_config = TemplateConfig(
        organization_name="Acme Corp",
        document_prefix="ACME-BRD",
        require_approvals=True,
        approval_roles=["Product Owner", "Tech Lead", "Architect"],
        include_risk_matrix=True,
    )

    generator = BRDGenerator(
        workspace_root=Path(os.getenv("CODEBASE_ROOT", ".")),
        template_config=template_config,
    )

    # ==========================================================================
    # PHASE 1: Generate BRD
    # ==========================================================================

    print("\n" + "=" * 70)
    print("PHASE 1: Generate BRD")
    print("=" * 70)

    request = BRDRequest(
        feature_description="Add a caching layer to improve API response times",
        affected_components=["api-service", "cache-service", "database"],
    )

    brd_output = await generator.generate_brd(request, use_skill=True)

    print("\n📄 BRD Generated:")
    print("-" * 50)
    print(f"Title: {brd_output.brd.title}")
    print(f"Functional Requirements: {len(brd_output.brd.functional_requirements)}")
    print(f"Technical Requirements: {len(brd_output.brd.technical_requirements)}")
    print(f"Risks: {len(brd_output.brd.risks)}")

    # User Review Point 1
    print("\n⏸️  USER REVIEW: Review and approve the BRD")
    user_approved = True  # Auto-approve for demo

    if not user_approved:
        print("❌ BRD not approved. Exiting.")
        await generator.cleanup()
        return

    # ==========================================================================
    # PHASE 2: Generate Epics from BRD
    # ==========================================================================

    print("\n" + "=" * 70)
    print("PHASE 2: Generate Epics from BRD")
    print("=" * 70)

    epics_output = await generator.generate_epics_from_brd(
        brd=brd_output.brd,
        use_skill=True,
    )

    print("\n🎯 Epics Generated:")
    print("-" * 50)
    for epic in epics_output.epics:
        print(f"\n{epic.id}: {epic.title}")
        print(f"   Priority: {epic.priority} | Effort: {epic.estimated_effort}")
        print(f"   Components: {', '.join(epic.components) or 'N/A'}")
        print(f"   Blocked by: {', '.join(epic.blocked_by) or 'None'}")

    print(f"\n✅ Total Epics: {len(epics_output.epics)}")

    # User Review Point 2
    print("\n⏸️  USER REVIEW: Review and approve the Epics")
    user_approved = True  # Auto-approve for demo

    if not user_approved:
        print("❌ Epics not approved. Exiting.")
        await generator.cleanup()
        return

    # ==========================================================================
    # PHASE 3: Generate Backlogs from Epics
    # ==========================================================================

    print("\n" + "=" * 70)
    print("PHASE 3: Generate Backlogs (User Stories) from Epics")
    print("=" * 70)

    backlogs_output = await generator.generate_backlogs_from_epics(
        epics_output=epics_output,
        use_skill=True,
    )

    print("\n📝 User Stories Generated:")
    print("-" * 50)

    for epic in backlogs_output.epics:
        stories = backlogs_output.get_stories_for_epic(epic.id)
        print(f"\n{epic.id}: {epic.title} ({len(stories)} stories)")
        for story in stories:
            points = story.estimated_points or "?"
            blocked = f" [blocked by {', '.join(story.blocked_by)}]" if story.blocked_by else ""
            print(f"   📌 {story.id}: {story.title} ({points} pts){blocked}")

    total_points = sum(s.estimated_points or 0 for s in backlogs_output.stories)
    print(f"\n✅ Total Stories: {len(backlogs_output.stories)}")
    print(f"✅ Total Story Points: {total_points}")

    # User Review Point 3
    print("\n⏸️  USER REVIEW: Review and approve the Backlogs")
    user_approved = True  # Auto-approve for demo

    if not user_approved:
        print("❌ Backlogs not approved. Exiting.")
        await generator.cleanup()
        return

    # ==========================================================================
    # PHASE 4: Create in JIRA
    # ==========================================================================

    print("\n" + "=" * 70)
    print("PHASE 4: Create Issues in JIRA")
    print("=" * 70)

    if os.getenv("MCP_ATLASSIAN_ENABLED", "false").lower() != "true":
        print("\n⚠️  Atlassian MCP not enabled.")
        print("To enable JIRA integration, set:")
        print("  - MCP_ATLASSIAN_ENABLED=true")
        print("  - ATLASSIAN_URL=https://your-domain.atlassian.net")
        print("  - ATLASSIAN_EMAIL=your-email@company.com")
        print("  - ATLASSIAN_API_TOKEN=your-api-token")
        print("\nSkipping JIRA creation.")
    else:
        project_key = os.getenv("JIRA_PROJECT_KEY", "DEMO")

        jira_result = await generator.create_jira_issues(
            backlogs_output=backlogs_output,
            project_key=project_key,
            use_skill=True,
        )

        print(f"\n🎫 JIRA Issues Created in {project_key}:")
        print("-" * 50)
        print(jira_result.to_markdown())

    # ==========================================================================
    # SUMMARY
    # ==========================================================================

    print("\n" + "=" * 70)
    print("WORKFLOW COMPLETE")
    print("=" * 70)

    print("""
Four-Phase Workflow Summary:

┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 1: Generate BRD                                               │
│ ─────────────────────                                               │
│ • Analyzed codebase using Neo4j and Filesystem MCP                  │
│ • Generated Business Requirements Document                          │
│ • User reviews and approves BRD                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 2: Generate Epics                                             │
│ ───────────────────────                                             │
│ • Analyzed approved BRD                                             │
│ • Created Epics grouped by component/feature                        │
│ • Defined Epic dependencies                                         │
│ • User reviews and approves Epics                                   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 3: Generate Backlogs                                          │
│ ──────────────────────────                                          │
│ • Broke Epics into User Stories                                     │
│ • Added acceptance criteria                                         │
│ • Defined story dependencies                                        │
│ • Estimated story points                                            │
│ • User reviews and approves Backlogs                                │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 4: Create in JIRA                                             │
│ ───────────────────────                                             │
│ • Connected to JIRA via Atlassian MCP server                        │
│ • Created Epic issues                                               │
│ • Created Story issues linked to Epics                              │
│ • Created dependency links                                          │
└─────────────────────────────────────────────────────────────────────┘
""")

    await generator.cleanup()
    print("✅ Done!")


if __name__ == "__main__":
    asyncio.run(main())
