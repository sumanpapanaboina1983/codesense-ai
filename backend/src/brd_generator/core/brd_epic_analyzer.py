"""BRD and EPIC Analyzer for Intelligent Count Determination.

This module provides intelligent analysis of BRD documents and EPICs to determine
optimal counts for EPIC and Backlog generation, mimicking how experienced PMs/BAs
approach decomposition.

Phase 1: Pre-analysis before generation
Phase 2: Dynamic adjustment during generation
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional

from ..models.epic import (
    AnalyzeBRDRequest,
    AnalyzeEpicsForBacklogsRequest,
    AnalyzeEpicsForBacklogsResponse,
    BRDAnalysisResult,
    Epic,
    EpicAnalysisResult,
    SuggestedBacklogBreakdown,
    SuggestedEpicBreakdown,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Analysis Prompts
# =============================================================================

ANALYSIS_FOCUS_PROMPTS = {
    "functional_areas": """
Focus on identifying distinct FUNCTIONAL AREAS in the BRD:
- Each major functional domain should become its own EPIC
- Examples: User Management, Payment Processing, Reporting, Notifications
- Look for module/feature boundaries in the requirements
""",
    "user_journeys": """
Focus on identifying distinct USER JOURNEYS in the BRD:
- Each complete user workflow should become its own EPIC
- Examples: Customer Onboarding Flow, Checkout Flow, Support Ticket Resolution
- Follow the user through their end-to-end experience
""",
    "technical_components": """
Focus on identifying distinct TECHNICAL COMPONENTS in the BRD:
- Each major technical layer or component should become its own EPIC
- Examples: Authentication Service, API Gateway, Data Migration, Third-party Integrations
- Consider architectural boundaries and deployable units
""",
    "business_capabilities": """
Focus on identifying distinct BUSINESS CAPABILITIES in the BRD:
- Each business value stream should become its own EPIC
- Examples: Revenue Generation, Customer Retention, Compliance, Analytics
- Align EPICs with business outcomes and KPIs
""",
    "integrations": """
Focus on INTEGRATION POINTS in the BRD:
- Each external system integration should be considered for its own EPIC
- Examples: Payment Gateway Integration, CRM Sync, Email Service, Analytics Platform
- Consider the complexity and risk of each integration
""",
    "user_personas": """
Focus on USER PERSONAS mentioned in the BRD:
- Each user type's needs may warrant dedicated EPICs
- Examples: Admin Portal EPIC, Customer-facing Features EPIC, Partner Features EPIC
- Group requirements by who benefits from them
""",
}

BRD_ANALYSIS_SYSTEM_PROMPT = """You are an expert Product Manager and Business Analyst with 15+ years of experience
decomposing Business Requirements Documents into EPICs for agile delivery.

Your task is to analyze a BRD document and determine the optimal number and structure of EPICs.

## How Experienced PMs/BAs Approach EPIC Decomposition:

1. **Identify Functional Domains**: Each distinct functional area (e.g., Authentication, Payments, Reporting)
   typically becomes its own EPIC.

2. **Map User Journeys**: Different user journeys or workflows often warrant separate EPICs
   (e.g., Customer Onboarding, Checkout Flow, Admin Management).

3. **Assess Business Value Streams**: Each independently deliverable value stream should be an EPIC.

4. **Apply Size Constraints**:
   - An EPIC should be deliverable in 2-6 weeks (1-3 sprints)
   - If too large, split into multiple EPICs
   - If too small, it might just be a user story

5. **Consider Dependencies**:
   - Tightly coupled features → same EPIC
   - Loosely coupled features → separate EPICs

6. **Vertical Slicing**: Each EPIC should deliver end-to-end value, not be a horizontal layer
   (e.g., "User can search products" not "Backend search API").

## EPIC Sizing Guidelines:

| BRD Size | Typical EPIC Count |
|----------|-------------------|
| Small (2-5 pages) | 1-3 EPICs |
| Medium (5-15 pages) | 3-6 EPICs |
| Large (15-30 pages) | 6-12 EPICs |
| Enterprise (30+ pages) | 10-25+ EPICs |

