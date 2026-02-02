"""API Request and Response Models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Generation Mode Enum
# =============================================================================

class GenerationMode(str, Enum):
    """BRD generation mode.

    DRAFT: Fast, single-pass generation using LLM + MCP tools.
           No multi-agent verification, no evidence gathering.
           Good for quick exploration or initial drafts.

    VERIFIED: Thorough, multi-agent generation with verification.
              Includes evidence gathering, claim verification,
              hallucination detection, and confidence scoring.
              Slower but highly accurate.
    """

    DRAFT = "draft"
    VERIFIED = "verified"


class GenerationApproach(str, Enum):
    """BRD generation approach - how context is gathered and BRD is created.

    CONTEXT_FIRST: Two-phase approach:
        1. Aggregator gathers context from codebase (Neo4j + Filesystem)
        2. LLM receives context and generates BRD
        More reliable but slower. Context is explicitly passed to LLM.

    SKILLS_ONLY: Single-phase approach:
        1. Simple prompt triggers the generate-brd skill
        2. Skill instructs LLM to use MCP tools directly
        3. LLM gathers context and generates BRD in one session
        Faster but relies on skill being triggered correctly.

    AUTO: Automatically choose based on mode:
        - DRAFT mode -> SKILLS_ONLY (faster)
        - VERIFIED mode -> CONTEXT_FIRST (more reliable)
    """

    CONTEXT_FIRST = "context_first"
    SKILLS_ONLY = "skills_only"
    AUTO = "auto"


# =============================================================================
# Phase 1: Generate BRD - Request/Response Models
# =============================================================================

# =============================================================================
# Sufficiency Criteria Models
# =============================================================================

class SufficiencyDimension(BaseModel):
    """A dimension to explore when gathering context for BRD generation."""

    name: str = Field(
        ...,
        description="Name of the dimension (e.g., 'Data Model', 'Business Logic')"
    )
    description: str = Field(
        ...,
        description="What to look for in this dimension"
    )
    required: bool = Field(
        False,
        description="Whether this dimension must be covered"
    )


class SufficiencyOutputRequirements(BaseModel):
    """Output requirements for BRD generation."""

    code_traceability: bool = Field(
        True,
        description="Include file paths and line numbers for claims"
    )
    explicit_gaps: bool = Field(
        True,
        description="Document what information wasn't found"
    )
    evidence_based: bool = Field(
        True,
        description="All claims must be backed by tool results"
    )


class SufficiencyCriteria(BaseModel):
    """Criteria for what makes a complete analysis before generating BRD.

    Customize these to define what context is sufficient for your project.

    Example for a security-focused project:
    ```json
    {
        "dimensions": [
            {"name": "Authentication", "description": "Auth mechanisms", "required": true},
            {"name": "Authorization", "description": "RBAC, permissions", "required": true},
            {"name": "Data Protection", "description": "Encryption, PII", "required": true}
        ],
        "min_dimensions_covered": 3
    }
    ```
    """

    dimensions: list[SufficiencyDimension] = Field(
        default_factory=list,
        description="Dimensions to explore when gathering context"
    )
    output_requirements: Optional[SufficiencyOutputRequirements] = Field(
        None,
        description="Requirements for BRD output format"
    )
    min_dimensions_covered: int = Field(
        3,
        ge=1,
        description="Minimum number of dimensions to cover before generating"
    )


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
    """Request model for BRD generation.

    Supports two generation modes:

    DRAFT MODE (default):
    - Fast, single-pass generation using LLM + MCP tools
    - No multi-agent verification or evidence gathering
    - Good for quick exploration or initial drafts

    VERIFIED MODE:
    - Thorough, multi-agent generation with verification
    - Generator Agent creates BRD sections iteratively
    - Verifier Agent validates claims against codebase
    - Includes evidence gathering, hallucination detection, confidence scoring

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

    # Generation mode selection
    mode: GenerationMode = Field(
        GenerationMode.DRAFT,
        description="""
        Generation mode:
        - 'draft': Fast single-pass generation (default). Uses LLM + MCP tools
          but skips multi-agent verification. Good for quick exploration.
        - 'verified': Thorough multi-agent generation with verification,
          evidence gathering, and hallucination detection. Slower but more accurate.
        """
    )

    # Generation approach selection
    approach: GenerationApproach = Field(
        GenerationApproach.AUTO,
        description="""
        How context is gathered and BRD is generated:
        - 'context_first': Aggregator gathers context first, then LLM generates BRD
          with explicit context. More reliable but slower.
        - 'skills_only': Simple prompt triggers skill, LLM uses MCP tools directly.
          Faster but relies on skill matching.
        - 'auto' (default): Automatically choose based on mode.
          DRAFT -> skills_only, VERIFIED -> context_first
        """
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

    # Multi-agent verification settings (only used in VERIFIED mode)
    max_iterations: int = Field(
        3,
        ge=1,
        le=10,
        description="Maximum verification iterations (VERIFIED mode only)"
    )

    min_confidence: float = Field(
        0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score for BRD approval (VERIFIED mode only)"
    )

    show_evidence: bool = Field(
        False,
        description="Include full evidence trail in response (VERIFIED mode only)"
    )

    # Sufficiency criteria - what makes a complete analysis
    sufficiency_criteria: Optional[SufficiencyCriteria] = Field(
        None,
        description="""
        Define what context is sufficient for BRD generation.

        Customize dimensions to explore (e.g., Data Model, Business Logic, API Contracts)
        and set minimum coverage requirements.

        If not provided, uses default dimensions:
        - Data Model (required)
        - Business Logic (required)
        - User Flow (required)
        - API Contracts (optional)
        - Validation Rules (optional)
        - Error Handling (optional)
        - Dependencies (optional)
        """
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
    """Response model for BRD generation.

    Response varies based on generation mode:

    DRAFT MODE:
    - BRD document
    - mode = "draft"
    - No verification metrics (is_verified, confidence_score, etc. are None)
    - Includes a warning that draft may need review

    VERIFIED MODE:
    - BRD document
    - mode = "verified"
    - Full verification metrics (confidence, hallucination risk, iterations)
    - Optional evidence trail (when show_evidence=True)
    - SME review requirements if applicable
    """

    success: bool = True
    brd: BRDResponse

    # Generation mode used
    mode: GenerationMode = Field(
        ...,
        description="Generation mode used: 'draft' or 'verified'"
    )

    # Verification metrics (only populated in VERIFIED mode)
    is_verified: Optional[bool] = Field(
        None,
        description="Whether the BRD passed verification (VERIFIED mode only)"
    )
    confidence_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Overall confidence score 0-1 (VERIFIED mode only)"
    )
    hallucination_risk: Optional[str] = Field(
        None,
        description="Hallucination risk level: none, low, medium, high, critical (VERIFIED mode only)"
    )
    iterations_used: Optional[int] = Field(
        None,
        description="Number of generator-verifier iterations (VERIFIED mode only)"
    )

    # Evidence trail (only in VERIFIED mode if requested)
    evidence_trail: Optional["EvidenceTrailSummary"] = Field(
        None,
        description="Evidence trail summary (VERIFIED mode with show_evidence=True)"
    )
    evidence_trail_text: Optional[str] = Field(
        None,
        description="Full evidence trail as formatted text (VERIFIED mode with show_evidence=True)"
    )

    # SME review requirements (VERIFIED mode only)
    needs_sme_review: bool = Field(
        False,
        description="Whether the BRD has claims that need SME review (VERIFIED mode only)"
    )
    sme_review_claims: list["ClaimSummary"] = Field(
        default_factory=list,
        description="Claims flagged for SME review (VERIFIED mode only)"
    )

    # Draft mode warning
    draft_warning: Optional[str] = Field(
        None,
        description="Warning message for draft mode (e.g., 'Draft may contain inaccuracies')"
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


# =============================================================================
# Phase 3: Agentic Readiness Report - Request/Response Models
# =============================================================================

class ReadinessGrade(str, Enum):
    """Readiness grade levels."""
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class RecommendationPriority(str, Enum):
    """Recommendation priority levels."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RecommendationCategory(str, Enum):
    """Recommendation category."""
    TESTING = "testing"
    DOCUMENTATION = "documentation"


class UntestedCriticalFunction(BaseModel):
    """An untested critical function."""
    entity_id: str
    name: str
    file_path: str
    reason: str
    stereotype: Optional[str] = None


class TestingCoverage(BaseModel):
    """Testing coverage metrics."""
    percentage: int = Field(ge=0, le=100)
    grade: ReadinessGrade


class TestQuality(BaseModel):
    """Test quality assessment."""
    has_unit_tests: bool
    has_integration_tests: bool
    has_e2e_tests: bool
    frameworks: list[str] = Field(default_factory=list)
    mocking_coverage: Optional[float] = None


class TestingReadinessResponse(BaseModel):
    """Testing readiness assessment."""
    overall_grade: ReadinessGrade
    overall_score: int = Field(ge=0, le=100)
    coverage: TestingCoverage
    untested_critical_functions: list[UntestedCriticalFunction] = Field(default_factory=list)
    test_quality: TestQuality
    recommendations: list[str] = Field(default_factory=list)


class UndocumentedPublicApi(BaseModel):
    """An undocumented public API."""
    entity_id: str
    name: str
    file_path: str
    kind: str
    signature: Optional[str] = None


class DocumentationCoverage(BaseModel):
    """Documentation coverage metrics."""
    percentage: int = Field(ge=0, le=100)
    grade: ReadinessGrade


class DocumentationQualityDistribution(BaseModel):
    """Distribution of documentation quality."""
    excellent: int = 0
    good: int = 0
    partial: int = 0
    minimal: int = 0
    none: int = 0


class DocumentationReadinessResponse(BaseModel):
    """Documentation readiness assessment."""
    overall_grade: ReadinessGrade
    overall_score: int = Field(ge=0, le=100)
    coverage: DocumentationCoverage
    public_api_coverage: DocumentationCoverage
    undocumented_public_apis: list[UndocumentedPublicApi] = Field(default_factory=list)
    quality_distribution: DocumentationQualityDistribution
    recommendations: list[str] = Field(default_factory=list)


class ReadinessRecommendation(BaseModel):
    """A recommendation for improving readiness."""
    priority: RecommendationPriority
    category: RecommendationCategory
    title: str
    description: str
    affected_count: int
    affected_entities: list[str] = Field(default_factory=list)
    estimated_effort: Optional[str] = None


class EnrichmentAction(BaseModel):
    """An available enrichment action."""
    id: str
    name: str
    description: str
    affected_entities: int
    category: str
    is_automated: bool


class ReadinessSummary(BaseModel):
    """Summary statistics for readiness report."""
    total_entities: int
    tested_entities: int
    documented_entities: int
    critical_gaps: int


class AgenticReadinessResponse(BaseModel):
    """Complete Agentic Readiness Report response."""
    success: bool = True
    repository_id: str
    repository_name: str
    generated_at: datetime

    overall_grade: ReadinessGrade
    overall_score: int = Field(ge=0, le=100)
    is_agentic_ready: bool = Field(
        ...,
        description="Whether the repository meets agentic readiness threshold (score >= 75)"
    )

    testing: TestingReadinessResponse
    documentation: DocumentationReadinessResponse

    recommendations: list[ReadinessRecommendation] = Field(default_factory=list)
    enrichment_actions: list[EnrichmentAction] = Field(default_factory=list)

    summary: ReadinessSummary


# =============================================================================
# Phase 4: Codebase Enrichment - Request/Response Models
# =============================================================================

class DocumentationStyle(str, Enum):
    """Documentation style for generation."""
    JSDOC = "jsdoc"
    JAVADOC = "javadoc"
    DOCSTRING = "docstring"
    XMLDOC = "xmldoc"
    GODOC = "godoc"


class DocumentationEnrichmentRequest(BaseModel):
    """Request for documentation enrichment."""
    entity_ids: list[str] | str = Field(
        ...,
        description="Entity IDs to enrich, or 'all-undocumented'"
    )
    style: DocumentationStyle = DocumentationStyle.JSDOC
    include_examples: bool = True
    include_parameters: bool = True
    include_returns: bool = True
    include_throws: bool = True
    max_entities: Optional[int] = Field(
        50,
        description="Maximum entities to process (for 'all-undocumented')"
    )


class TestType(str, Enum):
    """Test type for generation."""
    UNIT = "unit"
    INTEGRATION = "integration"


class TestEnrichmentRequest(BaseModel):
    """Request for test enrichment."""
    entity_ids: list[str] | str = Field(
        ...,
        description="Entity IDs to generate tests for, or 'all-untested'"
    )
    framework: str = Field(
        "jest",
        description="Test framework to use (jest, junit, pytest, etc.)"
    )
    test_types: list[TestType] = Field(
        default_factory=lambda: [TestType.UNIT]
    )
    include_mocks: bool = True
    include_edge_cases: bool = True
    max_entities: Optional[int] = Field(
        20,
        description="Maximum entities to process (for 'all-untested')"
    )


class GeneratedContent(BaseModel):
    """Generated content for a single entity."""
    entity_id: str
    entity_name: str
    file_path: str
    content: str
    insert_position: dict[str, int] = Field(
        ...,
        description="Line and column for insertion"
    )
    content_type: str
    is_new_file: bool


class EnrichmentError(BaseModel):
    """Error during enrichment."""
    entity_id: str
    error: str


class EnrichmentResponse(BaseModel):
    """Response from enrichment operation."""
    success: bool = True
    entities_processed: int
    entities_enriched: int
    entities_skipped: int
    generated_content: list[GeneratedContent] = Field(default_factory=list)
    errors: list[EnrichmentError] = Field(default_factory=list)
    enrichment_type: str
