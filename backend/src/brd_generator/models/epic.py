"""EPIC and Backlog Data Models with BRD Traceability.

This module defines the data models for:
- EPIC generation from BRD documents
- Backlog item generation from EPICs
- Feedback-driven refinement
- Traceability between BRD sections, EPICs, and Backlogs
- Template configuration for EPIC and Backlog generation
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class EpicStatus(str, Enum):
    """Status of an EPIC in the workflow."""
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    EXPORTED = "exported"


class BacklogItemType(str, Enum):
    """Type of backlog item."""
    USER_STORY = "user_story"
    TASK = "task"
    SPIKE = "spike"
    BUG = "bug"


class Priority(str, Enum):
    """Priority levels for EPICs and Backlogs."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EffortSize(str, Enum):
    """T-shirt sizing for effort estimation."""
    XSMALL = "xs"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    XLARGE = "xlarge"


# =============================================================================
# Template Configuration Models
# =============================================================================

class EpicFieldConfig(BaseModel):
    """Configuration for a single EPIC field."""
    field_name: str = Field(
        ...,
        description="Field name (e.g., 'description', 'business_value', 'objectives')"
    )
    enabled: bool = Field(
        True,
        description="Whether this field should be included in generation"
    )
    target_words: int = Field(
        100,
        ge=20,
        le=500,
        description="Target word count for this field"
    )
    guidelines: Optional[str] = Field(
        None,
        description="Custom guidelines for generating this field"
    )


class EpicTemplateConfig(BaseModel):
    """Template configuration for EPIC generation."""

    # Custom template content (markdown)
    epic_template: Optional[str] = Field(
        None,
        description="Custom EPIC template content (Markdown format)"
    )

    # Field configurations
    field_configs: Optional[list[EpicFieldConfig]] = Field(
        None,
        description="Per-field configuration for EPICs"
    )

    # Global defaults
    default_description_words: int = Field(
        150,
        ge=50,
        le=500,
        description="Default word count for EPIC descriptions"
    )
    default_business_value_words: int = Field(
        100,
        ge=30,
        le=300,
        description="Default word count for business value"
    )
    default_objectives_count: int = Field(
        3,
        ge=1,
        le=10,
        description="Default number of objectives per EPIC"
    )
    default_acceptance_criteria_count: int = Field(
        5,
        ge=2,
        le=15,
        description="Default number of acceptance criteria per EPIC"
    )

    # Include/exclude options
    include_technical_components: bool = Field(
        True,
        description="Include technical components in EPICs"
    )
    include_dependencies: bool = Field(
        True,
        description="Include dependency analysis between EPICs"
    )
    include_effort_estimates: bool = Field(
        True,
        description="Include effort estimates for EPICs"
    )


class BacklogFieldConfig(BaseModel):
    """Configuration for a single backlog field."""
    field_name: str = Field(
        ...,
        description="Field name (e.g., 'description', 'acceptance_criteria', 'technical_notes')"
    )
    enabled: bool = Field(
        True,
        description="Whether this field should be included in generation"
    )
    target_words: int = Field(
        50,
        ge=10,
        le=300,
        description="Target word count for this field"
    )
    guidelines: Optional[str] = Field(
        None,
        description="Custom guidelines for generating this field"
    )


class BacklogTemplateConfig(BaseModel):
    """Template configuration for Backlog generation."""

    # Custom template content (markdown)
    backlog_template: Optional[str] = Field(
        None,
        description="Custom Backlog item template content (Markdown format)"
    )

    # Field configurations
    field_configs: Optional[list[BacklogFieldConfig]] = Field(
        None,
        description="Per-field configuration for backlog items"
    )

    # Global defaults
    default_description_words: int = Field(
        80,
        ge=20,
        le=300,
        description="Default word count for item descriptions"
    )
    default_acceptance_criteria_count: int = Field(
        4,
        ge=1,
        le=10,
        description="Default number of acceptance criteria per item"
    )
    default_technical_notes_words: int = Field(
        50,
        ge=0,
        le=200,
        description="Default word count for technical notes"
    )

    # User story format control
    require_user_story_format: bool = Field(
        True,
        description="Require 'As a... I want... So that...' format for user stories"
    )

    # Include/exclude options
    include_technical_notes: bool = Field(
        True,
        description="Include technical notes in backlog items"
    )
    include_file_references: bool = Field(
        True,
        description="Include file references (files to modify/create)"
    )
    include_story_points: bool = Field(
        True,
        description="Include story point estimates"
    )


