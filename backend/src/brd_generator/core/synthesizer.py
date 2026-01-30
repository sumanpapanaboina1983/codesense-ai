"""LLM synthesis using GitHub Copilot SDK."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..models.context import AggregatedContext
from ..models.output import (
    BRDDocument,
    Epic,
    UserStory,
    Requirement,
    AcceptanceCriteria,
    JiraCreationResult,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Default timeout for LLM responses (5 minutes)
LLM_TIMEOUT_SECONDS = 300


@dataclass
class TemplateConfig:
    """
    Configuration for BRD output templates.

    Allows users to customize output format to match organizational standards.
    """
    # Template content (loaded from file or provided directly)
    brd_template: str = ""
    epic_template: str = ""
    story_template: str = ""

    # Custom sections to include
    custom_sections: list[str] = field(default_factory=list)

    # Organization-specific fields
    organization_name: str = ""
    document_prefix: str = "BRD"
    require_approvals: bool = True
    approval_roles: list[str] = field(default_factory=lambda: ["Product Owner", "Tech Lead"])

    # Output format preferences
    include_code_references: bool = True
    include_file_paths: bool = True
    include_cypher_queries: bool = False  # Include Neo4j queries used
    max_requirements_per_section: int = 10

    # Risk assessment
    include_risk_matrix: bool = True
    risk_levels: list[str] = field(default_factory=lambda: ["High", "Medium", "Low"])


class LLMSynthesizer:
    """
    Synthesizes BRD/Epics/Backlogs using GitHub Copilot SDK.

    Combines:
    - Skill-based approach: LLM uses MCP tools (Neo4j, Filesystem) autonomously
    - Template-controlled output: User-defined templates for organizational standards

    Uses the Copilot SDK session with the correct MessageOptions API.
    Falls back to mock responses if Copilot is unavailable.
    """

    def __init__(
        self,
        session: Any = None,
        templates_dir: Optional[Path] = None,
        model: str = "claude-sonnet-4.5",
        tool_registry: Any = None,
        template_config: Optional[TemplateConfig] = None,
    ):
        """
        Initialize the LLM Synthesizer.

        Args:
            session: Copilot SDK session
            templates_dir: Directory containing template files
            model: LLM model to use
            tool_registry: Registry of available tools
            template_config: Configuration for output templates
        """
        self.session = session
        self.templates_dir = templates_dir or self._get_templates_dir()
        self.model = model
        self.tool_registry = tool_registry
        self.template_config = template_config or TemplateConfig()
        self._copilot_available = session is not None

        # Load templates
        self._load_templates()

        if self._copilot_available:
            logger.info(f"LLM Synthesizer initialized with Copilot SDK session (model: {model})")
        else:
            logger.warning("LLM Synthesizer initialized without Copilot - mock mode active")

    def _get_templates_dir(self) -> Path:
        """Get templates directory from env or default."""
        env_dir = os.getenv("BRD_TEMPLATES_DIR")
        if env_dir:
            return Path(env_dir)
        return Path(__file__).parent.parent / "templates"

    def _load_templates(self) -> None:
        """Load templates from files if not provided in config."""
        if not self.template_config.brd_template:
            self.template_config.brd_template = self._load_template("brd-template.md")
        if not self.template_config.epic_template:
            self.template_config.epic_template = self._load_template("epic-template.md")
        if not self.template_config.story_template:
            self.template_config.story_template = self._load_template("backlog-template.md")

    async def generate_brd(
        self,
        context: AggregatedContext,
        use_skill: bool = True,
    ) -> BRDDocument:
        """
        Generate BRD from context.

        Args:
            context: Aggregated context from MCP servers
            use_skill: If True, use simple prompt to trigger automatic skill selection.
                      If False, use template-based approach with detailed prompts.
        """
        logger.info(f"Generating BRD (use_skill={use_skill})...")

        if use_skill and self._copilot_available:
            # SKILL-BASED APPROACH:
            # Send simple prompt - Copilot automatically matches to generate-brd skill
            # The skill instructs LLM to use MCP tools (Neo4j, Filesystem) to gather context
            response = await self._generate_brd_with_skill(context)
        else:
            # TEMPLATE-BASED APPROACH:
            # Build detailed prompt with pre-gathered context and templates
            response = await self._generate_brd_with_template(context)

        # Parse response into BRDDocument
        brd = self._parse_brd_response(response, context.request)

        logger.info("BRD generated successfully")
        return brd

    async def _generate_brd_with_skill(self, context: AggregatedContext) -> str:
        """
        Generate BRD using automatic skill selection WITH template-controlled output.

        Combines:
        - Skill-based: LLM uses MCP tools (Neo4j, Filesystem) to gather context
        - Template-controlled: Output follows user-defined template format

        The prompt:
        1. Triggers skill matching for MCP tool usage
        2. Includes template for output format control
        3. Includes organizational preferences
        """
        # Build template instructions
        template_instructions = self._build_template_instructions()

        # Build prompt that combines skill triggering + template control
        prompt = f"""Generate a BRD for the following feature:

{context.request}

## Instructions

1. **Analyze the codebase** using the available MCP tools:
   - Use Neo4j code graph to find affected components, classes, and dependencies
   - Use filesystem tools to read relevant source files and understand patterns

2. **Generate the BRD** following the EXACT template format below.

{template_instructions}

## Important Guidelines

- Use the MCP tools to gather REAL context from the codebase before writing
- Reference actual component names, file paths, and code patterns discovered
- Follow the template structure EXACTLY for organizational compliance
- Include specific file paths that need modification
- Be concrete and actionable in requirements
"""

        logger.info("Using skill-based BRD generation with template control")
        return await self._send_to_llm(prompt)

    def _build_template_instructions(self) -> str:
        """Build template instructions for LLM output format control."""
        config = self.template_config

        # Start with the base template
        instructions = f"""## Output Template (MUST FOLLOW THIS FORMAT)

