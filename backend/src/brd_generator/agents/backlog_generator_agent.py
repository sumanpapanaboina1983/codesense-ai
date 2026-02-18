"""Backlog Generator Agent - Generates user stories and tasks from EPICs.

This agent:
1. Breaks down EPICs into actionable backlog items
2. Maintains traceability to both EPIC and BRD
3. Generates proper user story format
4. Supports user feedback for refinement
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Callable, Optional

from ..models.epic import (
    Epic,
    BacklogItem,
    BacklogItemType,
    Priority,
    ProjectContext,
    GenerateBacklogsRequest,
    GenerateBacklogsResponse,
    RefineBacklogItemRequest,
    CoverageMatrixEntry,
    BacklogTemplateConfig,
    AnalyzeEpicsForBacklogsResponse,
    EpicAnalysisResult,
)
from ..core.epic_template_parser import EpicBacklogTemplateParser, ParsedBacklogTemplate
from ..utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Prompt Templates
# =============================================================================

BACKLOG_GENERATION_SYSTEM_PROMPT = """You are an expert Agile practitioner and user story writer. Your task is to break down EPICs into comprehensive, actionable user stories.

## Your Responsibilities:
1. Create well-structured user stories with complete documentation
2. Include clear, testable acceptance criteria
3. Maintain traceability to both EPIC and BRD sections
4. Provide implementation guidance and testing approach

## Story Sizing Guidelines (IMPORTANT):
- Stories should be BALANCED in scope - not too fine-grained and not too coarse
- Each story should represent 3-5 days of work (completable within a sprint)
- DO NOT create micro-stories for individual UI elements or trivial changes
- DO NOT create overly large stories that span multiple features
- Group related functionality together into meaningful, cohesive stories
- A good story delivers tangible, demonstrable value to the user

### Examples of GOOD story sizing:
- "Implement User Authentication with Email/Password" (includes login form, validation, API calls, session management)
- "Add Product Search with Filters" (includes search input, filter UI, API integration, results display)
- "Implement Shopping Cart Management" (includes add/remove items, quantity updates, persistence)

### Examples of BAD story sizing (too fine-grained):
- "Add email input field to login form" (too small - should be part of larger auth story)
- "Style the login button" (too small - should be part of login form story)
- "Add validation for password field" (too small - should be part of auth story)

### Examples of BAD story sizing (too coarse):
- "Implement entire e-commerce platform" (too large - should be multiple EPICs)
- "Build user management system with auth, profiles, settings, and admin" (too large - break into separate stories)

## Output Format:
Respond with a valid JSON array of user stories. Each story should have:
- id: Unique identifier (US-001, US-002, etc.)
- epic_id: Parent EPIC ID
- title: Clear, action-oriented title describing a complete feature (e.g., "Implement User Authentication with Email and Password")
- item_type: "user_story"
- description: Comprehensive description (2-3 paragraphs) explaining the feature, its purpose, key functionality, and how it delivers value
- as_a: User role (e.g., "registered user", "admin", "guest")
- i_want: Desired action/capability (a complete feature, not a tiny task)
- so_that: Expected business benefit/value
- acceptance_criteria: Array of specific, testable criteria (5-7 criteria covering the complete feature)
- priority: "critical", "high", "medium", or "low"
- brd_section_refs: Array of BRD sections this story addresses
- depends_on: Array of story IDs this depends on
- pre_conditions: Array of conditions that must be true before the story can be executed
- post_conditions: Array of conditions that must be true after successful completion
- testing_approach: Description of how to test this story (unit tests, integration tests, manual testing)
- edge_cases: Array of edge cases and error scenarios to handle
- files_to_modify: Existing files to change
- files_to_create: New files needed

## Guidelines:
- User stories should represent 3-5 days of work (completable within a sprint)
- Each story should deliver meaningful, demonstrable value
- Group related functionality together - don't split into micro-tasks
- Write comprehensive descriptions - not just one sentence
- Include 5-7 acceptance criteria per story
- Consider error handling and edge cases
- Include both happy path and error scenarios in testing approach
"""

BACKLOG_GENERATION_USER_PROMPT = """Break down the following EPIC into comprehensive, well-sized user stories:

## EPIC:
{epic_json}

## Full BRD Context:
{brd_content}

{project_context_section}