# =============================================================================
# Pre-Analysis Models (Phase 1: Intelligent Count Determination)
# =============================================================================

class SuggestedEpicBreakdown(BaseModel):
    """Suggested EPIC breakdown from BRD analysis."""

    id: str = Field(
        default="",
        description="Unique ID for this suggested EPIC (for editing/removal)"
    )
    name: str = Field(
        ...,
        description="Suggested EPIC name"
    )
    scope: str = Field(
        ...,
        description="What BRD sections/features this EPIC covers"
    )
    brd_sections: list[str] = Field(
        default_factory=list,
        description="BRD section references (e.g., ['2.1', '2.2', '3.1'])"
    )
    estimated_stories: int = Field(
        5,
        ge=1,
        le=20,
        description="Estimated number of user stories"
    )
    complexity: str = Field(
        "medium",
        description="Complexity level: low, medium, high"
    )
    reasoning: str = Field(
        "",
        description="Why this should be a separate EPIC"
    )
    user_modified: bool = Field(
        False,
        description="Whether user has modified this suggestion"
    )


class BRDAnalysisResult(BaseModel):
    """Result of BRD pre-analysis for intelligent EPIC count determination."""

    success: bool = True
    brd_id: str

    # Structural analysis
    functional_areas: list[str] = Field(
        default_factory=list,
        description="Distinct functional areas identified"
    )
    user_journeys: list[str] = Field(
        default_factory=list,
        description="User journeys/workflows identified"
    )
    user_personas: list[str] = Field(
        default_factory=list,
        description="User roles/personas mentioned"
    )
    integration_points: list[str] = Field(
        default_factory=list,
        description="External integrations identified"
    )

    # Complexity assessment
    complexity_level: str = Field(
        "medium",
        description="Overall complexity: low, medium, high, very_high"
    )
    complexity_factors: list[str] = Field(
        default_factory=list,
        description="Factors contributing to complexity"
    )

    # Size metrics
    word_count: int = Field(0, description="BRD word count")
    section_count: int = Field(0, description="Number of major sections")
    requirement_count: int = Field(0, description="Estimated requirement count")

    # EPIC count recommendation
    recommended_epic_count: int = Field(
        5,
        ge=1,
        le=25,
        description="Optimal EPIC count"
    )
    min_epic_count: int = Field(
        3,
        ge=1,
        le=20,
        description="Minimum recommended EPICs"
    )
    max_epic_count: int = Field(
        8,
        ge=2,
        le=30,
        description="Maximum recommended EPICs"
    )

    # Detailed breakdown
    suggested_epics: list[SuggestedEpicBreakdown] = Field(
        default_factory=list,
        description="Suggested EPIC breakdown with scope"
    )

    # Reasoning
    recommendation_reasoning: str = Field(
        "",
        description="Explanation for the recommendation"
    )

    # Warnings/notes
    warnings: list[str] = Field(
        default_factory=list,
        description="Any warnings or considerations"
    )


class AnalysisFocus(str, Enum):
    """Focus areas for BRD/EPIC analysis."""
    FUNCTIONAL_AREAS = "functional_areas"
    USER_JOURNEYS = "user_journeys"
    TECHNICAL_COMPONENTS = "technical_components"
    BUSINESS_CAPABILITIES = "business_capabilities"
    INTEGRATIONS = "integrations"
    USER_PERSONAS = "user_personas"