{config.brd_template if config.brd_template else self._get_default_brd_template()}
"""

        # Add organizational customizations
        if config.organization_name:
            instructions += f"""
## Organization: {config.organization_name}
- Document prefix: {config.document_prefix}
"""

        # Add section preferences
        if config.custom_sections:
            instructions += f"""
## Additional Sections Required:
{chr(10).join(f'- {section}' for section in config.custom_sections)}
"""

        # Add approval requirements
        if config.require_approvals and config.approval_roles:
            instructions += f"""
## Approval Section Required:
Include approval lines for: {', '.join(config.approval_roles)}
"""

        # Add output preferences
        instructions += f"""
## Output Preferences:
- Include code/file references: {config.include_code_references}
- Include file paths to modify: {config.include_file_paths}
- Include risk matrix: {config.include_risk_matrix}
- Max requirements per section: {config.max_requirements_per_section}
"""

        if config.include_risk_matrix:
            instructions += f"""
## Risk Matrix Format:
| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
Use risk levels: {', '.join(config.risk_levels)}
"""

        return instructions

    def _get_default_brd_template(self) -> str:
        """Return default BRD template if none loaded."""
        return """
# Business Requirements Document: {TITLE}

**Version:** 1.0
**Date:** {DATE}
**Status:** Draft

---

## 1. Executive Summary
{BUSINESS_CONTEXT}

## 2. Business Objectives
{OBJECTIVES}

## 3. Scope

### 3.1 In Scope (Functional Requirements)
{FUNCTIONAL_REQUIREMENTS}

### 3.2 Out of Scope
{OUT_OF_SCOPE}

## 4. Technical Requirements
{TECHNICAL_REQUIREMENTS}

### 4.1 Affected Components
{AFFECTED_COMPONENTS}

### 4.2 Files to Modify
{SOURCE_FILES}

## 5. Dependencies
{DEPENDENCIES}

## 6. Risk Assessment
{RISKS}

## 7. Acceptance Criteria
{ACCEPTANCE_CRITERIA}

---

## Approval
| Role | Name | Signature | Date |
|------|------|-----------|------|
| Product Owner | | | |
| Tech Lead | | | |
"""

    async def _generate_brd_with_template(self, context: AggregatedContext) -> str:
        """
        Generate BRD using template-based approach with detailed prompts.

        This approach:
        1. Pre-gathers context using aggregator
        2. Loads templates
        3. Builds detailed prompts
        4. Sends to LLM with all context embedded
        """
        # Load template
        template = self._load_template("brd-template.md")
        analysis_prompt = self._load_prompt("analysis-prompt.txt")

        # Stage 1: Analysis
        analysis = await self._analyze_context(context, analysis_prompt)

        # Stage 2: BRD Generation
        brd_prompt = self._build_brd_prompt(context, analysis, template)

        logger.info("Using template-based BRD generation")
        return await self._send_to_llm(brd_prompt)

    async def generate_epics_from_brd(
        self,
        brd: BRDDocument,
        use_skill: bool = True,
    ) -> list[Epic]:
        """
        PHASE 2: Generate Epics from an approved BRD.

        This generates Epics only (no stories). Stories are generated
        separately in Phase 3 after user approves the Epics.

        Args:
            brd: The approved BRD document
            use_skill: If True, use skill-based approach

        Returns:
            List of Epics
        """
        logger.info(f"Generating Epics from BRD: {brd.title}")

        if use_skill and self._copilot_available:
            prompt = self._build_epics_only_prompt(brd)
            response = await self._send_to_llm(prompt)
            epics = self._parse_epics_only_response(response)
        else:
            epics = self._generate_basic_epics(brd)

        logger.info(f"Generated {len(epics)} Epics")
        return epics

    def _build_epics_only_prompt(self, brd: BRDDocument) -> str:
        """Build prompt for generating Epics only (no stories)."""
        func_reqs = "\n".join(
            f"- {req.id}: {req.title}" for req in brd.functional_requirements[:10]
        )
        tech_reqs = "\n".join(
            f"- {req.id}: {req.title}" for req in brd.technical_requirements[:10]
        )

        return f"""Generate Epics from the following approved BRD.

## Approved BRD: {brd.title}

### Business Context
{brd.business_context}

### Functional Requirements
{func_reqs}

### Technical Requirements
{tech_reqs}

### Dependencies
{chr(10).join(f'- {dep}' for dep in brd.dependencies)}

---

## Instructions

1. **Analyze the codebase** using MCP tools to understand component relationships
2. **Group requirements into Epics** (2-4 Epics, each deliverable in 2-4 weeks)
3. **Define Epic dependencies** based on code analysis
4. **Do NOT generate User Stories** - those will be generated in the next phase

## Output Format

For each Epic:
```
EPIC-XXX: [Title]
Description: [Brief description - 2-3 sentences]
Components: [component1, component2]
Priority: [High/Medium/Low]
Effort: [Small/Medium/Large]
Blocked By: [EPIC-XXX or None]
Requirements: [FR-001, FR-002, TR-001]
```

