"""EPIC Generator Agent - Generates EPICs from BRD with user feedback support.

This agent:
1. Analyzes BRD content to identify logical EPIC groupings
2. Generates EPICs with BRD section traceability
3. Supports user feedback for refinement
4. Ensures coverage of all BRD requirements
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Callable, Optional

from ..models.epic import (
    Epic,
    Priority,
    EpicStatus,
    EffortSize,
    ProjectContext,
    GenerateEpicsRequest,
    GenerateEpicsResponse,
    RefineEpicRequest,
    CoverageMatrixEntry,
    EpicTemplateConfig,
    BRDAnalysisResult,
)
from ..core.epic_template_parser import EpicBacklogTemplateParser, ParsedEpicTemplate
from ..utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Prompt Templates
# =============================================================================

EPIC_GENERATION_SYSTEM_PROMPT = """You are an expert Product Manager and Agile practitioner. Your task is to analyze a Business Requirements Document (BRD) and generate well-structured EPICs.

## Your Responsibilities:
1. Identify logical groupings of requirements that form EPICs
2. Ensure each EPIC has clear business value
3. Maintain traceability to BRD sections
4. Consider dependencies between EPICs
5. Provide effort estimates

## Output Format:
You must respond with a valid JSON array of EPICs. Each EPIC should have:
- id: Unique identifier (EPIC-001, EPIC-002, etc.)
- title: Concise title (max 100 chars)
- description: Detailed description
- brd_section_refs: Array of BRD section references this EPIC covers
- business_value: Why this EPIC matters to the business
- objectives: Array of key objectives
- acceptance_criteria: Array of high-level acceptance criteria
- depends_on: Array of EPIC IDs this depends on (empty for first EPICs)
- affected_components: Array of system components affected

## Guidelines:
- Create 3-10 EPICs depending on BRD complexity
- Each EPIC should be independently deliverable
- EPICs should not overlap in scope
- Ensure all BRD sections are covered by at least one EPIC
- Order EPICs by dependency (independent EPICs first)
"""

EPIC_GENERATION_USER_PROMPT = """Analyze the following BRD and generate EPICs:

## BRD Content:
{brd_content}

## BRD ID: {brd_id}

{project_context_section}

## Requirements:
1. Generate {max_epics} EPICs maximum
2. Ensure every BRD section is covered by at least one EPIC
3. Identify dependencies between EPICs
4. Provide realistic effort estimates

Respond with a JSON array of EPICs only, no additional text.
"""

EPIC_REFINEMENT_PROMPT = """You are refining an existing EPIC based on user feedback.

## Current EPIC:
{current_epic_json}

## User Feedback:
{user_feedback}

## Relevant BRD Sections for Context:
{brd_sections}

{project_context_section}

## Instructions:
1. Incorporate the user's feedback into the EPIC
2. Maintain traceability to BRD sections
3. Keep the same EPIC ID
4. Update any affected fields (title, description, acceptance criteria, etc.)