class AnalyzeBRDRequest(BaseModel):
    """Request to analyze BRD for EPIC count determination."""

    brd_id: str = Field(
        ...,
        description="BRD document ID"
    )
    brd_markdown: str = Field(
        ...,
        min_length=100,
        description="Full BRD content in markdown"
    )
    brd_title: Optional[str] = Field(
        None,
        description="BRD title"
    )

    # Analysis focus - what perspective to analyze from
    analysis_focus: str = Field(
        "functional_areas",
        description="Focus for analysis: 'functional_areas', 'user_journeys', 'technical_components', 'business_capabilities', 'integrations', 'user_personas'"
    )

    # User feedback for re-analysis
    user_feedback: Optional[str] = Field(
        None,
        description="User feedback to guide the analysis (e.g., 'Focus more on mobile features', 'Split authentication into separate EPICs')"
    )

    # Previous analysis to refine (for re-analysis)
    previous_epics: Optional[list[SuggestedEpicBreakdown]] = Field(
        None,
        description="Previous suggested EPICs to refine based on feedback"
    )

    # Analysis preferences
    epic_size_preference: str = Field(
        "medium",
        description="'small' (granular), 'medium' (balanced), 'large' (fewer, bigger)"
    )
    team_velocity: Optional[int] = Field(
        None,
        ge=10,
        le=100,
        description="Team velocity in story points per sprint (helps size EPICs)"
    )
    target_sprint_count: Optional[int] = Field(
        None,
        ge=1,
        le=12,
        description="Target sprints for delivery (helps determine EPIC count)"
    )


class SuggestedBacklogBreakdown(BaseModel):
    """Suggested backlog item from EPIC analysis."""

    id: str = Field(
        default="",
        description="Unique ID for this suggested item (for editing/removal)"
    )
    title: str = Field(
        ...,
        description="Suggested item title"
    )
    item_type: str = Field(
        "user_story",
        description="Type: user_story, task, spike"
    )
    scope: str = Field(
        "",
        description="What this item covers"
    )
    complexity: str = Field(
        "medium",
        description="Complexity: low, medium, high"
    )
    estimated_points: int = Field(
        3,
        ge=1,
        le=13,
        description="Estimated story points"
    )
    user_modified: bool = Field(
        False,
        description="Whether user has modified this suggestion"
    )


class EpicAnalysisResult(BaseModel):
    """Result of EPIC analysis for intelligent backlog count determination."""

    epic_id: str
    epic_title: str

    # Scope analysis
    features_identified: list[str] = Field(
        default_factory=list,
        description="Distinct features within this EPIC"
    )
    user_interactions: list[str] = Field(
        default_factory=list,
        description="User interactions/actions identified"
    )
    technical_components: list[str] = Field(
        default_factory=list,
        description="Technical components involved"
    )

    # Complexity
    complexity_level: str = Field(
        "medium",
        description="EPIC complexity: low, medium, high"
    )

    # Backlog recommendation
    recommended_item_count: int = Field(
        5,
        ge=1,
        le=20,
        description="Optimal backlog item count"
    )
    min_item_count: int = Field(
        3,
        ge=1,
        le=15,
        description="Minimum items"
    )
    max_item_count: int = Field(
        8,
        ge=2,
        le=25,
        description="Maximum items"
    )

    # Item type breakdown
    suggested_user_stories: int = Field(0)
    suggested_tasks: int = Field(0)
    suggested_spikes: int = Field(0)

    # Detailed breakdown
    suggested_items: list[SuggestedBacklogBreakdown] = Field(
        default_factory=list,
        description="Suggested backlog items"
    )

    # Total points estimate
    estimated_total_points: int = Field(
        0,
        description="Total estimated story points"
    )

    reasoning: str = Field(
        "",
        description="Reasoning for the breakdown"
    )


class BacklogAnalysisFocus(str, Enum):
    """Focus areas for Backlog analysis."""
    USER_STORIES = "user_stories"
    TECHNICAL_TASKS = "technical_tasks"
    TESTING = "testing"
    INTEGRATION = "integration"
    UI_UX = "ui_ux"
    DATA_MIGRATION = "data_migration"