Generate 2-4 Epics that cover all requirements from the BRD.
"""

    def _parse_epics_only_response(self, response: str) -> list[Epic]:
        """Parse response into Epics (no stories)."""
        epics = []
        epic_pattern = r"EPIC-(\d+):\s*(.+?)(?=EPIC-\d+:|$)"
        matches = re.findall(epic_pattern, response, re.DOTALL)

        for match in matches:
            epic_id = f"EPIC-{match[0]}"
            content = match[1].strip()

            title = content.split("\n")[0].strip()

            desc_match = re.search(r"Description:\s*(.+?)(?=Components:|Priority:|Effort:|Blocked By:|Requirements:|$)", content, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else title

            comp_match = re.search(r"Components:\s*\[?([^\]]+)\]?", content)
            components = []
            if comp_match:
                components = [c.strip() for c in comp_match.group(1).split(",")]

            priority_match = re.search(r"Priority:\s*(High|Medium|Low)", content, re.IGNORECASE)
            priority = priority_match.group(1).lower() if priority_match else "medium"

            effort_match = re.search(r"Effort:\s*(Small|Medium|Large)", content, re.IGNORECASE)
            effort = effort_match.group(1).lower() if effort_match else "medium"

            blocked_match = re.search(r"Blocked By:\s*(.+?)(?=Requirements:|$)", content)
            blocked_by = []
            if blocked_match:
                blocked_str = blocked_match.group(1).strip()
                if blocked_str.lower() != "none":
                    blocked_by = re.findall(r"EPIC-\d+", blocked_str)

            epics.append(Epic(
                id=epic_id,
                title=title,
                description=description,
                components=components,
                estimated_effort=effort,
                priority=priority,
                blocked_by=blocked_by,
            ))

        if not epics:
            epics = self._generate_basic_epics_from_title(response)

        return epics

    def _generate_basic_epics_from_title(self, response: str) -> list[Epic]:
        """Fallback: generate basic epics from response text."""
        return [Epic(
            id="EPIC-001",
            title="Core Implementation",
            description="Implement the core functionality as per BRD requirements",
            components=[],
            estimated_effort="medium",
            priority="high",
        )]

    async def generate_backlogs_from_epics(
        self,
        epics: list[Epic],
        use_skill: bool = True,
    ) -> list[UserStory]:
        """
        PHASE 3: Generate User Stories (Backlogs) from approved Epics.

        Args:
            epics: List of approved Epics
            use_skill: If True, use skill-based approach

        Returns:
            List of User Stories
        """
        logger.info(f"Generating Backlogs from {len(epics)} Epics")

        all_stories = []
        for epic in epics:
            if use_skill and self._copilot_available:
                prompt = self._build_backlogs_prompt(epic)
                response = await self._send_to_llm(prompt)
                stories = self._parse_stories_response(response, epic.id)
            else:
                stories = self._generate_basic_stories_for_epic(epic)

            all_stories.extend(stories)
            epic.stories = [s.id for s in stories]

        logger.info(f"Generated {len(all_stories)} User Stories")
        return all_stories

    def _build_backlogs_prompt(self, epic: Epic) -> str:
        """Build prompt for generating Stories from an Epic."""
        return f"""Generate User Stories for the following approved Epic.

## Epic: {epic.id} - {epic.title}

### Description
{epic.description}

### Components Affected
{chr(10).join(f'- {c}' for c in epic.components) or '- To be determined from code analysis'}

### Priority
{epic.priority}

---

## Instructions

1. **Analyze the codebase** using MCP tools to understand:
   - Classes and methods in affected components
   - Existing patterns to follow
   - Test coverage requirements

2. **Create 3-5 User Stories** that:
   - Are completable in 1-3 days each
   - Have clear acceptance criteria
   - Include specific files to modify
   - Define dependencies between stories

## Output Format

For each Story:
```
STORY-XXX: [Title]
Epic: {epic.id}
As a [role], I want [capability], so that [benefit].
Description: [Detailed description]
Acceptance Criteria:
- [Criterion 1]
- [Criterion 2]
Files to Modify:
- path/to/file.py - [what to change]
Files to Create:
- path/to/new_file.py - [purpose]
Blocked By: [STORY-XXX or None]
Points: [1/2/3/5/8]
```

Generate 3-5 Stories for this Epic.
"""

    def _generate_basic_stories_for_epic(self, epic: Epic) -> list[UserStory]:
        """Fallback: generate basic stories for an epic."""
        base_num = int(epic.id.split("-")[1]) * 100
        return [
            UserStory(
                id=f"STORY-{base_num + 1:03d}",
                epic_id=epic.id,
                title=f"Implement core functionality for {epic.title}",
                description=f"Implement the main feature described in {epic.id}",
                as_a="user",
                i_want="the core functionality implemented",
                so_that="I can use the feature",
                acceptance_criteria=[AcceptanceCriteria(criterion="Feature works as expected")],
                estimated_points=5,
            ),
            UserStory(
                id=f"STORY-{base_num + 2:03d}",
                epic_id=epic.id,
                title=f"Add tests for {epic.title}",
                description=f"Add unit and integration tests for {epic.id}",
                as_a="developer",
                i_want="comprehensive test coverage",
                so_that="the feature is reliable",
                acceptance_criteria=[AcceptanceCriteria(criterion="Test coverage > 80%")],
                estimated_points=3,
                blocked_by=[f"STORY-{base_num + 1:03d}"],
            ),
        ]

    # Legacy method for backward compatibility
    async def generate_epics(
        self,
        context: AggregatedContext,
        brd: BRDDocument,
        use_skill: bool = True,
    ) -> list[Epic]:
        """Legacy: Generate epics from BRD and context."""
        return await self.generate_epics_from_brd(brd, use_skill)

    # Legacy method for backward compatibility
    async def generate_backlogs(
        self,
        context: AggregatedContext,
        epics: list[Epic],
        use_skill: bool = True,
    ) -> list[UserStory]:
        """Legacy: Generate user stories from epics."""
        return await self.generate_backlogs_from_epics(epics, use_skill)

    async def generate_epics_and_stories_from_brd(
        self,
        brd: BRDDocument,
        use_skill: bool = True,
    ) -> tuple[list[Epic], list[UserStory]]:
        """
        PHASE 2: Generate Epics and User Stories from an approved BRD.

        This uses the generate-epics-from-brd skill to create a complete
        breakdown with dependencies.

        Args:
            brd: The approved BRD document
            use_skill: If True, use skill-based approach

        Returns:
            Tuple of (epics, stories)
        """
        logger.info(f"Generating Epics and Stories from BRD: {brd.title}")

        if use_skill and self._copilot_available:
            # Use skill-based approach with template control
            prompt = self._build_epics_from_brd_prompt(brd)
            response = await self._send_to_llm(prompt)

            # Parse the response into epics and stories
            epics, stories = self._parse_epics_and_stories_response(response, brd)
        else:
            # Fallback: Simple generation
            epics = self._generate_basic_epics(brd)
            stories = self._generate_basic_stories(epics, brd)

        logger.info(f"Generated {len(epics)} Epics and {len(stories)} Stories")
        return epics, stories

    def _build_epics_from_brd_prompt(self, brd: BRDDocument) -> str:
        """Build prompt for generating Epics and Stories from BRD."""
        # Format requirements
        func_reqs = "\n".join(
            f"- {req.id}: {req.title}" for req in brd.functional_requirements[:10]
        )
        tech_reqs = "\n".join(
            f"- {req.id}: {req.title}" for req in brd.technical_requirements[:10]
        )

        return f"""Generate Epics and User Stories from the following approved BRD.