## Requirements:
1. Generate 3-5 meaningful user stories for this EPIC (quality over quantity)
2. Each story should represent 3-5 days of work - NOT micro-tasks
3. Group related functionality together into cohesive stories
4. Each story must deliver tangible, demonstrable value to users
5. Each story must have a comprehensive description (2-3 paragraphs explaining the complete feature)
6. Include 5-7 specific, testable acceptance criteria per story
7. Document pre-conditions and post-conditions
8. Include testing approach covering unit, integration, and manual testing
9. Identify edge cases and error scenarios
10. Ensure traceability to BRD sections

## IMPORTANT - Story Sizing:
- DO NOT create fine-grained micro-stories for individual UI elements
- DO NOT create stories like "Add input field" or "Style button" - these are tasks, not stories
- Each story should be a complete, valuable feature that a user can interact with
- Example: Instead of 10 small stories for login (email field, password field, button, validation, etc.), create ONE story: "Implement User Authentication with Email/Password"

{template_instructions}

Respond with a JSON array of user stories only.
"""

BACKLOG_REFINEMENT_PROMPT = """You are refining an existing backlog item based on user feedback.

## Current Item:
{current_item_json}

## Parent EPIC:
{epic_json}

## User Feedback:
{user_feedback}

## Relevant BRD Sections:
{brd_sections}

{project_context_section}

## Instructions:
1. Incorporate the user's feedback
2. Maintain traceability to BRD sections
3. Keep the same item ID and type
4. Update acceptance criteria if needed