class AnalyzeEpicsForBacklogsRequest(BaseModel):
    """Request to analyze EPICs for backlog count determination."""

    brd_id: str = Field(
        ...,
        description="Source BRD ID"
    )
    brd_markdown: str = Field(
        ...,
        description="BRD content for context"
    )
    epics: list["Epic"] = Field(
        ...,
        description="EPICs to analyze"
    )

    # Analysis focus - what perspective to analyze from
    analysis_focus: str = Field(
        "user_stories",
        description="Focus for analysis: 'user_stories', 'technical_tasks', 'testing', 'integration', 'ui_ux', 'data_migration'"
    )

    # User feedback for re-analysis
    user_feedback: Optional[str] = Field(
        None,
        description="User feedback to guide the analysis (e.g., 'Add more testing tasks', 'Focus on API integration')"
    )

    # Previous analysis to refine (for re-analysis)
    previous_items: Optional[dict[str, list[SuggestedBacklogBreakdown]]] = Field(
        None,
        description="Previous suggested items per EPIC to refine based on feedback"
    )

    # Analysis preferences
    granularity_preference: str = Field(
        "medium",
        description="'fine' (more items), 'medium', 'coarse' (fewer items)"
    )
    include_technical_tasks: bool = Field(
        True,
        description="Include technical implementation tasks"
    )
    include_spikes: bool = Field(
        True,
        description="Include research/spike items for unknowns"
    )


class AnalyzeEpicsForBacklogsResponse(BaseModel):
    """Response containing analysis for all EPICs."""

    success: bool = True
    brd_id: str

    # Per-EPIC analysis
    epic_analyses: list[EpicAnalysisResult] = Field(
        default_factory=list,
        description="Analysis for each EPIC"
    )

    # Totals
    total_recommended_items: int = Field(0)
    total_estimated_points: int = Field(0)

    # Summary by type
    total_user_stories: int = Field(0)
    total_tasks: int = Field(0)
    total_spikes: int = Field(0)

    # Overall recommendation
    recommendation_summary: str = Field(
        "",
        description="Summary of recommendations"
    )


# =============================================================================
# Project Context Model
# =============================================================================

class ProjectContext(BaseModel):
    """Persistent project context applied to all generations.

    This captures domain knowledge, team conventions, and preferences
    that should be consistently applied across EPIC and Backlog generation.
    """

    tech_stack: list[str] = Field(
        default_factory=list,
        description="Technologies used (e.g., ['React', 'Node.js', 'PostgreSQL'])"
    )

    terminology: dict[str, str] = Field(
        default_factory=dict,
        description="Terminology preferences (e.g., {'user': 'member', 'cart': 'basket'})"
    )

    conventions: list[str] = Field(
        default_factory=list,
        description="Team conventions (e.g., 'All stories need mobile acceptance criteria')"
    )

    estimation_method: str = Field(
        "story_points",
        description="Estimation method: 'story_points', 't_shirt', 'hours'"
    )

    sprint_length_days: int = Field(
        14,
        ge=7,
        le=28,
        description="Sprint length in days"
    )

    default_priority: Priority = Field(
        Priority.MEDIUM,
        description="Default priority for new items"
    )


# =============================================================================
# EPIC Models
# =============================================================================

class Epic(BaseModel):
    """An EPIC with full traceability to BRD sections.

    EPICs represent large bodies of work that can be broken down into
    smaller backlog items. Each EPIC maintains references to the BRD
    sections it addresses for traceability.
    """

    id: str = Field(
        ...,
        description="Unique EPIC identifier (e.g., 'EPIC-001')"
    )
    title: str = Field(
        ...,
        min_length=5,
        max_length=200,
        description="Concise EPIC title"
    )
    description: str = Field(
        ...,
        min_length=20,
        description="Detailed description of the EPIC"
    )

    # Traceability to BRD
    brd_id: str = Field(
        ...,
        description="Reference to source BRD document"
    )
    brd_section_refs: list[str] = Field(
        default_factory=list,
        description="BRD sections this EPIC covers (e.g., ['2.1', '2.3', '4.1'])"
    )

    # Business context
    business_value: str = Field(
        ...,
        description="Business value and rationale for this EPIC"
    )
    objectives: list[str] = Field(
        default_factory=list,
        description="Key objectives this EPIC aims to achieve"
    )

    # Acceptance criteria
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="High-level acceptance criteria for the EPIC"
    )

    # Metadata
    status: EpicStatus = Field(
        EpicStatus.DRAFT,
        description="Current status in the workflow"
    )
    estimated_story_count: Optional[int] = Field(
        None,
        ge=1,
        le=50,
        description="Estimated number of user stories"
    )

    # Dependencies
    depends_on: list[str] = Field(
        default_factory=list,
        description="EPIC IDs this EPIC depends on"
    )
    blocks: list[str] = Field(
        default_factory=list,
        description="EPIC IDs blocked by this EPIC"
    )

    # Technical hints (from codebase analysis)
    affected_components: list[str] = Field(
        default_factory=list,
        description="Components/modules affected by this EPIC"
    )
    technical_notes: Optional[str] = Field(
        None,
        description="Technical considerations and notes"
    )

    # Refinement tracking
    refinement_count: int = Field(
        0,
        ge=0,
        description="Number of times this EPIC has been refined"
    )
    last_feedback: Optional[str] = Field(
        None,
        description="Last user feedback applied to this EPIC"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="When the EPIC was created"
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="When the EPIC was last updated"
    )