## Analysis Checklist:
- Count major sections/features in the BRD
- Identify distinct user roles/personas
- Note external integrations (each may need an EPIC or add complexity)
- Assess technical complexity
- Consider cross-cutting concerns (security, logging, etc.)
"""

BRD_ANALYSIS_USER_PROMPT = """Analyze this BRD document and provide a detailed recommendation for EPIC decomposition.

## BRD Document:
{brd_content}

## Analysis Focus:
{analysis_focus_instructions}

## Analysis Preferences:
- EPIC Size Preference: {epic_size_preference}
- Team Velocity (if provided): {team_velocity}
- Target Sprint Count (if provided): {target_sprint_count}

{user_feedback_section}

{previous_epics_section}

## Required Output (JSON):
```json
{{
    "functional_areas": ["Area 1", "Area 2", ...],
    "user_journeys": ["Journey 1", "Journey 2", ...],
    "user_personas": ["Persona 1", "Persona 2", ...],
    "integration_points": ["Integration 1", ...],
    "complexity_level": "low|medium|high|very_high",
    "complexity_factors": ["Factor 1", "Factor 2", ...],
    "section_count": 5,
    "requirement_count": 25,
    "recommended_epic_count": 4,
    "min_epic_count": 3,
    "max_epic_count": 6,
    "recommendation_reasoning": "Detailed explanation...",
    "suggested_epics": [
        {{
            "id": "epic-1",
            "name": "EPIC Name",
            "scope": "What this EPIC covers",
            "brd_sections": ["2.1", "2.2"],
            "estimated_stories": 5,
            "complexity": "medium",
            "reasoning": "Why this should be a separate EPIC"
        }}
    ],
    "warnings": ["Any concerns or considerations"]
}}
```

IMPORTANT:
- Generate unique IDs for each suggested EPIC (e.g., "epic-1", "epic-2")
- Each EPIC should have a clear, descriptive NAME that conveys its purpose
- Focus on providing actionable, practical recommendations based on real-world agile practices.
"""

BACKLOG_FOCUS_PROMPTS = {
    "user_stories": """
Focus on USER-FACING FUNCTIONALITY:
- Prioritize user stories that deliver visible value to end users
- Use "As a... I want... So that..." format
- Each story should be independently testable and deployable
""",
    "technical_tasks": """
Focus on TECHNICAL IMPLEMENTATION TASKS:
- Include database schema changes, API endpoints, infrastructure setup
- Break down backend work into discrete, estimable tasks
- Consider deployment and DevOps requirements
""",
    "testing": """
Focus on TESTING AND QUALITY ASSURANCE:
- Include test scenarios, test data setup, automation tasks
- Consider unit tests, integration tests, E2E tests, performance tests
- Add tasks for test environment setup if needed
""",
    "integration": """
Focus on INTEGRATION WORK:
- Break down each external integration into specific tasks
- Include authentication, data mapping, error handling
- Consider webhooks, callbacks, sync mechanisms
""",
    "ui_ux": """
Focus on UI/UX IMPLEMENTATION:
- Break down each screen or component into stories
- Include responsive design considerations
- Consider accessibility requirements (WCAG)
""",
    "data_migration": """
Focus on DATA MIGRATION tasks:
- Include data extraction, transformation, loading tasks
- Consider data validation and cleanup
- Add rollback procedures and verification steps
""",
}

EPIC_ANALYSIS_SYSTEM_PROMPT = """You are an expert Scrum Master and Technical Lead with extensive experience
breaking down EPICs into well-sized user stories and tasks.

Your task is to analyze EPICs and determine the optimal backlog item decomposition.

## How to Decompose an EPIC into Backlog Items:

1. **Identify User Interactions**: Each distinct user action/interaction is a potential story.

2. **Consider CRUD Operations**: For data entities, consider Create, Read, Update, Delete operations.

3. **Map to Acceptance Criteria**: Each EPIC acceptance criterion often becomes 1-3 user stories.

4. **Include Technical Tasks**:
   - Database schema changes
   - API endpoint creation
   - Integration setup
   - Security implementation