Respond with the refined backlog item as a JSON object only.
"""


class BacklogGeneratorAgent:
    """Agent that generates backlog items from EPICs.

    Key responsibilities:
    1. Break down EPICs into actionable backlog items
    2. Maintain traceability to both EPIC and BRD
    3. Generate proper user story format
    4. Include technical details from codebase context
    5. Support template-based customization with length control
    """

    def __init__(
        self,
        copilot_session: Any = None,
        config: dict[str, Any] = None,
        template_config: Optional[BacklogTemplateConfig] = None,
        parsed_template: Optional[ParsedBacklogTemplate] = None,
    ):
        """Initialize the Backlog Generator Agent.

        Args:
            copilot_session: Copilot SDK session for LLM access
            config: Agent configuration
            template_config: Optional template configuration with length settings
            parsed_template: Optional pre-parsed template
        """
        self.session = copilot_session
        self.config = config or {}
        self.items_per_epic = config.get("items_per_epic", 5) if config else 5
        self._template_config = template_config
        self._parsed_template = parsed_template

        # Set defaults from config or use hardcoded (comprehensive story format)
        self._default_description_words = (
            template_config.default_description_words if template_config
            else 150  # Comprehensive descriptions (2-3 paragraphs)
        )
        self._default_acceptance_criteria_count = (
            template_config.default_acceptance_criteria_count if template_config
            else 7  # At least 5-7 acceptance criteria
        )
        self._default_technical_notes_words = (
            template_config.default_technical_notes_words if template_config
            else 80  # Implementation guidance
        )
        self._require_user_story_format = (
            template_config.require_user_story_format if template_config
            else True
        )

        logger.info("BacklogGeneratorAgent initialized")

    async def generate_backlogs(
        self,
        request: GenerateBacklogsRequest,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> GenerateBacklogsResponse:
        """Generate backlog items from EPICs.

        Args:
            request: The generation request with EPICs
            progress_callback: Optional callback for progress updates

        Returns:
            GenerateBacklogsResponse with generated items
        """
        logger.info(f"Generating backlogs for {len(request.epics)} EPICs")

        all_items: list[BacklogItem] = []
        items_by_epic: dict[str, list[str]] = {}

        # Filter EPICs if specific IDs provided
        epics_to_process = request.epics
        if request.epic_ids:
            epics_to_process = [e for e in request.epics if e.id in request.epic_ids]

        # Build EPIC analysis lookup for guided/auto modes
        epic_analysis_map = self._build_epic_analysis_map(request)

        # Generate items for each EPIC
        for i, epic in enumerate(epics_to_process):
            if progress_callback:
                progress_callback(f"Generating backlogs for {epic.id}: {epic.title} ({i+1}/{len(epics_to_process)})")

            # Determine item count for this EPIC
            items_count = self._determine_item_count_for_epic(
                epic=epic,
                request=request,
                epic_analysis=epic_analysis_map.get(epic.id),
            )

            items = await self._generate_items_for_epic(
                epic=epic,
                brd_markdown=request.brd_markdown,
                items_per_epic=items_count,
                include_technical_tasks=request.include_technical_tasks,
                include_spikes=request.include_spikes,
                project_context=request.project_context,
                item_offset=len(all_items),
                request=request,
                epic_analysis=epic_analysis_map.get(epic.id),
            )

            all_items.extend(items)
            items_by_epic[epic.id] = [item.id for item in items]

            if progress_callback:
                progress_callback(f"Generated {len(items)} items for {epic.id}")

        # Build coverage matrix
        coverage_matrix = self._build_coverage_matrix(all_items, request.brd_markdown)

        # Calculate summary stats (no story points - only stories by priority)
        by_type = {}
        by_priority = {}
        for item in all_items:
            by_type[item.item_type.value] = by_type.get(item.item_type.value, 0) + 1
            by_priority[item.priority.value] = by_priority.get(item.priority.value, 0) + 1

        # Calculate implementation order
        recommended_order = self._calculate_implementation_order(all_items)

        return GenerateBacklogsResponse(
            success=True,
            brd_id=request.brd_id,
            items=all_items,
            items_by_epic=items_by_epic,
            coverage_matrix=coverage_matrix,
            total_items=len(all_items),
            total_story_points=0,  # No longer tracking story points
            by_type=by_type,
            by_priority=by_priority,
            recommended_order=recommended_order,
            mode=request.mode,
            generated_at=datetime.now(),
        )

    def _build_epic_analysis_map(
        self,
        request: GenerateBacklogsRequest,
    ) -> dict[str, EpicAnalysisResult]:
        """Build a map from EPIC ID to its analysis result."""
        if not request.epic_analysis or not request.epic_analysis.epic_analyses:
            return {}

        return {
            analysis.epic_id: analysis
            for analysis in request.epic_analysis.epic_analyses
        }

    def _determine_item_count_for_epic(
        self,
        epic: Epic,
        request: GenerateBacklogsRequest,
        epic_analysis: Optional[EpicAnalysisResult],
    ) -> int:
        """Determine the target item count for a specific EPIC.

        Supports three modes:
        - 'manual': Use items_per_epic from request directly
        - 'guided': Use recommended count from analysis (if available)
        - 'auto': Let the AI decide based on analysis context
        """
        mode = request.item_count_mode or 'auto'

        if mode == 'manual':
            return request.items_per_epic

        if epic_analysis:
            if mode == 'guided':
                return epic_analysis.recommended_item_count

            # 'auto' mode - use analysis recommendation but respect items_per_epic as upper bound
            return min(epic_analysis.recommended_item_count, request.items_per_epic)

        # No analysis available, fall back to manual setting
        return request.items_per_epic

    async def _generate_items_for_epic(
        self,
        epic: Epic,
        brd_markdown: str,
        items_per_epic: int,
        include_technical_tasks: bool,
        include_spikes: bool,
        project_context: Optional[ProjectContext],
        item_offset: int = 0,
        request: Optional[GenerateBacklogsRequest] = None,
        epic_analysis: Optional[EpicAnalysisResult] = None,
    ) -> list[BacklogItem]:
        """Generate backlog items for a single EPIC."""
        logger.info(f"Generating items for EPIC: {epic.id}")

        # Build prompt
        prompt = self._build_generation_prompt(
            epic=epic,
            brd_markdown=brd_markdown,
            items_per_epic=items_per_epic,
            include_technical_tasks=include_technical_tasks,
            include_spikes=include_spikes,
            project_context=project_context,
            request=request,
            epic_analysis=epic_analysis,
        )

        # Call LLM
        response = await self._send_to_llm(prompt)

        # Parse response
        items = self._parse_items_response(response, epic.id, item_offset)

        return items

    async def refine_item(
        self,
        request: RefineBacklogItemRequest,
    ) -> BacklogItem:
        """Refine a single backlog item based on user feedback.

        Args:
            request: The refinement request with feedback

        Returns:
            Refined BacklogItem
        """
        logger.info(f"Refining item: {request.item_id}")

        # Build refinement prompt
        prompt = self._build_refinement_prompt(request)

        # Call LLM
        response = await self._send_to_llm(prompt)

        # Parse refined item
        refined_item = self._parse_single_item(response, request.current_item.epic_id, 0)

        # Preserve ID and type, increment refinement count
        refined_item.id = request.item_id
        refined_item.item_type = request.current_item.item_type
        refined_item.refinement_count = request.current_item.refinement_count + 1
        refined_item.last_feedback = request.user_feedback
        refined_item.updated_at = datetime.now()

        return refined_item

    async def regenerate_for_epic(
        self,
        epic: Epic,
        brd_markdown: str,
        feedback: Optional[str] = None,
        items_per_epic: int = 5,
        project_context: Optional[ProjectContext] = None,
    ) -> list[BacklogItem]:
        """Regenerate all backlogs for a specific EPIC."""
        logger.info(f"Regenerating all items for EPIC: {epic.id}")

        # If feedback provided, include it in the prompt
        extra_instructions = ""
        if feedback:
            extra_instructions = f"\n\n## Additional Feedback to Incorporate:\n{feedback}"

        prompt = self._build_generation_prompt(
            epic=epic,
            brd_markdown=brd_markdown + extra_instructions,
            items_per_epic=items_per_epic,
            include_technical_tasks=True,
            include_spikes=False,
            project_context=project_context,
        )

        response = await self._send_to_llm(prompt)
        items = self._parse_items_response(response, epic.id, 0)

        return items

    def _build_generation_prompt(
        self,
        epic: Epic,
        brd_markdown: str,
        items_per_epic: int,
        include_technical_tasks: bool,
        include_spikes: bool,
        project_context: Optional[ProjectContext],
        request: Optional[GenerateBacklogsRequest] = None,
        epic_analysis: Optional[EpicAnalysisResult] = None,
    ) -> str:
        """Build the backlog generation prompt with length constraints and analysis guidance."""
        project_context_section = self._format_project_context(project_context)

        # Get length settings from request or instance defaults
        desc_words = (
            request.default_description_words if request
            else self._default_description_words
        )
        ac_count = (
            request.default_acceptance_criteria_count if request
            else self._default_acceptance_criteria_count
        )

        # Get template config settings
        template_config = (request.template_config if request else None) or self._template_config
        tech_notes_words = (
            template_config.default_technical_notes_words if template_config
            else self._default_technical_notes_words
        )
        require_user_story = (
            template_config.require_user_story_format if template_config
            else self._require_user_story_format
        )

        # Build length instructions
        length_instructions = f"""