## Approved BRD: {brd.title}

### Business Context
{brd.business_context}

### Objectives
{chr(10).join(f'- {obj}' for obj in brd.objectives)}

### Functional Requirements
{func_reqs}

### Technical Requirements
{tech_reqs}

### Dependencies
{chr(10).join(f'- {dep}' for dep in brd.dependencies)}

### Risks
{chr(10).join(f'- {risk}' for risk in brd.risks)}

---

## Instructions

1. **Analyze the codebase** using MCP tools to understand component dependencies
2. **Group requirements into Epics** (2-4 Epics, each deliverable in 2-4 weeks)
3. **Break each Epic into User Stories** (3-5 stories per Epic, each 1-3 days)
4. **Define dependencies** between stories based on code analysis
5. **Estimate story points** (1, 2, 3, 5, 8 scale)

## Output Format

For each Epic:
```
EPIC-XXX: [Title]
Description: [Brief description]
Components: [component1, component2]
Priority: [High/Medium/Low]
Effort: [Small/Medium/Large]
```

For each Story within the Epic:
```
STORY-XXX: [Title]
Epic: EPIC-XXX
As a [role], I want [capability], so that [benefit].
Description: [Detailed description]
Acceptance Criteria:
- [Criterion 1]
- [Criterion 2]
Files to Modify:
- path/to/file.py
Blocked By: [STORY-XXX or None]
Points: [1-8]
```