Respond with the refined EPIC as a JSON object only.
"""


class EpicGeneratorAgent:
    """Agent that generates EPICs from BRD content.

    Key responsibilities:
    1. Parse BRD to identify logical groupings for EPICs
    2. Generate EPICs with proper BRD section references
    3. Ensure coverage of all BRD requirements
    4. Handle user feedback for refinement
    5. Support template-based customization with length control
    """

    def __init__(
        self,
        copilot_session: Any = None,
        config: dict[str, Any] = None,
        template_config: Optional[EpicTemplateConfig] = None,
        parsed_template: Optional[ParsedEpicTemplate] = None,
    ):
        """Initialize the EPIC Generator Agent.

        Args:
            copilot_session: Copilot SDK session for LLM access
            config: Agent configuration
            template_config: Optional template configuration with length settings
            parsed_template: Optional pre-parsed template
        """
        self.session = copilot_session
        self.config = config or {}
        self.max_epics = config.get("max_epics", 10) if config else 10
        self._template_config = template_config
        self._parsed_template = parsed_template

        # Set defaults from config or use hardcoded
        self._default_description_words = (
            template_config.default_description_words if template_config
            else 150
        )
        self._default_business_value_words = (
            template_config.default_business_value_words if template_config
            else 100
        )
        self._default_objectives_count = (
            template_config.default_objectives_count if template_config
            else 3
        )
        self._default_acceptance_criteria_count = (
            template_config.default_acceptance_criteria_count if template_config
            else 5
        )

        logger.info("EpicGeneratorAgent initialized")

    async def generate_epics(
        self,
        request: GenerateEpicsRequest,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> GenerateEpicsResponse:
        """Generate EPICs from BRD content.

        Args:
            request: The generation request with BRD content
            progress_callback: Optional callback for progress updates

        Returns:
            GenerateEpicsResponse with generated EPICs
        """
        logger.info(f"Generating EPICs for BRD: {request.brd_id}")

        if progress_callback:
            progress_callback("Analyzing BRD structure...")

        # Build the prompt
        prompt = self._build_generation_prompt(request)

        if progress_callback:
            progress_callback("Generating EPICs from BRD requirements...")

        # Call LLM
        response = await self._send_to_llm(prompt)

        if progress_callback:
            progress_callback("Parsing generated EPICs...")

        # Parse response into EPICs
        epics = self._parse_epics_response(response, request.brd_id)

        if progress_callback:
            progress_callback(f"Generated {len(epics)} EPICs")

        # Build coverage matrix
        coverage_matrix, uncovered = self._build_coverage_matrix(
            epics, request.brd_markdown
        )

        # Determine recommended order
        recommended_order = self._calculate_implementation_order(epics)

        return GenerateEpicsResponse(
            success=True,
            brd_id=request.brd_id,
            brd_title=request.brd_title,
            epics=epics,
            coverage_matrix=coverage_matrix,
            uncovered_sections=uncovered,
            total_epics=len(epics),
            recommended_order=recommended_order,
            mode=request.mode,
            generated_at=datetime.now(),
        )

    async def refine_epic(
        self,
        request: RefineEpicRequest,
    ) -> Epic:
        """Refine a single EPIC based on user feedback.

        Args:
            request: The refinement request with feedback

        Returns:
            Refined Epic
        """
        logger.info(f"Refining EPIC: {request.epic_id}")

        # Build refinement prompt
        prompt = self._build_refinement_prompt(request)

        # Call LLM
        response = await self._send_to_llm(prompt)

        # Parse refined EPIC
        refined_epic = self._parse_single_epic(response, request.current_epic.brd_id)

        # Preserve ID and increment refinement count
        refined_epic.id = request.epic_id
        refined_epic.refinement_count = request.current_epic.refinement_count + 1
        refined_epic.last_feedback = request.user_feedback
        refined_epic.updated_at = datetime.now()

        return refined_epic

    async def refine_all_epics(
        self,
        epics: list[Epic],
        global_feedback: str,
        brd_markdown: str,
        project_context: Optional[ProjectContext] = None,
    ) -> list[Epic]:
        """Apply global feedback to all EPICs.

        Args:
            epics: Current list of EPICs
            global_feedback: Feedback to apply to all
            brd_markdown: BRD content for context
            project_context: Optional project context

        Returns:
            List of refined EPICs
        """
        logger.info(f"Refining all {len(epics)} EPICs with global feedback")

        prompt = f"""You are refining a set of EPICs based on global user feedback.

## Current EPICs:
{json.dumps([e.model_dump() for e in epics], indent=2, default=str)}

## Global Feedback to Apply:
{global_feedback}

## BRD Context:
{brd_markdown[:5000]}...

{self._format_project_context(project_context)}

## Instructions:
1. Apply the global feedback to ALL EPICs where applicable
2. Maintain all existing EPIC IDs
3. Keep traceability to BRD sections
4. Update any affected fields consistently across all EPICs

Respond with a JSON array of all refined EPICs.
"""

        response = await self._send_to_llm(prompt)
        refined_epics = self._parse_epics_response(response, epics[0].brd_id if epics else "")

        # Preserve original IDs and update metadata
        for i, epic in enumerate(refined_epics):
            if i < len(epics):
                epic.id = epics[i].id
                epic.refinement_count = epics[i].refinement_count + 1
                epic.last_feedback = global_feedback
                epic.updated_at = datetime.now()

        return refined_epics

    def _build_generation_prompt(self, request: GenerateEpicsRequest) -> str:
        """Build the EPIC generation prompt with length constraints and analysis guidance."""
        project_context_section = self._format_project_context(request.project_context)

        # Get length settings from request or instance defaults
        desc_words = request.default_description_words or self._default_description_words
        biz_value_words = request.default_business_value_words or self._default_business_value_words

        # Get counts from template config if available
        template_config = request.template_config or self._template_config
        objectives_count = (
            template_config.default_objectives_count if template_config
            else self._default_objectives_count
        )
        ac_count = (
            template_config.default_acceptance_criteria_count if template_config
            else self._default_acceptance_criteria_count
        )

        # Determine EPIC count based on analysis or manual setting
        epic_count = self._determine_epic_count(request)

        # Build length instructions
        length_instructions = f"""