## Content Length Guidelines:
- Description: approximately {desc_words} words
- Acceptance Criteria: {ac_count} items per story
- Technical Notes: approximately {tech_notes_words} words (if included)
"""

        # Build analysis guidance section if analysis is available
        analysis_guidance = self._build_epic_analysis_guidance(epic_analysis, request)

        # User story format requirement
        format_requirement = ""
        if require_user_story:
            format_requirement = """
## User Story Format (REQUIRED):
All user stories MUST follow this format:
- As a [user role]
- I want [action/feature]
- So that [benefit/value]
"""

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

        # Limit BRD content to avoid token limits
        brd_content_limited = brd_markdown[:8000]

        # Include the actual template content if provided (from request or instance)
        actual_template = (request.backlog_template if request else None) or (
            template_config.backlog_template if template_config else None
        )

        # Build template instructions - use actual template if available
        if actual_template:
            template_instructions = f"""
## USER STORY TEMPLATE (FOLLOW THIS EXACTLY):
You MUST generate each user story following this exact template structure:

{actual_template}

IMPORTANT: Generate stories that EXACTLY follow the structure and detail level shown in the template above.
Each story should have all sections filled in with appropriate content matching the target word counts specified.
"""
        else:
            template_instructions = """
## Story Structure Requirements:
Each story MUST include:
1. **User Story Format**: As a [role], I want [action], So that [benefit]
2. **Description**: 2-3 paragraphs explaining the feature, its purpose, and key functionality (150-200 words)
3. **Acceptance Criteria**: At least 5-7 specific, testable criteria (use Given/When/Then format)
4. **Pre-conditions**: What must be true before the story executes
5. **Post-conditions**: What must be true after successful completion
6. **Testing Approach**: Unit tests, integration tests, and manual testing steps (80-100 words)
7. **Edge Cases**: Error scenarios and boundary conditions to handle
"""

        return f"""{BACKLOG_GENERATION_SYSTEM_PROMPT}