## Guidelines
- Every BRD requirement must map to at least one story
- Stories should be small enough to complete in 1-3 days
- Include specific file paths from code analysis
- Define clear dependencies between stories
"""

    def _parse_epics_and_stories_response(
        self,
        response: str,
        brd: BRDDocument,
    ) -> tuple[list[Epic], list[UserStory]]:
        """Parse response into Epics and Stories with dependencies."""
        epics = []
        stories = []

        # Parse Epics
        epic_pattern = r"EPIC-(\d+):\s*(.+?)(?=EPIC-\d+:|STORY-\d+:|$)"
        epic_matches = re.findall(epic_pattern, response, re.DOTALL)

        for match in epic_matches:
            epic_id = f"EPIC-{match[0]}"
            content = match[1].strip()

            title = content.split("\n")[0].strip()

            desc_match = re.search(r"Description:\s*(.+?)(?=Components:|Priority:|Effort:|$)", content, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else title

            comp_match = re.search(r"Components:\s*\[?([^\]]+)\]?", content)
            components = []
            if comp_match:
                components = [c.strip() for c in comp_match.group(1).split(",")]

            priority_match = re.search(r"Priority:\s*(High|Medium|Low)", content, re.IGNORECASE)
            priority = priority_match.group(1).lower() if priority_match else "medium"

            effort_match = re.search(r"Effort:\s*(Small|Medium|Large)", content, re.IGNORECASE)
            effort = effort_match.group(1).lower() if effort_match else "medium"

            epics.append(Epic(
                id=epic_id,
                title=title,
                description=description,
                components=components,
                estimated_effort=effort,
                priority=priority,
            ))

        # Parse Stories
        story_pattern = r"STORY-(\d+):\s*(.+?)(?=STORY-\d+:|$)"
        story_matches = re.findall(story_pattern, response, re.DOTALL)

        for match in story_matches:
            story_id = f"STORY-{match[0]}"
            content = match[1].strip()

            lines = content.split("\n")
            title = lines[0].strip()

            # Find Epic
            epic_match = re.search(r"Epic:\s*(EPIC-\d+)", content)
            epic_id = epic_match.group(1) if epic_match else (epics[0].id if epics else "EPIC-001")

            # Parse user story format
            as_a_match = re.search(r"As a\s+(.+?),", content)
            i_want_match = re.search(r"I want\s+(.+?),", content)
            so_that_match = re.search(r"so that\s+(.+?)(?:\.|$)", content)

            as_a = as_a_match.group(1) if as_a_match else "user"
            i_want = i_want_match.group(1) if i_want_match else "this functionality"
            so_that = so_that_match.group(1) if so_that_match else "I can achieve my goal"

            # Parse description
            desc_match = re.search(r"Description:\s*(.+?)(?=Acceptance Criteria:|Files to Modify:|Blocked By:|Points:|$)", content, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else content[:200]

            # Parse acceptance criteria
            ac_section = re.search(r"Acceptance Criteria:(.+?)(?=Files to Modify:|Blocked By:|Points:|$)", content, re.DOTALL)
            acceptance_criteria = []
            if ac_section:
                for line in ac_section.group(1).split("\n"):
                    line = line.strip().lstrip("-").strip()
                    if line:
                        acceptance_criteria.append(AcceptanceCriteria(criterion=line))

            # Parse files to modify
            files_match = re.search(r"Files to Modify:(.+?)(?=Blocked By:|Points:|$)", content, re.DOTALL)
            files_to_modify = []
            if files_match:
                for line in files_match.group(1).split("\n"):
                    line = line.strip().lstrip("-").strip()
                    if line and "/" in line:
                        files_to_modify.append(line.split()[0])

            # Parse dependencies
            blocked_match = re.search(r"Blocked By:\s*(.+?)(?=Points:|$)", content)
            blocked_by = []
            if blocked_match:
                blocked_str = blocked_match.group(1).strip()
                if blocked_str.lower() != "none":
                    blocked_by = re.findall(r"STORY-\d+", blocked_str)

            # Parse points
            points_match = re.search(r"Points:\s*(\d+)", content)
            points = int(points_match.group(1)) if points_match else 3

            stories.append(UserStory(
                id=story_id,
                epic_id=epic_id,
                title=title,
                description=description,
                as_a=as_a,
                i_want=i_want,
                so_that=so_that,
                acceptance_criteria=acceptance_criteria,
                files_to_modify=files_to_modify,
                blocked_by=blocked_by,
                estimated_points=points,
            ))

        # Link stories to epics
        for epic in epics:
            epic.stories = [s.id for s in stories if s.epic_id == epic.id]

        # Fallback if no epics/stories parsed
        if not epics:
            epics = self._generate_basic_epics(brd)
        if not stories:
            stories = self._generate_basic_stories(epics, brd)

        return epics, stories

    def _generate_basic_epics(self, brd: BRDDocument) -> list[Epic]:
        """Generate basic epics from BRD requirements."""
        epics = []

        # Group by functional areas
        if brd.functional_requirements:
            epics.append(Epic(
                id="EPIC-001",
                title="Core Functionality",
                description="Implement core functional requirements",
                components=[],
                estimated_effort="medium",
                priority="high",
            ))

        if brd.technical_requirements:
            epics.append(Epic(
                id="EPIC-002",
                title="Technical Implementation",
                description="Implement technical requirements and infrastructure",
                components=[],
                estimated_effort="medium",
                priority="medium",
            ))

        return epics or [Epic(
            id="EPIC-001",
            title="Implementation",
            description=f"Implement {brd.title}",
            components=[],
            estimated_effort="medium",
            priority="medium",
        )]

    def _generate_basic_stories(
        self,
        epics: list[Epic],
        brd: BRDDocument,
    ) -> list[UserStory]:
        """Generate basic stories from BRD requirements."""
        stories = []
        story_num = 1

        # Create stories from functional requirements
        for i, req in enumerate(brd.functional_requirements[:5]):
            epic_id = epics[0].id if epics else "EPIC-001"
            stories.append(UserStory(
                id=f"STORY-{story_num:03d}",
                epic_id=epic_id,
                title=req.title,
                description=req.description,
                as_a="user",
                i_want=req.title.lower(),
                so_that="I can use this functionality",
                acceptance_criteria=[AcceptanceCriteria(criterion=ac.criterion) for ac in req.acceptance_criteria],
                estimated_points=3,
            ))
            story_num += 1

        # Create stories from technical requirements
        for i, req in enumerate(brd.technical_requirements[:3]):
            epic_id = epics[1].id if len(epics) > 1 else (epics[0].id if epics else "EPIC-001")
            stories.append(UserStory(
                id=f"STORY-{story_num:03d}",
                epic_id=epic_id,
                title=req.title,
                description=req.description,
                as_a="developer",
                i_want=req.title.lower(),
                so_that="the system works correctly",
                estimated_points=5,
            ))
            story_num += 1

        return stories

    async def create_jira_issues(
        self,
        epics: list[Epic],
        stories: list[UserStory],
        project_key: str,
        use_skill: bool = True,
    ) -> JiraCreationResult:
        """
        PHASE 3: Create Epics and Stories in JIRA.

        Uses the create-jira-issues skill with Atlassian MCP server.

        Args:
            epics: List of approved Epics
            stories: List of approved User Stories
            project_key: JIRA project key
            use_skill: If True, use skill-based approach

        Returns:
            JiraCreationResult with created issue details
        """
        logger.info(f"Creating JIRA issues in project: {project_key}")

        if use_skill and self._copilot_available:
            # Use skill-based approach
            prompt = self._build_jira_creation_prompt(epics, stories, project_key)
            response = await self._send_to_llm(prompt)

            # Parse the response
            result = self._parse_jira_creation_response(response, epics, stories, project_key)
        else:
            # Return error - JIRA creation requires MCP tools
            result = JiraCreationResult(
                project_key=project_key,
                errors=[{
                    "issue": "Configuration",
                    "error": "JIRA creation requires Copilot SDK with Atlassian MCP server"
                }],
            )

        return result

    def _build_jira_creation_prompt(
        self,
        epics: list[Epic],
        stories: list[UserStory],
        project_key: str,
    ) -> str:
        """Build prompt for creating JIRA issues."""
        # Format epics
        epics_text = ""
        for epic in epics:
            epics_text += f"""
EPIC: {epic.id}
Title: {epic.title}
Description: {epic.description}
Components: {', '.join(epic.components)}
Priority: {epic.priority}
Effort: {epic.estimated_effort}
"""

        # Format stories
        stories_text = ""
        for story in stories:
            stories_text += f"""
STORY: {story.id}
Epic: {story.epic_id}
Title: {story.title}
User Story: As a {story.as_a}, I want {story.i_want}, so that {story.so_that}.
Description: {story.description}
Acceptance Criteria:
{chr(10).join(f'- {ac.criterion}' for ac in story.acceptance_criteria)}
Files to Modify: {', '.join(story.files_to_modify) or 'None'}
Blocked By: {', '.join(story.blocked_by) or 'None'}
Points: {story.estimated_points or 3}
"""

        return f"""Create JIRA issues for the following Epics and Stories.

## JIRA Project: {project_key}

## Epics to Create
{epics_text}

## Stories to Create
{stories_text}

---

## Instructions

1. **Verify project exists** using jira_get_projects
2. **Create Epics first** using jira_create_issue
   - Issue type: Epic
   - Add labels: ["brd-generated", "EPIC-XXX"]