5. **Add Spikes for Unknowns**: If there's technical uncertainty, add a research spike.

6. **Apply INVEST Criteria**: Each story should be:
   - Independent
   - Negotiable
   - Valuable
   - Estimable
   - Small
   - Testable

## Sizing Guidelines:

| EPIC Complexity | Typical Item Count |
|-----------------|-------------------|
| Simple | 3-5 items |
| Medium | 5-8 items |
| Complex | 8-12 items |
| Very Complex | 12-20 items |

## Item Type Guidelines:
- **User Stories**: User-facing functionality (60-70% of items)
- **Tasks**: Technical implementation work (20-30% of items)
- **Spikes**: Research/investigation (5-10% of items, only when needed)
"""

EPIC_ANALYSIS_USER_PROMPT = """Analyze this EPIC and determine the optimal backlog item decomposition.

## EPIC Details:
- ID: {epic_id}
- Title: {epic_title}
- Description: {epic_description}
- Business Value: {business_value}
- Objectives: {objectives}
- Acceptance Criteria: {acceptance_criteria}
- BRD Sections: {brd_sections}
- Technical Notes: {technical_notes}

## Related BRD Context:
{brd_context}

## Analysis Focus:
{analysis_focus_instructions}

## Analysis Preferences:
- Granularity Preference: {granularity_preference}
- Include Technical Tasks: {include_technical_tasks}
- Include Spikes: {include_spikes}

{user_feedback_section}

{previous_items_section}

## Required Output (JSON):
```json
{{
    "features_identified": ["Feature 1", "Feature 2", ...],
    "user_interactions": ["Interaction 1", "Interaction 2", ...],
    "technical_components": ["Component 1", "Component 2", ...],
    "complexity_level": "low|medium|high",
    "recommended_item_count": 6,
    "min_item_count": 4,
    "max_item_count": 8,
    "suggested_user_stories": 4,
    "suggested_tasks": 2,
    "suggested_spikes": 0,
    "estimated_total_points": 21,
    "reasoning": "Explanation for the breakdown...",
    "suggested_items": [
        {{
            "id": "item-1",
            "title": "Item Title",
            "item_type": "user_story|task|spike",
            "scope": "What this item covers",
            "complexity": "low|medium|high",
            "estimated_points": 3
        }}
    ]
}}
```