# =============================================================================
# Backlog Item Models
# =============================================================================

class BacklogItem(BaseModel):
    """A backlog item with traceability to both EPIC and BRD.

    Backlog items are actionable work items derived from EPICs.
    They maintain direct references to BRD sections (not just through
    the parent EPIC) for complete traceability.
    """

    id: str = Field(
        ...,
        description="Unique identifier (e.g., 'US-001', 'TASK-001')"
    )
    epic_id: str = Field(
        ...,
        description="Parent EPIC ID"
    )
    title: str = Field(
        ...,
        min_length=5,
        max_length=200,
        description="Concise item title"
    )

    # Traceability (direct to BRD, not just through EPIC)
    brd_section_refs: list[str] = Field(
        default_factory=list,
        description="BRD sections this item addresses"
    )

    # Item type and details
    item_type: BacklogItemType = Field(
        BacklogItemType.USER_STORY,
        description="Type of backlog item"
    )
    description: str = Field(
        ...,
        description="Detailed description"
    )

    # User story format (for USER_STORY type)
    as_a: Optional[str] = Field(
        None,
        description="User role (As a...)"
    )
    i_want: Optional[str] = Field(
        None,
        description="Desired action (I want...)"
    )
    so_that: Optional[str] = Field(
        None,
        description="Expected benefit (So that...)"
    )

    # Acceptance criteria
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="Specific acceptance criteria"
    )

    # Technical details
    technical_notes: Optional[str] = Field(
        None,
        description="Technical implementation notes"
    )
    files_to_modify: list[str] = Field(
        default_factory=list,
        description="Existing files that need modification"
    )
    files_to_create: list[str] = Field(
        default_factory=list,
        description="New files to create"
    )

    # Estimation
    priority: Priority = Field(
        Priority.MEDIUM,
        description="Item priority"
    )
    story_points: Optional[int] = Field(
        None,
        ge=1,
        le=21,
        description="Story point estimation (Fibonacci: 1,2,3,5,8,13,21)"
    )
    effort_size: Optional[EffortSize] = Field(
        None,
        description="T-shirt size (alternative to story points)"
    )

    # Dependencies
    depends_on: list[str] = Field(
        default_factory=list,
        description="Item IDs this depends on"
    )
    blocks: list[str] = Field(
        default_factory=list,
        description="Item IDs blocked by this"
    )

    # Comprehensive story sections
    pre_conditions: list[str] = Field(
        default_factory=list,
        description="Conditions that must be true before the story can be executed"
    )
    post_conditions: list[str] = Field(
        default_factory=list,
        description="Conditions that must be true after successful completion"
    )
    testing_approach: Optional[str] = Field(
        None,
        description="How to test this story (unit tests, integration tests, manual testing)"
    )
    edge_cases: list[str] = Field(
        default_factory=list,
        description="Edge cases and error scenarios to handle"
    )
    implementation_notes: Optional[str] = Field(
        None,
        description="Technical guidance for implementation"
    )
    ui_ux_notes: Optional[str] = Field(
        None,
        description="UI/UX considerations if applicable"
    )

    # Status
    status: str = Field(
        "draft",
        description="Item status: draft, approved, in_progress, done"
    )

    # Refinement tracking
    refinement_count: int = Field(
        0,
        ge=0,
        description="Number of refinements"
    )
    last_feedback: Optional[str] = Field(
        None,
        description="Last feedback applied"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.now
    )
    updated_at: Optional[datetime] = Field(None)

    @property
    def user_story_format(self) -> str:
        """Return the user story in standard format."""
        if self.item_type != BacklogItemType.USER_STORY:
            return self.description

        parts = []
        if self.as_a:
            parts.append(f"As a {self.as_a}")
        if self.i_want:
            parts.append(f"I want {self.i_want}")
        if self.so_that:
            parts.append(f"So that {self.so_that}")

        return ", ".join(parts) if parts else self.description