3. **Create Stories** and link to Epics
   - Issue type: Story
   - Link to parent Epic
   - Add story points
4. **Create issue links** for dependencies (blocks/is blocked by)
5. **Add technical notes as comments** for each story

## Expected Output

Report the JIRA keys created for each Epic and Story:
- EPIC-001 → PROJ-101
- STORY-001 → PROJ-102
- etc.

Report any errors encountered.
"""

    def _parse_jira_creation_response(
        self,
        response: str,
        epics: list[Epic],
        stories: list[UserStory],
        project_key: str,
    ) -> JiraCreationResult:
        """Parse JIRA creation response and update Epic/Story objects."""
        created_epics = []
        created_stories = []
        links = []
        errors = []

        # Look for JIRA key assignments in response
        # Pattern: EPIC-001 → PROJ-101 or EPIC-001 -> PROJ-101
        key_pattern = r"(EPIC-\d+|STORY-\d+)\s*[→\->]+\s*([A-Z]+-\d+)"
        matches = re.findall(key_pattern, response)

        jira_keys = {local_id: jira_key for local_id, jira_key in matches}

        # Update epics with JIRA keys
        for epic in epics:
            epic_copy = epic.model_copy()
            if epic.id in jira_keys:
                epic_copy.jira_key = jira_keys[epic.id]
                epic_copy.jira_status = "created"
            else:
                epic_copy.jira_status = "pending"
            created_epics.append(epic_copy)

        # Update stories with JIRA keys
        for story in stories:
            story_copy = story.model_copy()
            if story.id in jira_keys:
                story_copy.jira_key = jira_keys[story.id]
                story_copy.jira_status = "created"
            else:
                story_copy.jira_status = "pending"
            created_stories.append(story_copy)

        # Look for link creations
        link_pattern = r"([A-Z]+-\d+)\s+(?:blocks|is blocked by)\s+([A-Z]+-\d+)"
        link_matches = re.findall(link_pattern, response, re.IGNORECASE)
        for from_key, to_key in link_matches:
            links.append({"from": from_key, "type": "blocks", "to": to_key})

        # Look for errors
        error_pattern = r"Error:?\s*(.+?)(?=\n|$)"
        error_matches = re.findall(error_pattern, response, re.IGNORECASE)
        for error_msg in error_matches:
            errors.append({"issue": "Unknown", "error": error_msg.strip()})

        return JiraCreationResult(
            project_key=project_key,
            epics_created=created_epics,
            stories_created=created_stories,
            links_created=links,
            errors=errors,
            metadata={
                "total_epics": len(created_epics),
                "total_stories": len(created_stories),
                "total_links": len(links),
                "failed_count": len(errors),
            },
        )

    async def cleanup(self):
        """Cleanup resources."""
        pass  # Session cleanup is handled by the generator

    async def _send_to_llm(self, prompt: str) -> str:
        """Send prompt to LLM via Copilot SDK session."""
        if not self._copilot_available or not self.session:
            logger.warning("Copilot session not available. Using mock response.")
            return self._generate_mock_response(prompt)

        try:
            # Send message using SDK session with correct MessageOptions format
            response = await asyncio.wait_for(
                self._send_to_session(prompt),
                timeout=LLM_TIMEOUT_SECONDS,
            )

            if response:
                logger.info(f"Got Copilot response: {len(response)} chars")
                return response
            else:
                logger.warning("Empty response from Copilot")
                return self._generate_mock_response(prompt)

        except asyncio.TimeoutError:
            logger.warning(f"LLM response timed out after {LLM_TIMEOUT_SECONDS}s")
            return self._generate_mock_response(prompt)
        except Exception as e:
            logger.error(f"Copilot call failed: {e}")
            return self._generate_mock_response(prompt)

    async def _send_to_session(self, prompt: str) -> str:
        """Send message to Copilot SDK session using correct API."""
        try:
            # Build MessageOptions with prompt key
            message_options = {"prompt": prompt}
            logger.info(f"Sending prompt to Copilot ({len(prompt)} chars)...")

            # Use send_and_wait for synchronous response (it's async)
            if hasattr(self.session, 'send_and_wait'):
                logger.info("Using send_and_wait method...")
                # send_and_wait is an async method - await it directly
                event = await self.session.send_and_wait(message_options, timeout=LLM_TIMEOUT_SECONDS)

                if event:
                    # Extract content from SessionEvent
                    logger.info(f"Got event type: {type(event)}")
                    return self._extract_from_event(event)
                else:
                    logger.warning("send_and_wait returned None")

            # Fallback to send() method
            if hasattr(self.session, 'send'):
                logger.info("Using send method...")
                # send() is also async
                message_id = await self.session.send(message_options)
                logger.info(f"Message sent, ID: {message_id}")

                # Wait for response by polling get_messages
                return await self._wait_for_response(message_id)

            logger.error("No suitable send method found on session")
            return ""

        except Exception as e:
            logger.error(f"Error sending to Copilot session: {e}")
            raise

    def _extract_from_event(self, event: Any) -> str:
        """Extract text content from a SessionEvent."""
        try:
            if hasattr(event, 'data'):
                data = event.data
                # Check for message content
                if hasattr(data, 'message') and hasattr(data.message, 'content'):
                    return str(data.message.content)
                if hasattr(data, 'content'):
                    return str(data.content)
                if hasattr(data, 'text'):
                    return str(data.text)

            # Try direct attributes
            if hasattr(event, 'content'):
                return str(event.content)
            if hasattr(event, 'text'):
                return str(event.text)

            # Convert to string as last resort
            logger.warning(f"Unknown event format: {type(event)}")
            return str(event)

        except Exception as e:
            logger.error(f"Error extracting from event: {e}")
            return ""

    async def _wait_for_response(self, message_id: str) -> str:
        """Wait for a response to a sent message by polling get_messages."""
        start_time = asyncio.get_event_loop().time()
        poll_interval = 1.0

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > LLM_TIMEOUT_SECONDS:
                logger.warning("Timeout waiting for response")
                return ""

            try:
                messages = self.session.get_messages()
                # Look for a response event
                for msg in reversed(messages):
                    if hasattr(msg, 'data'):
                        data = msg.data
                        # Check if this is a response to our message
                        if hasattr(data, 'message_type') and 'assistant' in str(data.message_type).lower():
                            return self._extract_from_event(msg)
                        if hasattr(data, 'role') and data.role == 'assistant':
                            return self._extract_from_event(msg)
                        # Check for completion event
                        if hasattr(data, 'type') and 'completion' in str(data.type).lower():
                            return self._extract_from_event(msg)

            except Exception as e:
                logger.warning(f"Error polling messages: {e}")

            await asyncio.sleep(poll_interval)

    def _generate_mock_response(self, prompt: str) -> str:
        """Generate mock response for testing without LLM."""
        if "business requirements" in prompt.lower() or "brd" in prompt.lower():
            return """