IMPORTANT:
- Generate unique IDs for each suggested item (e.g., "item-1", "item-2")
- Each item should have a clear, descriptive TITLE
- Provide practical, implementable item suggestions.
"""


# =============================================================================
# BRD Analyzer
# =============================================================================

class BRDAnalyzer:
    """Analyzes BRD documents to determine optimal EPIC count and structure."""

    def __init__(self, copilot_session):
        """Initialize with copilot session for LLM calls."""
        self.copilot_session = copilot_session

    async def analyze_brd(self, request: AnalyzeBRDRequest) -> BRDAnalysisResult:
        """Analyze BRD and return EPIC count recommendations.

        This is Phase 1: Pre-analysis before generation.
        """
        logger.info(f"Analyzing BRD {request.brd_id} for EPIC decomposition")

        # First, do structural analysis (fast, no LLM)
        structural_analysis = self._analyze_structure(request.brd_markdown)

        # Then, do LLM-based semantic analysis
        try:
            llm_analysis = await self._llm_analyze_brd(request)
        except Exception as e:
            logger.warning(f"LLM analysis failed, using structural fallback: {e}")
            llm_analysis = None

        # Merge results
        result = self._merge_analysis_results(
            request=request,
            structural=structural_analysis,
            llm=llm_analysis,
        )

        logger.info(
            f"BRD analysis complete: recommended {result.recommended_epic_count} EPICs "
            f"(range: {result.min_epic_count}-{result.max_epic_count})"
        )

        return result

    def _analyze_structure(self, brd_markdown: str) -> dict:
        """Perform fast structural analysis without LLM."""
        lines = brd_markdown.split('\n')

        # Count sections (H2 headers)
        h2_count = len([l for l in lines if l.startswith('## ')])
        h3_count = len([l for l in lines if l.startswith('### ')])

        # Word count
        word_count = len(brd_markdown.split())

        # Count potential requirements (bullet points with keywords)
        requirement_patterns = [
            r'(?:shall|must|should|will|can)\s+',
            r'(?:user|system|application)\s+(?:shall|must|should|will|can)',
            r'^\s*[-*]\s+',  # Bullet points
        ]
        requirement_count = 0
        for pattern in requirement_patterns:
            requirement_count += len(re.findall(pattern, brd_markdown, re.IGNORECASE | re.MULTILINE))
        requirement_count = min(requirement_count // 2, 100)  # Dedupe and cap

        # Detect personas
        persona_patterns = [
            r'(?:as a|role of|user type|persona)[:\s]+([^,\n.]+)',
            r'(?:admin|administrator|manager|customer|user|operator|viewer)',
        ]
        personas = set()
        for pattern in persona_patterns:
            matches = re.findall(pattern, brd_markdown, re.IGNORECASE)
            personas.update([m.strip().lower() for m in matches if m.strip()])

        # Detect integrations
        integration_patterns = [
            r'(?:integrate|integration|API|connect|interface)\s+(?:with)?\s*([^,\n.]+)',
            r'(?:third[- ]party|external)\s+(?:system|service|API)',
        ]
        integrations = set()
        for pattern in integration_patterns:
            matches = re.findall(pattern, brd_markdown, re.IGNORECASE)
            integrations.update([m.strip() for m in matches if m.strip() and len(m.strip()) < 50])

        return {
            'section_count': h2_count,
            'subsection_count': h3_count,
            'word_count': word_count,
            'requirement_count': requirement_count,
            'persona_count': len(personas),
            'personas': list(personas)[:10],
            'integration_count': len(integrations),
            'integrations': list(integrations)[:10],
        }

    async def _llm_analyze_brd(self, request: AnalyzeBRDRequest) -> Optional[dict]:
        """Use LLM for semantic BRD analysis."""

        # Get focus-specific instructions
        analysis_focus = request.analysis_focus or "functional_areas"
        focus_instructions = ANALYSIS_FOCUS_PROMPTS.get(
            analysis_focus,
            ANALYSIS_FOCUS_PROMPTS["functional_areas"]
        )

        # Build user feedback section
        user_feedback_section = ""
        if request.user_feedback:
            user_feedback_section = f"""
## User Feedback (IMPORTANT - Consider this in your analysis):
{request.user_feedback}

Please adjust your EPIC suggestions based on this feedback.
"""

        # Build previous EPICs section for re-analysis
        previous_epics_section = ""
        if request.previous_epics:
            previous_list = "\n".join([
                f"- {epic.name}: {epic.scope}"
                for epic in request.previous_epics
            ])
            previous_epics_section = f"""
## Previous EPIC Suggestions (Refine these based on feedback):
{previous_list}