# =============================================================================
# Request Models
# =============================================================================

class GenerateEpicsRequest(BaseModel):
    """Request to generate EPICs from a BRD document."""

    brd_id: str = Field(
        ...,
        description="BRD document ID"
    )
    brd_markdown: str = Field(
        ...,
        min_length=100,
        description="Full BRD content in markdown"
    )
    brd_title: Optional[str] = Field(
        None,
        description="BRD title for reference"
    )

    # Optional: Focus on specific sections
    focus_sections: Optional[list[str]] = Field(
        None,
        description="Specific BRD sections to focus on (optional)"
    )

    # Generation settings
    mode: str = Field(
        "verified",
        description="Generation mode: 'draft' (fast) or 'verified' (thorough)"
    )
    max_epics: int = Field(
        10,
        ge=1,
        le=20,
        description="Maximum number of EPICs to generate"
    )
    include_dependencies: bool = Field(
        True,
        description="Analyze and include EPIC dependencies"
    )
    include_estimates: bool = Field(
        True,
        description="Include effort estimates"
    )

    # Project context
    project_context: Optional[ProjectContext] = Field(
        None,
        description="Project context for consistent generation"
    )

    # Model selection
    model: Optional[str] = Field(
        None,
        description="LLM model to use"
    )

    # Detail level for content generation
    detail_level: Optional[str] = Field(
        "standard",
        description="Content detail level: 'concise', 'standard', or 'detailed'"
    )

    # Template configuration (NEW)
    epic_template: Optional[str] = Field(
        None,
        description="Custom EPIC template content (Markdown format)"
    )
    template_config: Optional[EpicTemplateConfig] = Field(
        None,
        description="Template and length configuration"
    )

    # Length control - Top-level shortcuts for common settings
    default_description_words: int = Field(
        150,
        ge=50,
        le=500,
        description="Default word count for EPIC descriptions"
    )
    default_business_value_words: int = Field(
        100,
        ge=30,
        le=300,
        description="Default word count for business value"
    )

    # Pre-analysis results (Phase 1) - Pass analysis to guide generation
    brd_analysis: Optional[BRDAnalysisResult] = Field(
        None,
        description="Pre-analysis results from /epics/analyze-brd endpoint"
    )

    # Dynamic EPIC count control
    epic_count_mode: str = Field(
        "auto",
        description="'auto' (AI decides based on analysis), 'guided' (use analysis recommendation), 'manual' (use max_epics)"
    )
    epic_size_preference: str = Field(
        "medium",
        description="'small' (more granular EPICs), 'medium' (balanced), 'large' (fewer, bigger EPICs)"
    )

    # Use suggested breakdown from analysis
    use_suggested_breakdown: bool = Field(
        False,
        description="Use the suggested EPIC breakdown from analysis as a guide"
    )

    # User-defined EPICs (edited/added/removed by user)
    user_defined_epics: Optional[list[SuggestedEpicBreakdown]] = Field(
        None,
        description="User-modified EPIC list (takes precedence over analysis suggestions)"
    )


class RefineEpicRequest(BaseModel):
    """Request to refine a single EPIC based on user feedback."""

    epic_id: str = Field(
        ...,
        description="ID of the EPIC to refine"
    )
    current_epic: Epic = Field(
        ...,
        description="Current state of the EPIC"
    )
    user_feedback: str = Field(
        ...,
        min_length=5,
        description="User feedback for refinement"
    )

    # Context for refinement
    brd_sections_content: list[str] = Field(
        default_factory=list,
        description="Relevant BRD section content"
    )
    project_context: Optional[ProjectContext] = Field(
        None,
        description="Project context"
    )