## Business Context
This feature addresses the need for improved functionality.

## Objectives
1. Enhance user experience
2. Improve system performance
3. Maintain backward compatibility

## Functional Requirements
FR-001: The system shall provide the requested functionality.
FR-002: The system shall validate all inputs.

## Technical Requirements
TR-001: The implementation shall follow existing patterns.
TR-002: The solution shall be scalable.

## Dependencies
- Existing authentication system
- Database infrastructure

## Risks
- Integration complexity
- Testing coverage requirements
"""
        elif "epic" in prompt.lower():
            return """
EPIC-001: Core Implementation
- Description: Implement the core functionality
- Components: main-service, database
- Effort: medium

EPIC-002: Integration
- Description: Integrate with existing systems
- Components: api-gateway, auth-service
- Effort: small
"""
        else:
            return """
STORY-001: As a user, I want to use the new feature, so that I can improve my workflow.
Acceptance Criteria:
- Feature is accessible from main menu
- Feature works as expected
"""

    async def _analyze_context(
        self,
        context: AggregatedContext,
        analysis_prompt: str,
    ) -> str:
        """First stage: analyze the context."""
        components_json = json.dumps(
            [c.model_dump() for c in context.architecture.components],
            indent=2,
        )

        prompt = analysis_prompt.format(
            request=context.request,
            components=components_json,
            files_count=len(context.implementation.key_files),
        )

        response = await self._send_to_llm(prompt)
        return response

    def _build_brd_prompt(
        self,
        context: AggregatedContext,
        analysis: str,
        template: str,
    ) -> str:
        """Build the BRD generation prompt."""
        file_summaries = []
        for fc in context.implementation.key_files[:5]:
            file_summaries.append(f"- {fc.path}: {len(fc.content)} chars")

        return f"""
Generate a comprehensive Business Requirements Document for the following feature request.

Feature Request: {context.request}

Analysis:
{analysis}

Architecture Context:
- Components: {len(context.architecture.components)}
- API Contracts: {len(context.architecture.api_contracts)}
- Dependencies: {len(context.architecture.dependencies)}

Key Files:
{chr(10).join(file_summaries) or "No files analyzed"}

Similar Features Found: {', '.join(context.similar_features) or 'None'}

Template to follow:
{template if template else 'Standard BRD format'}

Generate the BRD with:
1. Business Context - Why this feature is needed
2. Objectives - Clear, measurable goals
3. Functional Requirements - What the system should do (use FR-XXX format)
4. Technical Requirements - How it should be implemented (use TR-XXX format)
5. Dependencies - What this feature depends on
6. Risks - Potential issues and mitigation strategies

Be specific and reference actual component names when possible.
"""

    def _build_epics_prompt(
        self,
        context: AggregatedContext,
        brd: BRDDocument,
    ) -> str:
        """Build prompt for epic generation."""
        requirements_summary = []
        for req in brd.functional_requirements[:5]:
            requirements_summary.append(f"- {req.id}: {req.title}")

        return f"""
Based on the following BRD, generate Epics that group related work.

Feature: {brd.title}

Business Context: {brd.business_context[:500]}

Key Requirements:
{chr(10).join(requirements_summary)}

Components Involved: {', '.join(c.name for c in context.architecture.components)}

Generate 2-4 Epics in this format:
EPIC-XXX: Title
- Description: Brief description
- Components: comma-separated list
- Effort: small/medium/large

Focus on logical groupings that can be delivered incrementally.
"""

    def _build_stories_prompt(
        self,
        context: AggregatedContext,
        epic: Epic,
    ) -> str:
        """Build prompt for user story generation."""
        return f"""
Generate User Stories for the following Epic.

Epic: {epic.title}
Description: {epic.description}
Components: {', '.join(epic.components)}

Generate 3-5 User Stories in this format:
STORY-XXX: Title
As a [role], I want [capability], so that [benefit].
Acceptance Criteria:
- Criterion 1
- Criterion 2
Technical Notes: Implementation hints