The user wants to modify these suggestions. Keep what works, adjust what doesn't.
"""

        prompt = BRD_ANALYSIS_USER_PROMPT.format(
            brd_content=request.brd_markdown[:15000],  # Limit context
            analysis_focus_instructions=focus_instructions,
            epic_size_preference=request.epic_size_preference,
            team_velocity=request.team_velocity or "Not specified",
            target_sprint_count=request.target_sprint_count or "Not specified",
            user_feedback_section=user_feedback_section,
            previous_epics_section=previous_epics_section,
        )

        try:
            if self.copilot_session is None:
                logger.warning("No copilot session available for LLM analysis")
                return None

            # Combine system and user prompt
            full_prompt = f"{BRD_ANALYSIS_SYSTEM_PROMPT}\n\n{prompt}"
            message_options = {"prompt": full_prompt}

            if hasattr(self.copilot_session, 'send_and_wait'):
                event = await asyncio.wait_for(
                    self.copilot_session.send_and_wait(message_options, timeout=120),
                    timeout=120
                )
                response = self._extract_response_text(event)
            else:
                logger.warning("Copilot session does not support send_and_wait")
                return None

            if not response:
                logger.warning("Empty response from LLM")
                return None

            # Extract JSON from response
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))

            # Try parsing the whole response as JSON
            return json.loads(response)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            return None
        except asyncio.TimeoutError:
            logger.warning("LLM analysis timed out")
            return None
        except Exception as e:
            logger.error(f"LLM analysis error: {e}")
            return None

    def _extract_response_text(self, event: Any) -> Optional[str]:
        """Extract text content from a Copilot event."""
        try:
            if event is None:
                return None
            if hasattr(event, 'data'):
                data = event.data
                if hasattr(data, 'message') and hasattr(data.message, 'content'):
                    return data.message.content
                if hasattr(data, 'content'):
                    return data.content
                if hasattr(data, 'text'):
                    return data.text
            if hasattr(event, 'content'):
                return event.content
            if hasattr(event, 'text'):
                return event.text
            if isinstance(event, str):
                return event
            if isinstance(event, dict):
                return event.get('content') or event.get('text') or event.get('message', {}).get('content')
            return str(event)
        except Exception as e:
            logger.warning(f"Failed to extract response text: {e}")
            return None

    def _merge_analysis_results(
        self,
        request: AnalyzeBRDRequest,
        structural: dict,
        llm: Optional[dict],
    ) -> BRDAnalysisResult:
        """Merge structural and LLM analysis results."""

        # If LLM analysis succeeded, use it as primary source
        if llm:
            # Ensure each EPIC has an ID
            suggested_epics = []
            for i, epic_data in enumerate(llm.get('suggested_epics', [])):
                if 'id' not in epic_data or not epic_data['id']:
                    epic_data['id'] = f"epic-{i + 1}"
                suggested_epics.append(SuggestedEpicBreakdown(**epic_data))

            return BRDAnalysisResult(
                success=True,
                brd_id=request.brd_id,
                functional_areas=llm.get('functional_areas', []),
                user_journeys=llm.get('user_journeys', []),
                user_personas=llm.get('user_personas', structural.get('personas', [])),
                integration_points=llm.get('integration_points', structural.get('integrations', [])),
                complexity_level=llm.get('complexity_level', 'medium'),
                complexity_factors=llm.get('complexity_factors', []),
                word_count=structural['word_count'],
                section_count=structural['section_count'],
                requirement_count=llm.get('requirement_count', structural['requirement_count']),
                recommended_epic_count=llm.get('recommended_epic_count', 5),
                min_epic_count=llm.get('min_epic_count', 3),
                max_epic_count=llm.get('max_epic_count', 8),
                suggested_epics=suggested_epics,
                recommendation_reasoning=llm.get('recommendation_reasoning', ''),
                warnings=llm.get('warnings', []),
            )

        # Fallback to heuristic-based analysis
        return self._heuristic_analysis(request, structural)

    def _heuristic_analysis(
        self,
        request: AnalyzeBRDRequest,
        structural: dict,
    ) -> BRDAnalysisResult:
        """Fallback heuristic analysis when LLM fails."""

        # Calculate base EPIC count from sections
        section_count = structural['section_count']
        base_count = max(1, section_count - 2)  # Exclude intro/conclusion

        # Adjust for word count (complexity proxy)
        word_count = structural['word_count']
        if word_count > 10000:
            base_count = int(base_count * 1.3)
        elif word_count > 5000:
            base_count = int(base_count * 1.15)
        elif word_count < 2000:
            base_count = max(1, int(base_count * 0.8))

        # Adjust for integrations
        integration_count = structural['integration_count']
        if integration_count > 5:
            base_count += 2
        elif integration_count > 2:
            base_count += 1

        # Adjust for size preference
        if request.epic_size_preference == 'small':
            base_count = int(base_count * 1.3)
        elif request.epic_size_preference == 'large':
            base_count = max(1, int(base_count * 0.7))

        # Calculate range
        min_count = max(1, int(base_count * 0.7))
        max_count = max(min_count + 2, int(base_count * 1.4))
        recommended = max(min_count, min(base_count, max_count))

        # Determine complexity
        complexity = 'medium'
        complexity_factors = []
        if word_count > 8000:
            complexity = 'high'
            complexity_factors.append('Large document size')
        if integration_count > 3:
            complexity = 'high'
            complexity_factors.append(f'{integration_count} integrations identified')
        if structural['requirement_count'] > 50:
            complexity_factors.append('High requirement count')

        return BRDAnalysisResult(
            success=True,
            brd_id=request.brd_id,
            functional_areas=[],  # Can't determine without LLM
            user_journeys=[],
            user_personas=structural.get('personas', []),
            integration_points=structural.get('integrations', []),
            complexity_level=complexity,
            complexity_factors=complexity_factors,
            word_count=word_count,
            section_count=section_count,
            requirement_count=structural['requirement_count'],
            recommended_epic_count=recommended,
            min_epic_count=min_count,
            max_epic_count=max_count,
            suggested_epics=[],
            recommendation_reasoning=(
                f"Based on structural analysis: {section_count} major sections, "
                f"{word_count} words, {integration_count} potential integrations. "
                f"Size preference: {request.epic_size_preference}."
            ),
            warnings=["LLM analysis unavailable - using heuristic analysis"],
        )


# =============================================================================
# EPIC Analyzer (for Backlog decomposition)
# =============================================================================

class EpicAnalyzer:
    """Analyzes EPICs to determine optimal backlog item decomposition."""

    def __init__(self, copilot_session):
        """Initialize with copilot session for LLM calls."""
        self.copilot_session = copilot_session

    async def analyze_epics(
        self,
        request: AnalyzeEpicsForBacklogsRequest,
    ) -> AnalyzeEpicsForBacklogsResponse:
        """Analyze all EPICs and return backlog count recommendations.

        This is Phase 1: Pre-analysis before backlog generation.
        """
        logger.info(f"Analyzing {len(request.epics)} EPICs for backlog decomposition")

        epic_analyses = []
        total_items = 0
        total_points = 0
        total_stories = 0
        total_tasks = 0
        total_spikes = 0

        # Get previous items per EPIC (for re-analysis)
        previous_items = request.previous_items or {}

        for epic in request.epics:
            # Get previous items for this EPIC if available
            epic_previous_items = previous_items.get(epic.id, [])

            analysis = await self._analyze_single_epic(
                epic=epic,
                brd_markdown=request.brd_markdown,
                granularity=request.granularity_preference,
                include_tasks=request.include_technical_tasks,
                include_spikes=request.include_spikes,
                analysis_focus=request.analysis_focus,
                user_feedback=request.user_feedback,
                previous_items=epic_previous_items,
            )
            epic_analyses.append(analysis)

            total_items += analysis.recommended_item_count
            total_points += analysis.estimated_total_points
            total_stories += analysis.suggested_user_stories
            total_tasks += analysis.suggested_tasks
            total_spikes += analysis.suggested_spikes

        # Build summary
        summary = (
            f"Recommended {total_items} total backlog items across {len(request.epics)} EPICs: "
            f"{total_stories} user stories, {total_tasks} tasks, {total_spikes} spikes. "
            f"Estimated total: {total_points} story points."
        )

        return AnalyzeEpicsForBacklogsResponse(
            success=True,
            brd_id=request.brd_id,
            epic_analyses=epic_analyses,
            total_recommended_items=total_items,
            total_estimated_points=total_points,
            total_user_stories=total_stories,
            total_tasks=total_tasks,
            total_spikes=total_spikes,
            recommendation_summary=summary,
        )

    async def _analyze_single_epic(
        self,
        epic: Epic,
        brd_markdown: str,
        granularity: str,
        include_tasks: bool,
        include_spikes: bool,
        analysis_focus: str = "user_stories",
        user_feedback: Optional[str] = None,
        previous_items: Optional[list[SuggestedBacklogBreakdown]] = None,
    ) -> EpicAnalysisResult:
        """Analyze a single EPIC for backlog decomposition."""

        # Try LLM analysis first
        try:
            llm_result = await self._llm_analyze_epic(
                epic=epic,
                brd_markdown=brd_markdown,
                granularity=granularity,
                include_tasks=include_tasks,
                include_spikes=include_spikes,
                analysis_focus=analysis_focus,
                user_feedback=user_feedback,
                previous_items=previous_items,
            )
            if llm_result:
                return self._parse_llm_epic_result(epic, llm_result)
        except Exception as e:
            logger.warning(f"LLM analysis failed for EPIC {epic.id}: {e}")

        # Fallback to heuristic
        return self._heuristic_epic_analysis(epic, granularity, include_tasks, include_spikes)

    async def _llm_analyze_epic(
        self,
        epic: Epic,
        brd_markdown: str,
        granularity: str,
        include_tasks: bool,
        include_spikes: bool,
        analysis_focus: str = "user_stories",
        user_feedback: Optional[str] = None,
        previous_items: Optional[list[SuggestedBacklogBreakdown]] = None,
    ) -> Optional[dict]:
        """Use LLM to analyze EPIC for backlog decomposition."""

        # Extract relevant BRD context
        brd_context = self._extract_brd_context(brd_markdown, epic.brd_section_refs)

        # Get focus-specific instructions
        focus_instructions = BACKLOG_FOCUS_PROMPTS.get(
            analysis_focus,
            BACKLOG_FOCUS_PROMPTS["user_stories"]
        )

        # Build user feedback section
        user_feedback_section = ""
        if user_feedback:
            user_feedback_section = f"""