class RefineAllEpicsRequest(BaseModel):
    """Request to apply global feedback to all EPICs."""

    epics: list[Epic] = Field(
        ...,
        description="All current EPICs"
    )
    global_feedback: str = Field(
        ...,
        min_length=5,
        description="Feedback to apply to all EPICs"
    )
    brd_markdown: str = Field(
        ...,
        description="Full BRD content for context"
    )
    project_context: Optional[ProjectContext] = Field(
        None,
        description="Project context"
    )


class GenerateBacklogsRequest(BaseModel):
    """Request to generate backlog items from EPICs."""

    brd_id: str = Field(
        ...,
        description="Source BRD ID"
    )
    brd_markdown: str = Field(
        ...,
        description="Full BRD content for context anchoring"
    )
    epics: list[Epic] = Field(
        ...,
        description="EPICs to generate backlogs for"
    )

    # Which EPICs to generate for (None = all)
    epic_ids: Optional[list[str]] = Field(
        None,
        description="Specific EPIC IDs (None = all EPICs)"
    )

    # Generation settings
    mode: str = Field(
        "verified",
        description="Generation mode: 'draft' or 'verified'"
    )
    items_per_epic: int = Field(
        5,
        ge=1,
        le=15,
        description="Target number of backlog items per EPIC"
    )
    include_technical_tasks: bool = Field(
        True,
        description="Include technical/implementation tasks"
    )
    include_spikes: bool = Field(
        False,
        description="Include spike/research items for unknowns"
    )

    # Project context
    project_context: Optional[ProjectContext] = Field(
        None,
        description="Project context"
    )

    # Model selection
    model: Optional[str] = Field(
        None,
        description="LLM model to use"
    )

    # Template configuration (NEW)
    backlog_template: Optional[str] = Field(
        None,
        description="Custom backlog item template content (Markdown format)"
    )
    template_config: Optional[BacklogTemplateConfig] = Field(
        None,
        description="Template and length configuration"
    )

    # Length control - Top-level shortcuts for common settings
    default_description_words: int = Field(
        80,
        ge=20,
        le=300,
        description="Default word count for item descriptions"
    )
    default_acceptance_criteria_count: int = Field(
        4,
        ge=1,
        le=10,
        description="Default number of acceptance criteria per item"
    )

    # Pre-analysis results (Phase 1) - Pass analysis to guide generation
    epic_analysis: Optional[AnalyzeEpicsForBacklogsResponse] = Field(
        None,
        description="Pre-analysis results from /backlogs/analyze-epics endpoint"
    )

    # Dynamic item count control
    item_count_mode: str = Field(
        "auto",
        description="'auto' (AI decides based on analysis), 'guided' (use analysis recommendation), 'manual' (use items_per_epic)"
    )
    granularity_preference: str = Field(
        "medium",
        description="'fine' (more granular items), 'medium' (balanced), 'coarse' (fewer, larger items)"
    )

    # Use suggested breakdown from analysis
    use_suggested_breakdown: bool = Field(
        False,
        description="Use the suggested item breakdown from analysis as a guide"
    )

    # User-defined items per EPIC (edited/added/removed by user)
    user_defined_items: Optional[dict[str, list[SuggestedBacklogBreakdown]]] = Field(
        None,
        description="User-modified item list per EPIC ID (takes precedence over analysis suggestions)"
    )


class RefineBacklogItemRequest(BaseModel):
    """Request to refine a single backlog item."""

    item_id: str = Field(
        ...,
        description="ID of the item to refine"
    )
    current_item: BacklogItem = Field(
        ...,
        description="Current state of the item"
    )
    user_feedback: str = Field(
        ...,
        min_length=5,
        description="User feedback for refinement"
    )

    # Context
    epic: Epic = Field(
        ...,
        description="Parent EPIC for context"
    )
    brd_sections_content: list[str] = Field(
        default_factory=list,
        description="Relevant BRD section content"
    )
    project_context: Optional[ProjectContext] = Field(
        None,
        description="Project context"
    )