Make stories small enough to complete in 1-3 days.
"""

    def _parse_brd_response(self, response: str, request: str) -> BRDDocument:
        """Parse LLM response into BRDDocument."""
        business_context = self._extract_section(response, "Business Context") or request
        objectives = self._extract_list(response, "Objectives")
        func_reqs = self._extract_requirements(response, "Functional Requirements", "FR")
        tech_reqs = self._extract_requirements(response, "Technical Requirements", "TR")
        dependencies = self._extract_list(response, "Dependencies")
        risks = self._extract_list(response, "Risks")

        return BRDDocument(
            title=f"BRD: {request[:50]}",
            business_context=business_context,
            objectives=objectives,
            functional_requirements=func_reqs,
            technical_requirements=tech_reqs,
            dependencies=dependencies,
            risks=risks,
        )

    def _parse_epics_response(self, response: str) -> list[Epic]:
        """Parse LLM response into Epics."""
        epics = []
        epic_pattern = r"EPIC-(\d+):\s*(.+?)(?=EPIC-\d+:|$)"
        matches = re.findall(epic_pattern, response, re.DOTALL)

        for match in matches:
            epic_id = f"EPIC-{match[0]}"
            content = match[1].strip()
            lines = content.split("\n")
            title = lines[0].strip() if lines else "Untitled Epic"

            desc_match = re.search(r"Description:\s*(.+?)(?=Components:|Effort:|$)", content, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else content[:200]

            comp_match = re.search(r"Components:\s*(.+?)(?=Effort:|$)", content)
            components = []
            if comp_match:
                components = [c.strip() for c in comp_match.group(1).split(",")]

            effort_match = re.search(r"Effort:\s*(small|medium|large)", content, re.IGNORECASE)
            effort = effort_match.group(1).lower() if effort_match else "medium"

            epics.append(Epic(
                id=epic_id,
                title=title,
                description=description,
                components=components,
                estimated_effort=effort,
            ))

        if not epics:
            epics.append(Epic(
                id="EPIC-001",
                title="Core Implementation",
                description="Implement the core functionality",
                components=[],
                estimated_effort="medium",
            ))

        return epics

    def _parse_stories_response(self, response: str, epic_id: str) -> list[UserStory]:
        """Parse LLM response into UserStories."""
        stories = []
        story_pattern = r"STORY-(\d+):\s*(.+?)(?=STORY-\d+:|$)"
        matches = re.findall(story_pattern, response, re.DOTALL)

        for match in matches:
            story_id = f"STORY-{match[0]}"
            content = match[1].strip()
            lines = content.split("\n")
            title = lines[0].strip() if lines else "Untitled Story"

            as_a_match = re.search(r"As a\s+(.+?),", content)
            i_want_match = re.search(r"I want\s+(.+?),", content)
            so_that_match = re.search(r"so that\s+(.+?)(?:\.|$)", content)

            as_a = as_a_match.group(1) if as_a_match else "user"
            i_want = i_want_match.group(1) if i_want_match else "this functionality"
            so_that = so_that_match.group(1) if so_that_match else "I can achieve my goal"

            ac_section = re.search(r"Acceptance Criteria:(.+?)(?:Technical Notes:|$)", content, re.DOTALL)
            acceptance_criteria = []
            if ac_section:
                for line in ac_section.group(1).split("\n"):
                    line = line.strip().lstrip("-").strip()
                    if line:
                        acceptance_criteria.append(AcceptanceCriteria(criterion=line))

            tech_notes_match = re.search(r"Technical Notes:\s*(.+?)$", content, re.DOTALL)
            tech_notes = tech_notes_match.group(1).strip() if tech_notes_match else None

            stories.append(UserStory(
                id=story_id,
                epic_id=epic_id,
                title=title,
                description=content[:500],
                as_a=as_a,
                i_want=i_want,
                so_that=so_that,
                acceptance_criteria=acceptance_criteria,
                technical_notes=tech_notes,
            ))

        if not stories:
            stories.append(UserStory(
                id=f"STORY-{epic_id.split('-')[1]}01",
                epic_id=epic_id,
                title="Implement core functionality",
                description="Implement the main feature",
                as_a="user",
                i_want="to use the new feature",
                so_that="I can improve my workflow",
                acceptance_criteria=[
                    AcceptanceCriteria(criterion="Feature works as expected"),
                ],
            ))

        return stories

    def _extract_section(self, text: str, section_name: str) -> str:
        """Extract a section from the response."""
        pattern = rf"(?:##?\s*\d*\.?\s*)?{section_name}[:\s]*\n+(.*?)(?=(?:##?\s*\d*\.?\s*\w)|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _extract_list(self, text: str, section_name: str) -> list[str]:
        """Extract a bulleted list from a section."""
        section = self._extract_section(text, section_name)
        if not section:
            return []

        items = []
        for line in section.split("\n"):
            line = line.strip()
            line = re.sub(r"^[\d\.\-\*]+\s*", "", line)
            if line:
                items.append(line)

        return items

    def _extract_requirements(
        self,
        text: str,
        section_name: str,
        prefix: str,
    ) -> list[Requirement]:
        """Extract requirements from a section."""
        section = self._extract_section(text, section_name)
        if not section:
            return []

        requirements = []
        req_pattern = rf"({prefix}-\d+):\s*(.+?)(?={prefix}-\d+:|$)"
        matches = re.findall(req_pattern, section, re.DOTALL)

        for req_id, content in matches:
            lines = content.strip().split("\n")
            title = lines[0].strip() if lines else "Untitled"
            description = "\n".join(lines[1:]).strip() if len(lines) > 1 else title

            requirements.append(Requirement(
                id=req_id,
                title=title,
                description=description,
                priority="medium",
            ))

        if not requirements:
            items = self._extract_list(text, section_name)
            for i, item in enumerate(items, 1):
                requirements.append(Requirement(
                    id=f"{prefix}-{i:03d}",
                    title=item[:100],
                    description=item,
                    priority="medium",
                ))

        return requirements

    def _load_template(self, filename: str) -> str:
        """Load template file."""
        path = self.templates_dir / filename
        if not path.exists():
            logger.warning(f"Template not found: {filename}")
            return ""
        return path.read_text()

    def _load_prompt(self, filename: str) -> str:
        """Load prompt file."""
        prompts_dir = self.templates_dir.parent / "prompts"
        path = prompts_dir / filename
        if not path.exists():
            logger.warning(f"Prompt not found: {filename}")
            return """
Analyze the following feature request and codebase context:

Feature Request: {request}

Architecture Components:
{components}

Files Available: {files_count}

Provide:
1. Scope assessment (which components affected)
2. Integration points identified
3. Similar existing features (if any)
4. Key technical challenges
5. Recommended implementation approach

Be specific and reference actual component names and file paths.
"""
        return path.read_text()
