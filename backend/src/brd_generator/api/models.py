"""API Request and Response Models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Phase 1: Generate BRD - Request/Response Models
# =============================================================================

class BRDTemplateConfig(BaseModel):
    """Template configuration for BRD generation."""

    # Custom template content (optional - uses default if not provided)
    brd_template: Optional[str] = Field(
        None,
        description="Custom BRD template content (Markdown format)"
    )

    # Organization-specific settings
    organization_name: Optional[str] = Field(
        None,
        description="Organization name for branding"
    )
    document_prefix: str = Field(
        "BRD",
        description="Document ID prefix (e.g., 'ACME-BRD')"
    )

    # Approval settings
    require_approvals: bool = Field(
        True,
        description="Include approval section in BRD"
    )
    approval_roles: list[str] = Field(
        default_factory=lambda: ["Product Owner", "Tech Lead"],
        description="Roles required for approval"
    )

    # Output preferences
    include_code_references: bool = Field(
        True,
        description="Include code file references in BRD"
    )
    include_risk_matrix: bool = Field(
        True,
        description="Include risk assessment matrix"
    )
    max_requirements_per_section: int = Field(
        10,
        description="Maximum requirements per section"
    )

    # Custom sections
    custom_sections: list[str] = Field(
        default_factory=list,
        description="Additional sections to include"
    )


class GenerateBRDRequest(BaseModel):
    """Request model for BRD generation with multi-agent verification.

    Multi-agent verification is always enabled:
    - Generator Agent creates BRD sections iteratively
    - Verifier Agent validates claims against codebase

    BRD structure is TEMPLATE-DRIVEN:
    - Upload any BRD template and the system will follow its structure
    - Template is parsed by LLM to understand sections and content expectations
    - No hardcoded sections - everything comes from the template
    """

    feature_description: str = Field(
        ...,
        description="Description of the feature to generate BRD for",
        min_length=10,
        examples=["Add a caching layer to improve API response times"]
    )

    affected_components: Optional[list[str]] = Field(
        None,
        description="List of components affected by this feature"
    )

    include_similar_features: bool = Field(
        True,
        description="Search for similar features in codebase"
    )

    # Template-driven BRD generation (THE KEY FIELD)
    brd_template: Optional[str] = Field(
        None,
        description="""
        Custom BRD template content (markdown format).

        The system will parse this template using LLM to understand:
        - Section names and their order
        - What each section should contain
        - Format requirements (tables, lists, diagrams)
        - Writing guidelines and examples

        Example sections that might be in a template:
        - Feature Overview
        - Functional Requirements
        - Business Rules and Validations
        - Actors and Interactions
        - Business Process Flow
        - Acceptance Criteria

        If not provided, a default template structure will be used.
        """
    )

    template_config: Optional[BRDTemplateConfig] = Field(
        None,
        description="Additional template configuration (org name, approval roles, etc.)"
    )

    # Multi-agent verification settings (always enabled)
    max_iterations: int = Field(
        3,
        ge=1,
        le=5,
        description="Maximum verification iterations before accepting BRD"
    )

    min_confidence: float = Field(
        0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score for BRD approval"
    )

    show_evidence: bool = Field(
        False,
        description="Include full evidence trail in response (hidden by default)"
    )


class RequirementResponse(BaseModel):
    """Requirement in BRD response."""

    id: str
    title: str
    description: str
    priority: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class BRDResponse(BaseModel):
    """BRD document response."""

    id: str = Field(..., description="Unique BRD identifier")
    title: str
    version: str = "1.0"
    created_at: datetime

    business_context: str
    objectives: list[str]
    functional_requirements: list[RequirementResponse]
    technical_requirements: list[RequirementResponse]
    dependencies: list[str]
    risks: list[str]

    # Markdown representation
    markdown: str = Field(..., description="Full BRD in Markdown format")


class GenerateBRDResponse(BaseModel):
    """Response model for BRD generation with verification results.

    Multi-agent verification is always enabled, so response includes:
    - The generated BRD document
    - Verification metrics (confidence, hallucination risk, etc.)
    - Optional evidence trail (when show_evidence=True)
    """

    success: bool = True
    brd: BRDResponse

    # Verification metrics (always included since multi-agent is always on)
    is_verified: bool = Field(
        ...,
        description="Whether the BRD passed verification"
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence score (0-1)"
    )
    hallucination_risk: str = Field(
        ...,
        description="Hallucination risk level: none, low, medium, high, critical"
    )
    iterations_used: int = Field(
        ...,
        description="Number of generator-verifier iterations"
    )

    # Evidence trail (only if requested)
    evidence_trail: Optional["EvidenceTrailSummary"] = Field(
        None,
        description="Evidence trail summary (only included if show_evidence=True)"
    )
    evidence_trail_text: Optional[str] = Field(
        None,
        description="Full evidence trail as formatted text (only if show_evidence=True)"
    )

    # SME review requirements
    needs_sme_review: bool = Field(
        False,
        description="Whether the BRD has claims that need SME review"
    )
    sme_review_claims: list["ClaimSummary"] = Field(
        default_factory=list,
        description="Claims flagged for SME review"
    )

    metadata: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Phase 2: Generate Epics - Request/Response Models
# =============================================================================

class GenerateEpicsRequest(BaseModel):
    """Request model for Phase 2: Generate Epics from BRD."""

    brd: BRDResponse = Field(
        ...,
        description="The approved BRD document from Phase 1"
    )

    use_skill: bool = Field(
        True,
        description="Use skill-based generation with MCP tools"
    )


class EpicResponse(BaseModel):
    """Epic in response."""

    id: str = Field(..., description="Epic identifier (e.g., EPIC-001)")
    title: str
    description: str
    components: list[str] = Field(default_factory=list)
    priority: str = "medium"
    estimated_effort: str = "medium"  # small, medium, large
    blocked_by: list[str] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)
    estimated_story_count: Optional[int] = None


class GenerateEpicsResponse(BaseModel):
    """Response model for Phase 2: Generate Epics."""

    success: bool = True
    brd_id: str = Field(..., description="Reference to source BRD")
    brd_title: str
    epics: list[EpicResponse]
    implementation_order: list[str] = Field(
        default_factory=list,
        description="Recommended order of Epic implementation"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Phase 3: Generate Backlogs - Request/Response Models
# =============================================================================

class GenerateBacklogsRequest(BaseModel):
    """Request model for Phase 3: Generate Backlogs from Epics."""

    brd: BRDResponse = Field(
        ...,
        description="The approved BRD document (for context)"
    )

    epics: list[EpicResponse] = Field(
        ...,
        description="The approved Epics from Phase 2"
    )

    use_skill: bool = Field(
        True,
        description="Use skill-based generation with MCP tools"
    )


class UserStoryResponse(BaseModel):
    """User Story in response."""

    id: str = Field(..., description="Story identifier (e.g., STORY-001)")
    epic_id: str = Field(..., description="Parent Epic ID")
    title: str
    description: str

    # User story format
    as_a: str = Field(..., description="User role")
    i_want: str = Field(..., description="Desired capability")
    so_that: str = Field(..., description="Expected benefit")

    # Details
    acceptance_criteria: list[str] = Field(default_factory=list)
    files_to_modify: list[str] = Field(default_factory=list)
    files_to_create: list[str] = Field(default_factory=list)
    technical_notes: Optional[str] = None

    # Estimation
    estimated_points: Optional[int] = None
    priority: str = "medium"

    # Dependencies
    blocked_by: list[str] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)

    # Formatted output
    user_story_format: str = Field(
        ...,
        description="Story in 'As a... I want... So that...' format"
    )


class GenerateBacklogsResponse(BaseModel):
    """Response model for Phase 3: Generate Backlogs."""

    success: bool = True
    epics: list[EpicResponse] = Field(..., description="Source Epics (for reference)")
    stories: list[UserStoryResponse]
    implementation_order: list[str] = Field(
        default_factory=list,
        description="Recommended order of Story implementation"
    )
    total_story_points: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Phase 4: Create JIRA Issues - Request/Response Models
# =============================================================================

class CreateJiraRequest(BaseModel):
    """Request model for Phase 4: Create JIRA Issues."""

    project_key: str = Field(
        ...,
        description="JIRA project key (e.g., 'PROJ')",
        min_length=2,
        max_length=10
    )

    epics: list[EpicResponse] = Field(
        ...,
        description="Approved Epics to create in JIRA"
    )

    stories: list[UserStoryResponse] = Field(
        ...,
        description="Approved Stories to create in JIRA"
    )

    use_skill: bool = Field(
        True,
        description="Use skill-based creation with Atlassian MCP"
    )

    # Optional JIRA configuration
    epic_issue_type: str = Field(
        "Epic",
        description="JIRA issue type for Epics"
    )
    story_issue_type: str = Field(
        "Story",
        description="JIRA issue type for Stories"
    )
    labels: list[str] = Field(
        default_factory=lambda: ["brd-generated"],
        description="Labels to add to created issues"
    )


class JiraIssueResult(BaseModel):
    """Result of creating a single JIRA issue."""

    local_id: str = Field(..., description="Local ID (e.g., EPIC-001)")
    jira_key: Optional[str] = Field(None, description="JIRA issue key (e.g., PROJ-123)")
    jira_url: Optional[str] = Field(None, description="Full JIRA issue URL")
    status: str = Field(..., description="Creation status: created, failed, skipped")
    error: Optional[str] = Field(None, description="Error message if failed")


class CreateJiraResponse(BaseModel):
    """Response model for Phase 4: Create JIRA Issues."""

    success: bool = True
    project_key: str
    created_at: datetime = Field(default_factory=datetime.now)

    epics_created: list[JiraIssueResult]
    stories_created: list[JiraIssueResult]
    links_created: list[dict[str, str]] = Field(default_factory=list)

    # Summary
    total_created: int = 0
    total_failed: int = 0

    errors: list[dict[str, str]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Common Models
# =============================================================================

class ErrorResponse(BaseModel):
    """Error response model."""

    success: bool = False
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str
    mcp_servers: dict[str, bool] = Field(default_factory=dict)
    copilot_available: bool = False


# =============================================================================
# Multi-Agent Verified BRD - Request/Response Models
# =============================================================================

class GenerateVerifiedBRDRequest(BaseModel):
    """Request model for multi-agent verified BRD generation."""

    feature_description: str = Field(
        ...,
        description="Description of the feature to generate BRD for",
        min_length=10,
        examples=["Add a caching layer to improve API response times"]
    )

    affected_components: Optional[list[str]] = Field(
        None,
        description="List of components affected by this feature"
    )

    include_similar_features: bool = Field(
        True,
        description="Search for similar features in codebase"
    )

    max_iterations: int = Field(
        3,
        ge=1,
        le=5,
        description="Maximum verification iterations before accepting BRD"
    )

    min_confidence: float = Field(
        0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score for BRD approval"
    )

    show_evidence: bool = Field(
        False,
        description="Include full evidence trail in response (hidden by default)"
    )


class ClaimSummary(BaseModel):
    """Summary of a verified claim."""

    claim_id: str
    text: str
    section: str
    status: str  # verified, partially_verified, unverified, contradicted
    confidence: float
    hallucination_risk: str
    needs_sme_review: bool
    evidence_count: int


class SectionSummary(BaseModel):
    """Summary of a verified section."""

    section_name: str
    status: str
    confidence: float
    total_claims: int
    verified_claims: int
    unverified_claims: int
    hallucination_risk: str


class EvidenceTrailSummary(BaseModel):
    """Summary of the evidence trail (shown when requested)."""

    brd_id: str
    overall_confidence: float
    overall_status: str
    hallucination_risk: str

    total_claims: int
    verified_claims: int
    claims_needing_sme: int

    evidence_sources: list[str]
    queries_executed: int
    files_analyzed: int

    sections: list[SectionSummary]
    claims: Optional[list[ClaimSummary]] = None  # Only if show_evidence=True


class GenerateVerifiedBRDResponse(BaseModel):
    """Response model for multi-agent verified BRD generation."""

    success: bool = True
    brd: BRDResponse

    # Verification metrics
    is_verified: bool = Field(
        ...,
        description="Whether the BRD passed verification"
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence score (0-1)"
    )
    hallucination_risk: str = Field(
        ...,
        description="Hallucination risk level: none, low, medium, high, critical"
    )
    iterations_used: int = Field(
        ...,
        description="Number of generator-verifier iterations"
    )

    # Evidence trail (only if requested)
    evidence_trail: Optional[EvidenceTrailSummary] = Field(
        None,
        description="Evidence trail summary (only included if show_evidence=True)"
    )
    evidence_trail_text: Optional[str] = Field(
        None,
        description="Full evidence trail as formatted text (only if show_evidence=True)"
    )

    # SME review requirements
    needs_sme_review: bool = Field(
        False,
        description="Whether the BRD has claims that need SME review"
    )
    sme_review_claims: list[ClaimSummary] = Field(
        default_factory=list,
        description="Claims flagged for SME review"
    )

    metadata: dict[str, Any] = Field(default_factory=dict)


class GetEvidenceTrailRequest(BaseModel):
    """Request model for retrieving evidence trail."""

    brd_id: str = Field(
        ...,
        description="BRD ID to retrieve evidence trail for"
    )

    show_details: bool = Field(
        True,
        description="Include full evidence details vs just summary"
    )


class GetEvidenceTrailResponse(BaseModel):
    """Response for evidence trail retrieval."""

    success: bool = True
    brd_id: str
    evidence_trail: EvidenceTrailSummary
    evidence_trail_text: str = Field(
        ...,
        description="Full formatted evidence trail"
    )