class RegenerateBacklogsForEpicRequest(BaseModel):
    """Request to regenerate all backlogs for a specific EPIC."""

    epic: Epic = Field(
        ...,
        description="The EPIC to regenerate backlogs for"
    )
    brd_markdown: str = Field(
        ...,
        description="Full BRD content"
    )
    feedback: Optional[str] = Field(
        None,
        description="Optional feedback to incorporate"
    )
    items_per_epic: int = Field(
        5,
        ge=1,
        le=15,
        description="Target number of items"
    )
    project_context: Optional[ProjectContext] = Field(
        None,
        description="Project context"
    )


# =============================================================================
# Response Models
# =============================================================================

class CoverageMatrixEntry(BaseModel):
    """Entry in the traceability coverage matrix."""

    brd_section: str
    brd_section_title: Optional[str] = None
    epic_ids: list[str] = Field(default_factory=list)
    backlog_ids: list[str] = Field(default_factory=list)
    is_covered: bool = False


class GenerateEpicsResponse(BaseModel):
    """Response containing generated EPICs with traceability info."""

    success: bool = True
    brd_id: str
    brd_title: Optional[str] = None

    # Generated EPICs
    epics: list[Epic] = Field(default_factory=list)

    # Traceability
    coverage_matrix: list[CoverageMatrixEntry] = Field(
        default_factory=list,
        description="BRD section to EPIC mapping"
    )
    uncovered_sections: list[str] = Field(
        default_factory=list,
        description="BRD sections not covered by any EPIC"
    )

    # Summary
    total_epics: int = 0
    recommended_order: list[str] = Field(
        default_factory=list,
        description="Recommended implementation order"
    )

    # Generation metadata
    mode: str = "verified"
    model_used: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.now)


class GenerateBacklogsResponse(BaseModel):
    """Response containing generated backlog items."""

    success: bool = True
    brd_id: str

    # Generated items
    items: list[BacklogItem] = Field(default_factory=list)

    # Grouped by EPIC
    items_by_epic: dict[str, list[str]] = Field(
        default_factory=dict,
        description="EPIC ID -> list of item IDs"
    )

    # Traceability
    coverage_matrix: list[CoverageMatrixEntry] = Field(
        default_factory=list,
        description="BRD section to backlog mapping"
    )

    # Summary
    total_items: int = 0
    total_story_points: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_priority: dict[str, int] = Field(default_factory=dict)

    # Implementation order
    recommended_order: list[str] = Field(
        default_factory=list,
        description="Recommended implementation order"
    )

    # Generation metadata
    mode: str = "verified"
    model_used: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.now)


class TraceabilityMatrixResponse(BaseModel):
    """Complete traceability matrix for a BRD."""

    success: bool = True
    brd_id: str
    brd_title: Optional[str] = None

    # Full matrix
    matrix: list[CoverageMatrixEntry] = Field(default_factory=list)

    # Summary
    total_brd_sections: int = 0
    covered_sections: int = 0
    uncovered_sections: int = 0
    coverage_percentage: float = 0.0

    # Counts
    total_epics: int = 0
    total_backlogs: int = 0

    generated_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# Streaming Event Models
# =============================================================================

class EpicStreamEvent(BaseModel):
    """Streaming event for EPIC generation progress."""

    type: str = Field(
        ...,
        description="Event type: 'thinking', 'epic', 'complete', 'error'"
    )
    content: Optional[str] = Field(
        None,
        description="Progress message for 'thinking' events"
    )
    epic: Optional[Epic] = Field(
        None,
        description="Generated EPIC for 'epic' events"
    )
    data: Optional[GenerateEpicsResponse] = Field(
        None,
        description="Complete response for 'complete' events"
    )
    error: Optional[str] = Field(
        None,
        description="Error message for 'error' events"
    )


class BacklogStreamEvent(BaseModel):
    """Streaming event for backlog generation progress."""

    type: str = Field(
        ...,
        description="Event type: 'thinking', 'item', 'complete', 'error'"
    )
    content: Optional[str] = Field(
        None,
        description="Progress message"
    )
    item: Optional[BacklogItem] = Field(
        None,
        description="Generated item"
    )
    data: Optional[GenerateBacklogsResponse] = Field(
        None,
        description="Complete response"
    )
    error: Optional[str] = Field(
        None,
        description="Error message"
    )
