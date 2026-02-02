"""Output models for generated documents."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AcceptanceCriteria(BaseModel):
    """Acceptance criteria for a requirement."""

    criterion: str
    testable: bool = True


class Requirement(BaseModel):
    """A single requirement."""

    id: str
    title: str
    description: str
    priority: str  # 'high', 'medium', 'low'
    acceptance_criteria: list[AcceptanceCriteria] = Field(default_factory=list)


class BRDDocument(BaseModel):
    """Business Requirements Document."""

    title: str
    version: str = "1.0"
    created_at: datetime = Field(default_factory=datetime.now)

    business_context: str
    objectives: list[str] = Field(default_factory=list)
    functional_requirements: list[Requirement] = Field(default_factory=list)
    technical_requirements: list[Requirement] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    # Store raw LLM-generated markdown to preserve full content
    raw_markdown: Optional[str] = None

    def to_markdown(self) -> str:
        """Convert to Markdown format. Returns raw markdown if available."""
        # If we have raw LLM-generated markdown, return it (preserves full content)
        if self.raw_markdown:
            return self.raw_markdown
        lines = [
            f"# Business Requirements Document: {self.title}",
            "",
            f"**Version:** {self.version}",
            f"**Date:** {self.created_at.strftime('%Y-%m-%d')}",
            "**Status:** Draft",
            "",
            "---",
            "",
            "## 1. Business Context",
            "",
            self.business_context,
            "",
            "## 2. Objectives",
            "",
        ]

        for i, obj in enumerate(self.objectives, 1):
            lines.append(f"{i}. {obj}")

        lines.extend(["", "## 3. Functional Requirements", ""])

        for req in self.functional_requirements:
            lines.append(f"### {req.id}: {req.title}")
            lines.append("")
            lines.append(f"**Priority:** {req.priority}")
            lines.append("")
            lines.append(req.description)
            lines.append("")
            if req.acceptance_criteria:
                lines.append("**Acceptance Criteria:**")
                for ac in req.acceptance_criteria:
                    lines.append(f"- [ ] {ac.criterion}")
            lines.append("")

        lines.extend(["## 4. Technical Requirements", ""])

        for req in self.technical_requirements:
            lines.append(f"### {req.id}: {req.title}")
            lines.append("")
            lines.append(f"**Priority:** {req.priority}")
            lines.append("")
            lines.append(req.description)
            lines.append("")

        lines.extend(["## 5. Dependencies", ""])

        for dep in self.dependencies:
            lines.append(f"- {dep}")

        lines.extend(["", "## 6. Risks and Mitigation", ""])

        for risk in self.risks:
            lines.append(f"- {risk}")

        lines.extend([
            "",
            "---",
            "",
            "**Approval:**",
            "- Product Owner: _______________",
            "- Technical Lead: _______________",
        ])

        return "\n".join(lines)


class Epic(BaseModel):
    """Epic definition."""

    id: str
    title: str
    description: str
    components: list[str] = Field(default_factory=list)
    estimated_effort: str  # 'small', 'medium', 'large'
    stories: list[str] = Field(default_factory=list)  # Story IDs
    priority: str = "medium"  # 'high', 'medium', 'low'

    # JIRA integration fields
    jira_key: Optional[str] = None  # e.g., "PROJ-101"
    jira_url: Optional[str] = None  # Full JIRA URL
    jira_status: Optional[str] = None  # Creation status

    # Dependencies
    blocked_by: list[str] = Field(default_factory=list)  # Epic IDs this is blocked by
    blocks: list[str] = Field(default_factory=list)  # Epic IDs this blocks

    def to_jira_description(self) -> str:
        """Convert to JIRA-formatted description."""
        lines = [
            f"h2. Description",
            "",
            self.description,
            "",
            f"h2. Components Affected",
            "",
        ]
        for comp in self.components:
            lines.append(f"* {comp}")

        lines.extend([
            "",
            f"h2. Estimated Effort",
            "",
            f"*{self.estimated_effort.upper()}*",
        ])

        return "\n".join(lines)


class UserStory(BaseModel):
    """User story/backlog item."""

    id: str
    epic_id: str
    title: str
    description: str
    as_a: str  # User role
    i_want: str  # Capability
    so_that: str  # Benefit
    acceptance_criteria: list[AcceptanceCriteria] = Field(default_factory=list)
    technical_notes: Optional[str] = None
    estimated_points: Optional[int] = None
    files_to_modify: list[str] = Field(default_factory=list)
    files_to_create: list[str] = Field(default_factory=list)
    priority: str = "medium"  # 'high', 'medium', 'low'

    # JIRA integration fields
    jira_key: Optional[str] = None  # e.g., "PROJ-104"
    jira_url: Optional[str] = None  # Full JIRA URL
    jira_status: Optional[str] = None  # Creation status

    # Dependencies
    blocked_by: list[str] = Field(default_factory=list)  # Story IDs this is blocked by
    blocks: list[str] = Field(default_factory=list)  # Story IDs this blocks

    def to_user_story_format(self) -> str:
        """Convert to standard user story format."""
        return f"As a {self.as_a}, I want {self.i_want}, so that {self.so_that}."

    def to_jira_description(self) -> str:
        """Convert to JIRA-formatted description with acceptance criteria."""
        lines = [
            "h2. User Story",
            "",
            f"As a *{self.as_a}*,",
            f"I want *{self.i_want}*,",
            f"So that *{self.so_that}*.",
            "",
            "h2. Description",
            "",
            self.description,
            "",
            "h2. Acceptance Criteria",
            "",
        ]

        for ac in self.acceptance_criteria:
            lines.append(f"* (/) {ac.criterion}")

        if self.files_to_modify:
            lines.extend([
                "",
                "h2. Files to Modify",
                "",
            ])
            for file_path in self.files_to_modify:
                lines.append(f"* {{code}}{file_path}{{code}}")

        if self.files_to_create:
            lines.extend([
                "",
                "h2. Files to Create",
                "",
            ])
            for file_path in self.files_to_create:
                lines.append(f"* {{code}}{file_path}{{code}}")

        if self.technical_notes:
            lines.extend([
                "",
                "h2. Technical Notes",
                "",
                self.technical_notes,
            ])

        return "\n".join(lines)


class EpicsOutput(BaseModel):
    """Output from Epic generation (Phase 2 - Epics only, no stories)."""

    brd_id: str  # Reference to source BRD
    brd_title: str
    epics: list[Epic] = Field(default_factory=list)

    # Epic implementation order
    implementation_order: list[str] = Field(default_factory=list)  # Epic IDs in order

    metadata: dict[str, Any] = Field(
        default_factory=lambda: {
            "generation_time_ms": 0,
            "total_epics": 0,
        }
    )

    def to_markdown(self) -> str:
        """Convert to Markdown format."""
        lines = [
            f"# Epics",
            "",
            f"**Source BRD:** {self.brd_title}",
            f"**BRD ID:** {self.brd_id}",
            "",
            "---",
            "",
            "## Epic Summary",
            "",
            "| Epic ID | Title | Components | Effort | Priority | Blocked By |",
            "|---------|-------|------------|--------|----------|------------|",
        ]

        for epic in self.epics:
            components = ", ".join(epic.components[:2]) if epic.components else "N/A"
            blocked_by = ", ".join(epic.blocked_by) if epic.blocked_by else "None"
            lines.append(f"| {epic.id} | {epic.title} | {components} | {epic.estimated_effort} | {epic.priority} | {blocked_by} |")

        lines.extend(["", "---", ""])

        for epic in self.epics:
            lines.extend([
                f"## {epic.id}: {epic.title}",
                "",
                f"**Priority:** {epic.priority}",
                f"**Effort:** {epic.estimated_effort}",
                "",
                "### Description",
                epic.description,
                "",
                "### Components Affected",
            ])
            for comp in epic.components:
                lines.append(f"- {comp}")

            lines.extend([
                "",
                "### Dependencies",
                f"- **Blocked by:** {', '.join(epic.blocked_by) or 'None'}",
                f"- **Blocks:** {', '.join(epic.blocks) or 'None'}",
                "",
            ])

        if self.implementation_order:
            lines.extend([
                "---",
                "",
                "## Implementation Order",
                "",
            ])
            for i, epic_id in enumerate(self.implementation_order, 1):
                epic = next((e for e in self.epics if e.id == epic_id), None)
                if epic:
                    lines.append(f"{i}. {epic_id}: {epic.title}")

        return "\n".join(lines)


class BacklogsOutput(BaseModel):
    """Output from Backlog/Story generation (Phase 3 - Stories for approved Epics)."""

    epics: list[Epic] = Field(default_factory=list)  # Source epics (for reference)
    stories: list[UserStory] = Field(default_factory=list)

    # Story implementation order
    implementation_order: list[str] = Field(default_factory=list)  # Story IDs in order

    metadata: dict[str, Any] = Field(
        default_factory=lambda: {
            "generation_time_ms": 0,
            "total_stories": 0,
            "total_story_points": 0,
        }
    )

    def get_stories_for_epic(self, epic_id: str) -> list[UserStory]:
        """Get all stories belonging to an epic."""
        return [s for s in self.stories if s.epic_id == epic_id]

    def to_markdown(self) -> str:
        """Convert to Markdown format."""
        total_points = sum(s.estimated_points or 0 for s in self.stories)

        lines = [
            f"# User Stories (Backlogs)",
            "",
            f"**Total Stories:** {len(self.stories)}",
            f"**Total Story Points:** {total_points}",
            "",
            "---",
            "",
            "## Story Summary",
            "",
            "| Story ID | Epic | Title | Points | Blocked By |",
            "|----------|------|-------|--------|------------|",
        ]

        for story in self.stories:
            blocked_by = ", ".join(story.blocked_by) if story.blocked_by else "None"
            lines.append(f"| {story.id} | {story.epic_id} | {story.title} | {story.estimated_points or '-'} | {blocked_by} |")

        lines.extend(["", "---", ""])

        # Group stories by epic
        for epic in self.epics:
            epic_stories = self.get_stories_for_epic(epic.id)
            if not epic_stories:
                continue

            lines.extend([
                f"## {epic.id}: {epic.title}",
                "",
            ])

            for story in epic_stories:
                lines.extend([
                    f"### {story.id}: {story.title}",
                    "",
                    story.to_user_story_format(),
                    "",
                    "**Acceptance Criteria:**",
                ])
                for ac in story.acceptance_criteria:
                    lines.append(f"- [ ] {ac.criterion}")

                if story.files_to_modify:
                    lines.extend(["", "**Files to Modify:**"])
                    for f in story.files_to_modify:
                        lines.append(f"- `{f}`")

                if story.files_to_create:
                    lines.extend(["", "**Files to Create:**"])
                    for f in story.files_to_create:
                        lines.append(f"- `{f}`")

                lines.extend([
                    "",
                    f"**Points:** {story.estimated_points or 'TBD'}",
                    f"**Blocked by:** {', '.join(story.blocked_by) or 'None'}",
                    "",
                ])

        if self.implementation_order:
            lines.extend([
                "---",
                "",
                "## Implementation Order",
                "",
            ])
            for i, story_id in enumerate(self.implementation_order, 1):
                story = next((s for s in self.stories if s.id == story_id), None)
                if story:
                    lines.append(f"{i}. {story_id}: {story.title}")

        return "\n".join(lines)


class JiraCreationResult(BaseModel):
    """Result of creating issues in JIRA (Phase 3)."""

    project_key: str
    created_at: datetime = Field(default_factory=datetime.now)

    # Created issues
    epics_created: list[Epic] = Field(default_factory=list)
    stories_created: list[UserStory] = Field(default_factory=list)

    # Issue links created
    links_created: list[dict[str, str]] = Field(default_factory=list)

    # Errors encountered
    errors: list[dict[str, str]] = Field(default_factory=list)

    # Summary stats
    metadata: dict[str, Any] = Field(
        default_factory=lambda: {
            "total_epics": 0,
            "total_stories": 0,
            "total_links": 0,
            "failed_count": 0,
        }
    )

    def to_markdown(self) -> str:
        """Convert to Markdown summary."""
        lines = [
            "# JIRA Issues Created",
            "",
            f"**Project:** {self.project_key}",
            f"**Created At:** {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "---",
            "",
            "## Summary",
            "",
            "| Type | Count | Status |",
            "|------|-------|--------|",
            f"| Epics | {len(self.epics_created)} | {'✅' if self.epics_created else '⚠️'} |",
            f"| Stories | {len(self.stories_created)} | {'✅' if self.stories_created else '⚠️'} |",
            f"| Links | {len(self.links_created)} | {'✅' if self.links_created else '➖'} |",
            "",
            "---",
            "",
            "## Created Epics",
            "",
            "| Local ID | JIRA Key | Title |",
            "|----------|----------|-------|",
        ]

        for epic in self.epics_created:
            jira_key = epic.jira_key or "N/A"
            lines.append(f"| {epic.id} | {jira_key} | {epic.title} |")

        lines.extend([
            "",
            "## Created Stories",
            "",
            "| Local ID | JIRA Key | Epic | Title | Points |",
            "|----------|----------|------|-------|--------|",
        ])

        for story in self.stories_created:
            jira_key = story.jira_key or "N/A"
            lines.append(f"| {story.id} | {jira_key} | {story.epic_id} | {story.title} | {story.estimated_points or '-'} |")

        if self.errors:
            lines.extend([
                "",
                "## Errors",
                "",
                "| Issue | Error |",
                "|-------|-------|",
            ])
            for error in self.errors:
                lines.append(f"| {error.get('issue', 'Unknown')} | {error.get('error', 'Unknown error')} |")

        return "\n".join(lines)


class BRDOutput(BaseModel):
    """Complete BRD generation output (Phase 1 only - just BRD)."""

    brd: BRDDocument

    # Legacy fields for backward compatibility (empty when using separated flow)
    epics: list[Epic] = Field(default_factory=list)
    backlogs: list[UserStory] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(
        default_factory=lambda: {
            "neo4j_queries": 0,
            "files_analyzed": 0,
            "generation_time_ms": 0,
        }
    )