{length_instructions}

{analysis_guidance}

{format_requirement}

{template_guidelines}

{field_guidelines}

{BACKLOG_GENERATION_USER_PROMPT.format(
    epic_json=json.dumps(epic.model_dump(), indent=2, default=str),
    brd_content=brd_content_limited,
    items_per_epic=items_per_epic,
    template_instructions=template_instructions,
    project_context_section=project_context_section,
)}"""

    def _build_epic_analysis_guidance(
        self,
        epic_analysis: Optional[EpicAnalysisResult],
        request: Optional[GenerateBacklogsRequest],
    ) -> str:
        """Build guidance section from EPIC pre-analysis results."""
        if not epic_analysis:
            return ""

        parts = ["\n## Pre-Analysis Insights for this EPIC:"]

        # Complexity
        parts.append(f"- **Complexity Level**: {epic_analysis.complexity_level}")

        # Identified elements
        if epic_analysis.features_identified:
            parts.append(f"- **Features**: {', '.join(epic_analysis.features_identified)}")

        if epic_analysis.user_interactions:
            parts.append(f"- **User Interactions**: {', '.join(epic_analysis.user_interactions)}")

        if epic_analysis.technical_components:
            parts.append(f"- **Technical Components**: {', '.join(epic_analysis.technical_components)}")

        # Item count guidance
        parts.append(f"\n## Item Count Guidance:")
        parts.append(f"- **Recommended**: {epic_analysis.recommended_item_count} items")
        parts.append(f"- **Range**: {epic_analysis.min_item_count} to {epic_analysis.max_item_count} items")

        # Type breakdown
        if epic_analysis.suggested_user_stories or epic_analysis.suggested_tasks or epic_analysis.suggested_spikes:
            parts.append(f"- **Suggested User Stories**: {epic_analysis.suggested_user_stories}")

        if epic_analysis.reasoning:
            parts.append(f"- **Reasoning**: {epic_analysis.reasoning}")

        # Suggested items breakdown (if using suggested breakdown mode)
        if request and request.use_suggested_breakdown and epic_analysis.suggested_items:
            parts.append(f"\n## Suggested Stories (use as guide):")
            for i, item in enumerate(epic_analysis.suggested_items, 1):
                parts.append(f"\n### Story {i}: {item.title}")
                parts.append(f"- Scope: {item.scope}")
                parts.append(f"- Complexity: {item.complexity}")

        return "\n".join(parts)

    def _build_refinement_prompt(self, request: RefineBacklogItemRequest) -> str:
        """Build the item refinement prompt."""
        project_context_section = self._format_project_context(request.project_context)

        return BACKLOG_REFINEMENT_PROMPT.format(
            current_item_json=json.dumps(request.current_item.model_dump(), indent=2, default=str),
            epic_json=json.dumps(request.epic.model_dump(), indent=2, default=str),
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

        if ctx.estimation_method == "t_shirt":
            parts.append("- Use T-shirt sizing instead of story points")

        return "\n".join(parts)

    def _parse_items_response(
        self,
        response: str,
        epic_id: str,
        offset: int = 0,
    ) -> list[BacklogItem]:
        """Parse LLM response into BacklogItem objects."""
        try:
            # Extract JSON from response
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                json_match = re.search(r'\[[\s\S]*\]', response)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    json_str = response.strip()

            data = json.loads(json_str)

            if not isinstance(data, list):
                data = [data]

            items = []
            for i, item_data in enumerate(data):
                item = self._dict_to_item(item_data, epic_id, offset + i + 1)
                items.append(item)

            return items

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse items JSON: {e}")
            logger.debug(f"Response was: {response[:500]}")
            return []

    def _parse_single_item(self, response: str, epic_id: str, index: int) -> BacklogItem:
        """Parse a single backlog item from LLM response."""
        try:
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
            return self._dict_to_item(data, epic_id, index)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse item JSON: {e}")
            return BacklogItem(
                id=f"US-ERR",
                epic_id=epic_id,
                title="Error parsing item",
                description=f"Failed to parse: {str(e)}",
            )

    def _dict_to_item(self, data: dict, epic_id: str, index: int) -> BacklogItem:
        """Convert a dictionary to a BacklogItem object."""
        # Always use USER_STORY type (we only generate stories, not tasks)
        item_type = BacklogItemType.USER_STORY

        # Generate appropriate ID if not provided
        item_id = data.get("id")
        if not item_id:
            item_id = f"US-{index:03d}"

        # Map priority
        priority_map = {
            "critical": Priority.CRITICAL,
            "high": Priority.HIGH,
            "medium": Priority.MEDIUM,
            "low": Priority.LOW,
        }
        priority_str = str(data.get("priority", "medium")).lower()
        priority = priority_map.get(priority_str, Priority.MEDIUM)

        return BacklogItem(
            id=item_id,
            epic_id=data.get("epic_id", epic_id),
            title=data.get("title", f"Story {index}"),
            brd_section_refs=data.get("brd_section_refs", []),
            item_type=item_type,
            description=data.get("description", ""),
            as_a=data.get("as_a"),
            i_want=data.get("i_want"),
            so_that=data.get("so_that"),
            acceptance_criteria=data.get("acceptance_criteria", []),
            technical_notes=data.get("technical_notes") or data.get("implementation_notes"),
            files_to_modify=data.get("files_to_modify", []),
            files_to_create=data.get("files_to_create", []),
            priority=priority,
            depends_on=data.get("depends_on", []),
            blocks=data.get("blocks", []),
            # New comprehensive story fields
            pre_conditions=data.get("pre_conditions", []),
            post_conditions=data.get("post_conditions", []),
            testing_approach=data.get("testing_approach"),
            edge_cases=data.get("edge_cases", []),
            implementation_notes=data.get("implementation_notes"),
            ui_ux_notes=data.get("ui_ux_notes"),
        )

    def _build_coverage_matrix(
        self,
        items: list[BacklogItem],
        brd_markdown: str,
    ) -> list[CoverageMatrixEntry]:
        """Build coverage matrix from backlog items."""
        # Extract section headers from BRD
        section_pattern = r'^#{1,3}\s+(?:\d+\.?\s*)?(.+)$'
        brd_sections = []
        for line in brd_markdown.split('\n'):
            match = re.match(section_pattern, line.strip())
            if match:
                brd_sections.append(match.group(1).strip())

        # Build matrix
        matrix = []
        for section in brd_sections:
            entry = CoverageMatrixEntry(
                brd_section=section,
                brd_section_title=section,
                epic_ids=[],
                backlog_ids=[],
                is_covered=False,
            )

            for item in items:
                for ref in item.brd_section_refs:
                    if ref.lower() in section.lower() or section.lower() in ref.lower():
                        entry.backlog_ids.append(item.id)
                        entry.is_covered = True
                        break

            matrix.append(entry)

        return matrix

    def _calculate_implementation_order(self, items: list[BacklogItem]) -> list[str]:
        """Calculate recommended implementation order."""
        ordered = []
        remaining = {i.id: i for i in items}
        completed = set()

        while remaining:
            ready = []
            for item_id, item in remaining.items():
                deps_resolved = all(d in completed or d not in remaining for d in item.depends_on)
                if deps_resolved:
                    ready.append(item)

            if not ready:
                ready = sorted(remaining.values(), key=lambda i: (
                    0 if i.priority == Priority.CRITICAL else
                    1 if i.priority == Priority.HIGH else
                    2 if i.priority == Priority.MEDIUM else 3
                ))

            ready.sort(key=lambda i: (
                0 if i.priority == Priority.CRITICAL else
                1 if i.priority == Priority.HIGH else
                2 if i.priority == Priority.MEDIUM else 3,
                i.title,  # Alphabetically within same priority
            ))

            if ready:
                item = ready[0]
                ordered.append(item.id)
                completed.add(item.id)
                del remaining[item.id]

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
                    self.session.send_and_wait(message_options, timeout=180),
                    timeout=180
                )
                if event:
                    return self._extract_from_event(event)

            if hasattr(self.session, 'send'):
                await self.session.send(message_options)
                return await self._wait_for_response(180)

        except asyncio.TimeoutError:
            logger.error("LLM request timed out after 180 seconds")
        except Exception as e:
            logger.error(f"LLM error: {type(e).__name__}: {str(e) or 'No error message'}")

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
                "id": "US-001",
                "epic_id": "EPIC-001",
                "title": "Implement User Login with Email and Password",
                "item_type": "user_story",
                "description": "Create a secure and user-friendly login form that allows registered users to authenticate using their email and password credentials. The form should provide real-time validation feedback, handle various error states gracefully, and ensure a smooth transition to the user dashboard upon successful authentication.\n\nThe login functionality is a critical entry point for the application and must meet security best practices including rate limiting, secure credential transmission, and session management. The implementation should also support remember-me functionality and integrate with the existing authentication infrastructure.",
                "as_a": "registered user",
                "i_want": "to log in to my account using my email and password",
                "so_that": "I can access my personalized dashboard and features",
                "acceptance_criteria": [
                    "Login form displays email and password input fields",
                    "Email field validates format in real-time",
                    "Password field has show/hide toggle button",
                    "Submit button is disabled until both fields have valid input",
                    "Loading indicator displays during authentication",
                    "Error message shows for invalid credentials",
                    "User is redirected to dashboard on successful login"
                ],
                "priority": "high",
                "brd_section_refs": ["2.1 Authentication Requirements"],
                "depends_on": [],
                "pre_conditions": [
                    "User has a registered account",
                    "Authentication service is available",
                    "Database contains user credentials"
                ],
                "post_conditions": [
                    "User session is created with valid token",
                    "User is redirected to dashboard",
                    "Last login timestamp is updated"
                ],
                "testing_approach": "Unit tests for form validation logic. Integration tests for authentication API calls. E2E tests for complete login flow including error states. Security testing for credential handling.",
                "edge_cases": [
                    "User enters incorrect password multiple times",
                    "User account is locked or disabled",
                    "Session expires during login process",
                    "Network connection lost during authentication"
                ],
                "implementation_notes": "Use React Hook Form for form state management. Implement JWT token storage in httpOnly cookies for security. Add rate limiting on backend to prevent brute force attacks.",
                "ui_ux_notes": "Form should be centered on the page with clear visual hierarchy. Error messages should be inline and descriptive. Consider accessibility requirements for screen readers.",
                "files_to_modify": ["src/components/Login.tsx", "src/services/auth.ts"],
                "files_to_create": ["src/hooks/useAuth.ts", "src/components/LoginForm.tsx"],
            },
            {
                "id": "US-002",
                "epic_id": "EPIC-001",
                "title": "Implement Password Reset via Email",
                "item_type": "user_story",
                "description": "Implement a secure password reset flow that allows users who have forgotten their password to regain access to their account through email verification. The flow should generate a time-limited secure token, send a reset link to the user's registered email, and provide a form to set a new password.\n\nThis feature must balance security (preventing unauthorized access) with usability (making the process straightforward for legitimate users). The reset tokens should expire after a reasonable timeframe and be single-use to prevent replay attacks.",
                "as_a": "user who forgot their password",
                "i_want": "to reset my password via email",
                "so_that": "I can regain access to my account securely",
                "acceptance_criteria": [
                    "Reset request form accepts email address",
                    "System validates email exists in database",
                    "Secure reset link is sent to registered email",
                    "Reset link expires after 24 hours",
                    "Reset link can only be used once",
                    "New password must meet security requirements",
                    "User receives confirmation after successful reset"
                ],
                "priority": "medium",
                "brd_section_refs": ["2.1 Authentication", "2.2 Security Requirements"],
                "depends_on": ["US-001"],
                "pre_conditions": [
                    "User has a registered account with valid email",
                    "Email service is configured and operational"
                ],
                "post_conditions": [
                    "User password is updated in database",
                    "All existing sessions are invalidated",
                    "Password reset token is marked as used"
                ],
                "testing_approach": "Unit tests for token generation and validation. Integration tests for email sending. E2E tests for complete reset flow. Security tests for token expiration and single-use enforcement.",
                "edge_cases": [
                    "User requests reset for non-existent email",
                    "User clicks expired reset link",
                    "User tries to reuse reset link",
                    "Email delivery fails"
                ],
                "implementation_notes": "Generate cryptographically secure tokens using crypto.randomBytes(). Store hashed tokens in database with expiration timestamp. Use email queue for reliable delivery.",
                "ui_ux_notes": "Show generic success message even for non-existent emails (security). Provide clear instructions in reset email. Show password strength meter on new password form.",
                "files_to_modify": ["src/services/auth.ts"],
                "files_to_create": ["src/pages/ResetPassword.tsx", "src/components/ResetPasswordForm.tsx"],
            },
        ])