## User Feedback (IMPORTANT - Consider this in your analysis):
{user_feedback}

Please adjust your item suggestions based on this feedback.
"""

        # Build previous items section for re-analysis
        previous_items_section = ""
        if previous_items:
            previous_list = "\n".join([
                f"- [{item.item_type}] {item.title}: {item.scope}"
                for item in previous_items
            ])
            previous_items_section = f"""
## Previous Item Suggestions (Refine these based on feedback):
{previous_list}

The user wants to modify these suggestions. Keep what works, adjust what doesn't.
"""

        prompt = EPIC_ANALYSIS_USER_PROMPT.format(
            epic_id=epic.id,
            epic_title=epic.title,
            epic_description=epic.description,
            business_value=epic.business_value,
            objectives='\n'.join(f"- {obj}" for obj in epic.objectives),
            acceptance_criteria='\n'.join(f"- {ac}" for ac in epic.acceptance_criteria),
            brd_sections=', '.join(epic.brd_section_refs),
            technical_notes=epic.technical_notes or "None",
            brd_context=brd_context[:5000],  # Limit context
            analysis_focus_instructions=focus_instructions,
            granularity_preference=granularity,
            include_technical_tasks=include_tasks,
            include_spikes=include_spikes,
            user_feedback_section=user_feedback_section,
            previous_items_section=previous_items_section,
        )

        try:
            if self.copilot_session is None:
                logger.warning("No copilot session available for EPIC analysis")
                return None

            # Combine system and user prompt
            full_prompt = f"{EPIC_ANALYSIS_SYSTEM_PROMPT}\n\n{prompt}"
            message_options = {"prompt": full_prompt}

            if hasattr(self.copilot_session, 'send_and_wait'):
                event = await asyncio.wait_for(
                    self.copilot_session.send_and_wait(message_options, timeout=120),
                    timeout=120
                )
                response = self._extract_response_text(event)
            else:
                logger.warning("Copilot session does not support send_and_wait")
                return None

            if not response:
                logger.warning("Empty response from LLM for EPIC analysis")
                return None

            # Extract JSON
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            return json.loads(response)

        except asyncio.TimeoutError:
            logger.warning("EPIC analysis timed out")
            return None
        except Exception as e:
            logger.warning(f"Failed to parse EPIC analysis: {e}")
            return None

    def _extract_response_text(self, event: Any) -> Optional[str]:
        """Extract text content from a Copilot event."""
        try:
            if event is None:
                return None
            if hasattr(event, 'data'):
                data = event.data
                if hasattr(data, 'message') and hasattr(data.message, 'content'):
                    return data.message.content
                if hasattr(data, 'content'):
                    return data.content
                if hasattr(data, 'text'):
                    return data.text
            if hasattr(event, 'content'):
                return event.content
            if hasattr(event, 'text'):
                return event.text
            if isinstance(event, str):
                return event
            if isinstance(event, dict):
                return event.get('content') or event.get('text') or event.get('message', {}).get('content')
            return str(event)
        except Exception as e:
            logger.warning(f"Failed to extract response text: {e}")
            return None

    def _extract_brd_context(self, brd_markdown: str, section_refs: list[str]) -> str:
        """Extract relevant BRD sections for context."""
        if not section_refs:
            return brd_markdown[:3000]

        # Try to find and extract referenced sections
        lines = brd_markdown.split('\n')
        relevant_content = []
        capture = False
        current_section = ""

        for line in lines:
            # Check if this is a header
            if line.startswith('#'):
                # Check if any section ref matches
                capture = any(ref in line for ref in section_refs)
                if capture:
                    current_section = line
                    relevant_content.append(line)
            elif capture:
                relevant_content.append(line)

        if relevant_content:
            return '\n'.join(relevant_content)
        return brd_markdown[:3000]

    def _parse_llm_epic_result(self, epic: Epic, llm_result: dict) -> EpicAnalysisResult:
        """Parse LLM result into EpicAnalysisResult."""
        # Ensure each item has an ID
        suggested_items = []
        for i, item_data in enumerate(llm_result.get('suggested_items', [])):
            if 'id' not in item_data or not item_data['id']:
                item_data['id'] = f"{epic.id}-item-{i + 1}"
            suggested_items.append(SuggestedBacklogBreakdown(**item_data))

        return EpicAnalysisResult(
            epic_id=epic.id,
            epic_title=epic.title,
            features_identified=llm_result.get('features_identified', []),
            user_interactions=llm_result.get('user_interactions', []),
            technical_components=llm_result.get('technical_components', []),
            complexity_level=llm_result.get('complexity_level', 'medium'),
            recommended_item_count=llm_result.get('recommended_item_count', 5),
            min_item_count=llm_result.get('min_item_count', 3),
            max_item_count=llm_result.get('max_item_count', 8),
            suggested_user_stories=llm_result.get('suggested_user_stories', 4),
            suggested_tasks=llm_result.get('suggested_tasks', 1),
            suggested_spikes=llm_result.get('suggested_spikes', 0),
            suggested_items=suggested_items,
            estimated_total_points=llm_result.get('estimated_total_points', 21),
            reasoning=llm_result.get('reasoning', ''),
        )

    def _heuristic_epic_analysis(
        self,
        epic: Epic,
        granularity: str,
        include_tasks: bool,
        include_spikes: bool,
    ) -> EpicAnalysisResult:
        """Fallback heuristic analysis for EPIC decomposition."""

        # Base count from acceptance criteria
        ac_count = len(epic.acceptance_criteria)
        base_count = max(3, ac_count)

        # Adjust for objectives
        obj_count = len(epic.objectives)
        if obj_count > 3:
            base_count += obj_count - 3

        # Adjust for granularity
        if granularity == 'fine':
            base_count = int(base_count * 1.4)
        elif granularity == 'coarse':
            base_count = max(2, int(base_count * 0.7))

        # Calculate type breakdown
        stories = int(base_count * 0.65)
        tasks = int(base_count * 0.25) if include_tasks else 0
        spikes = 1 if include_spikes and len(epic.affected_components) > 3 else 0

        total = stories + tasks + spikes

        # Estimate points (average 3 points per item)
        estimated_points = stories * 3 + tasks * 2 + spikes * 5

        return EpicAnalysisResult(
            epic_id=epic.id,
            epic_title=epic.title,
            features_identified=[],
            user_interactions=[],
            technical_components=epic.affected_components,
            complexity_level='medium',
            recommended_item_count=total,
            min_item_count=max(2, int(total * 0.7)),
            max_item_count=int(total * 1.4),
            suggested_user_stories=stories,
            suggested_tasks=tasks,
            suggested_spikes=spikes,
            suggested_items=[],
            estimated_total_points=estimated_points,
            reasoning=(
                f"Based on {ac_count} acceptance criteria and {obj_count} objectives. "
                f"Granularity preference: {granularity}."
            ),
        )