## Content Length Guidelines:
- Description: approximately {desc_words} words
- Business Value: approximately {biz_value_words} words
- Objectives: {objectives_count} items
- Acceptance Criteria: {ac_count} items
"""

        # Build analysis guidance section if analysis is available
        analysis_guidance = self._build_analysis_guidance(request)

        # Include custom template guidelines if provided
        template_guidelines = ""
        if self._parsed_template and self._parsed_template.writing_guidelines:
            template_guidelines = "\n## Template Guidelines:\n" + "\n".join(
                f"- {g}" for g in self._parsed_template.writing_guidelines
            )

        # Include field-specific guidelines from template config
        field_guidelines = ""
        if template_config and template_config.field_configs:
            active_fields = [f for f in template_config.field_configs if f.enabled]
            if active_fields:
                field_guidelines = "\n## Field-Specific Guidelines:\n"
                for field in active_fields:
                    if field.guidelines:
                        field_guidelines += f"- {field.field_name}: {field.guidelines}\n"
                    else:
                        field_guidelines += f"- {field.field_name}: ~{field.target_words} words\n"

        return f"""{EPIC_GENERATION_SYSTEM_PROMPT}

{length_instructions}

{analysis_guidance}

{template_guidelines}

{field_guidelines}

{EPIC_GENERATION_USER_PROMPT.format(
    brd_content=request.brd_markdown,
    brd_id=request.brd_id,
    max_epics=epic_count,
    project_context_section=project_context_section,
)}"""

    def _determine_epic_count(self, request: GenerateEpicsRequest) -> int:
        """Determine the target EPIC count based on mode and analysis.

        Supports three modes:
        - 'manual': Use max_epics from request directly
        - 'guided': Use recommended count from analysis (if available)
        - 'auto': Let the AI decide based on analysis context
        """
        mode = request.epic_count_mode or 'auto'

        if mode == 'manual':
            return request.max_epics

        if mode == 'guided' and request.brd_analysis:
            return request.brd_analysis.recommended_epic_count

        # 'auto' mode - use analysis recommendation as guidance or fall back to max_epics
        if request.brd_analysis:
            # Use the recommended count but respect max_epics as upper bound
            return min(
                request.brd_analysis.recommended_epic_count,
                request.max_epics
            )

        return request.max_epics

    def _build_analysis_guidance(self, request: GenerateEpicsRequest) -> str:
        """Build guidance section from pre-analysis results."""
        if not request.brd_analysis:
            return ""

        analysis = request.brd_analysis
        parts = ["\n## Pre-Analysis Insights:"]

        # Complexity assessment
        parts.append(f"- **Complexity Level**: {analysis.complexity_level}")
        if analysis.complexity_factors:
            parts.append(f"- **Complexity Factors**: {', '.join(analysis.complexity_factors)}")

        # Identified areas
        if analysis.functional_areas:
            parts.append(f"- **Functional Areas**: {', '.join(analysis.functional_areas)}")

        if analysis.user_journeys:
            parts.append(f"- **User Journeys**: {', '.join(analysis.user_journeys)}")

        if analysis.user_personas:
            parts.append(f"- **User Personas**: {', '.join(analysis.user_personas)}")

        if analysis.integration_points:
            parts.append(f"- **Integration Points**: {', '.join(analysis.integration_points)}")

        # EPIC count guidance
        parts.append(f"\n## EPIC Count Guidance:")
        parts.append(f"- **Recommended**: {analysis.recommended_epic_count} EPICs")
        parts.append(f"- **Range**: {analysis.min_epic_count} to {analysis.max_epic_count} EPICs")

        if analysis.recommendation_reasoning:
            parts.append(f"- **Reasoning**: {analysis.recommendation_reasoning}")

        # Suggested breakdown (if using suggested breakdown mode)
        if request.use_suggested_breakdown and analysis.suggested_epics:
            parts.append(f"\n## Suggested EPIC Structure (use as guide):")
            for i, epic in enumerate(analysis.suggested_epics, 1):
                parts.append(f"\n### EPIC {i}: {epic.name}")
                parts.append(f"- Scope: {epic.scope}")
                if epic.brd_sections:
                    parts.append(f"- BRD Sections: {', '.join(epic.brd_sections)}")
                parts.append(f"- Estimated Stories: {epic.estimated_stories}")
                parts.append(f"- Complexity: {epic.complexity}")
                if epic.reasoning:
                    parts.append(f"- Reasoning: {epic.reasoning}")

        # Warnings
        if analysis.warnings:
            parts.append(f"\n## Notes:")
            for warning in analysis.warnings:
                parts.append(f"- {warning}")

        return "\n".join(parts)

    def _build_refinement_prompt(self, request: RefineEpicRequest) -> str:
        """Build the EPIC refinement prompt."""
        project_context_section = self._format_project_context(request.project_context)

        return EPIC_REFINEMENT_PROMPT.format(
            current_epic_json=json.dumps(request.current_epic.model_dump(), indent=2, default=str),
            user_feedback=request.user_feedback,
            brd_sections="\n".join(request.brd_sections_content),
            project_context_section=project_context_section,
        )

    def _format_project_context(self, ctx: Optional[ProjectContext]) -> str:
        """Format project context for prompt."""
        if not ctx:
            return ""

        parts = ["## Project Context:"]

        if ctx.tech_stack:
            parts.append(f"- Tech Stack: {', '.join(ctx.tech_stack)}")

        if ctx.terminology:
            terms = [f"'{k}' → '{v}'" for k, v in ctx.terminology.items()]
            parts.append(f"- Terminology: {', '.join(terms)}")

        if ctx.conventions:
            parts.append("- Team Conventions:")
            for conv in ctx.conventions:
                parts.append(f"  - {conv}")

        if ctx.estimation_method:
            parts.append(f"- Estimation: {ctx.estimation_method}")

        return "\n".join(parts)

    def _parse_epics_response(self, response: str, brd_id: str) -> list[Epic]:
        """Parse LLM response into Epic objects."""
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                # Try to find JSON array directly
                json_match = re.search(r'\[[\s\S]*\]', response)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    json_str = response.strip()

            data = json.loads(json_str)

            if not isinstance(data, list):
                data = [data]

            epics = []
            for i, item in enumerate(data):
                epic = self._dict_to_epic(item, brd_id, i + 1)
                epics.append(epic)

            return epics

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse EPICs JSON: {e}")
            logger.debug(f"Response was: {response[:500]}")
            return []

    def _parse_single_epic(self, response: str, brd_id: str) -> Epic:
        """Parse a single EPIC from LLM response."""
        try:
            # Extract JSON from response
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    json_str = response.strip()

            data = json.loads(json_str)
            return self._dict_to_epic(data, brd_id, 1)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse EPIC JSON: {e}")
            # Return a placeholder epic
            return Epic(
                id="EPIC-ERR",
                title="Error parsing EPIC",
                description=f"Failed to parse LLM response: {str(e)}",
                brd_id=brd_id,
                business_value="N/A",
            )

    def _dict_to_epic(self, data: dict, brd_id: str, index: int) -> Epic:
        """Convert a dictionary to an Epic object."""
        return Epic(
            id=data.get("id", f"EPIC-{index:03d}"),
            title=data.get("title", f"Epic {index}"),
            description=data.get("description", ""),
            brd_id=brd_id,
            brd_section_refs=data.get("brd_section_refs", []),
            business_value=data.get("business_value", ""),
            objectives=data.get("objectives", []),
            acceptance_criteria=data.get("acceptance_criteria", []),
            status=EpicStatus.DRAFT,
            estimated_story_count=data.get("estimated_story_count"),
            depends_on=data.get("depends_on", []),
            blocks=data.get("blocks", []),
            affected_components=data.get("affected_components", []),
            technical_notes=data.get("technical_notes"),
        )

    def _build_coverage_matrix(
        self,
        epics: list[Epic],
        brd_markdown: str,
    ) -> tuple[list[CoverageMatrixEntry], list[str]]:
        """Build coverage matrix from EPICs and BRD.

        Returns:
            Tuple of (coverage_matrix, uncovered_sections)
        """
        # Extract section headers from BRD markdown
        section_pattern = r'^#{1,3}\s+(?:\d+\.?\s*)?(.+)$'
        brd_sections = []
        for line in brd_markdown.split('\n'):
            match = re.match(section_pattern, line.strip())
            if match:
                section_name = match.group(1).strip()
                # Normalize section references
                brd_sections.append(section_name)

        # Build matrix
        matrix = []
        covered_sections = set()

        for section in brd_sections:
            entry = CoverageMatrixEntry(
                brd_section=section,
                brd_section_title=section,
                epic_ids=[],
                backlog_ids=[],
                is_covered=False,
            )

            # Find EPICs that cover this section
            for epic in epics:
                for ref in epic.brd_section_refs:
                    if ref.lower() in section.lower() or section.lower() in ref.lower():
                        entry.epic_ids.append(epic.id)
                        entry.is_covered = True
                        covered_sections.add(section)
                        break

            matrix.append(entry)

        # Find uncovered sections
        uncovered = [s for s in brd_sections if s not in covered_sections]

        return matrix, uncovered

    def _calculate_implementation_order(self, epics: list[Epic]) -> list[str]:
        """Calculate recommended implementation order based on dependencies."""
        # Topological sort based on depends_on
        ordered = []
        remaining = {e.id: e for e in epics}
        completed = set()

        while remaining:
            # Find EPICs with no unresolved dependencies
            ready = []
            for epic_id, epic in remaining.items():
                deps_resolved = all(d in completed or d not in remaining for d in epic.depends_on)
                if deps_resolved:
                    ready.append(epic)

            if not ready:
                # Circular dependency or all have deps - add remaining by title
                ready = sorted(remaining.values(), key=lambda e: e.title)

            # Sort ready EPICs by title for consistent ordering
            ready.sort(key=lambda e: e.title)

            # Add first ready EPIC to order
            if ready:
                epic = ready[0]
                ordered.append(epic.id)
                completed.add(epic.id)
                del remaining[epic.id]

        return ordered

    async def _send_to_llm(self, prompt: str) -> str:
        """Send prompt to LLM via Copilot SDK."""
        if not self.session:
            logger.warning("No Copilot session, returning mock response")
            return self._generate_mock_response()

        try:
            import asyncio

            message_options = {"prompt": prompt}

            if hasattr(self.session, 'send_and_wait'):
                event = await asyncio.wait_for(
                    self.session.send_and_wait(message_options, timeout=120),
                    timeout=120
                )
                if event:
                    return self._extract_from_event(event)

            if hasattr(self.session, 'send'):
                await self.session.send(message_options)
                return await self._wait_for_response(120)

        except Exception as e:
            logger.error(f"LLM error: {e}")

        return self._generate_mock_response()

    def _extract_from_event(self, event: Any) -> str:
        """Extract text content from a Copilot event."""
        try:
            if hasattr(event, 'data'):
                data = event.data
                if hasattr(data, 'message') and hasattr(data.message, 'content'):
                    return str(data.message.content)
                if hasattr(data, 'content'):
                    return str(data.content)
                if hasattr(data, 'text'):
                    return str(data.text)

            if hasattr(event, 'content'):
                return str(event.content)
            if hasattr(event, 'text'):
                return str(event.text)

            return str(event)
        except Exception as e:
            logger.error(f"Error extracting from event: {e}")
            return ""

    async def _wait_for_response(self, timeout: float) -> str:
        """Wait for LLM response by polling."""
        import asyncio
        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                return ""

            try:
                messages = self.session.get_messages()
                for msg in reversed(messages):
                    if hasattr(msg, 'data'):
                        data = msg.data
                        if hasattr(data, 'role') and data.role == 'assistant':
                            return self._extract_from_event(msg)
            except Exception:
                pass

            await asyncio.sleep(1.0)

    def _generate_mock_response(self) -> str:
        """Generate mock response for testing."""
        return json.dumps([
            {
                "id": "EPIC-001",
                "title": "User Authentication & Authorization",
                "description": "Implement comprehensive user authentication and role-based access control",
                "brd_section_refs": ["2.1", "2.2"],
                "business_value": "Enable secure access to the platform",
                "objectives": ["Implement login/logout", "Add role-based permissions"],
                "acceptance_criteria": ["Users can log in with email/password", "Admins can manage roles"],
                "depends_on": [],
                "affected_components": ["auth-service", "user-service"],
            },
            {
                "id": "EPIC-002",
                "title": "Core Feature Implementation",
                "description": "Implement the main business features described in the BRD",
                "brd_section_refs": ["3.1", "3.2", "3.3"],
                "business_value": "Deliver primary value to users",
                "objectives": ["Build core workflows", "Implement data management"],
                "acceptance_criteria": ["Users can perform main actions", "Data is persisted correctly"],
                "depends_on": ["EPIC-001"],
                "affected_components": ["api-service", "database"],
            },
        ])
