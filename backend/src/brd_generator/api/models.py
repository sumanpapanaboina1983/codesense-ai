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


class DetailLevel(str, Enum):
    """Detail level for BRD output - controls verbosity and depth.

    CONCISE: Brief, executive-summary style output.
        - 1-2 paragraphs per section
        - Bullet points preferred
        - Focus on key points only
        - Good for quick reviews or presentations

    STANDARD: Balanced detail level (default).
        - 2-4 paragraphs per section
        - Mix of prose and bullets
        - Includes examples and explanations
        - Good for most use cases

    DETAILED: Comprehensive, thorough documentation.
        - Full explanations with all details
        - Extensive code references
        - Complete acceptance criteria
        - Good for formal documentation or compliance
    """

    CONCISE = "concise"
    STANDARD = "standard"
    DETAILED = "detailed"


class BRDSection(BaseModel):
    """Custom section definition for BRD output."""

    name: str = Field(
        ...,
        description="Section name (e.g., 'Executive Summary', 'Functional Requirements')"
    )
    description: Optional[str] = Field(
        None,
        description="Brief description of what this section should contain"
    )
    required: bool = Field(
        True,
        description="Whether this section is required in the output"
    )


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


class VerificationLimits(BaseModel):
    """Dynamic limits for verification queries in verified mode.

    Configure how many entities, patterns, and results to process during
    claim verification. Higher values = more thorough but slower.
    """

    max_entities_per_claim: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum entities to verify per claim"
    )
    max_patterns_per_claim: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum patterns to search per claim"
    )
    results_per_query: int = Field(
        20,
        ge=5,
        le=100,
        description="Maximum results returned per Neo4j query"
    )
    code_refs_per_evidence: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum code references to include per evidence item"
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

    # Output control
    detail_level: DetailLevel = Field(
        DetailLevel.STANDARD,
        description="""
        Controls the verbosity and depth of the generated BRD:
        - 'concise': Brief, executive-summary style (1-2 paragraphs per section)
        - 'standard': Balanced detail level (default)
        - 'detailed': Comprehensive documentation with full explanations
        """
    )

    # Custom sections (simpler alternative to full template)
    sections: Optional[list[BRDSection]] = Field(
        None,
        description="""
        Custom sections to include in the BRD. If not provided, default sections are used.

        Example:
        [
            {"name": "Executive Summary", "required": true},
            {"name": "Current Implementation", "description": "Document existing code", "required": true},
            {"name": "Data Flow", "description": "How data moves through the system", "required": false}
        ]

        If you want full control over format, use 'brd_template' instead.
        """
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

    # Verification query limits (VERIFIED mode only)
    verification_limits: Optional[VerificationLimits] = Field(
        None,
        description="""
        Dynamic limits for verification queries (VERIFIED mode only).

        Configure how thoroughly claims are verified:
        - max_entities_per_claim: Entities to verify per claim (default: 10)
        - max_patterns_per_claim: Patterns to search per claim (default: 5)
        - results_per_query: Results per Neo4j query (default: 20)
        - code_refs_per_evidence: Code refs per evidence item (default: 10)

        Higher values = more thorough verification but slower.
        """
    )

    # Consistency controls for reproducible outputs
    temperature: float = Field(
        0.3,
        ge=0.0,
        le=1.0,
        description="""
        LLM temperature for generation consistency.

        - 0.0: Most deterministic, always picks highest probability token
        - 0.3 (default): Balanced, consistent outputs with some variation
        - 0.7: More creative, higher variance
        - 1.0: Maximum creativity, high variance

        Lower values produce more consistent BRDs across runs.
        """
    )

    seed: Optional[int] = Field(
        None,
        description="""
        Random seed for reproducible outputs.

        When set, running the same request with the same seed will produce
        identical (or very similar) outputs. Useful for:
        - Testing and debugging
        - Creating reproducible documentation
        - A/B comparisons

        If not set, outputs may vary between runs.
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

    # Complete verification report (VERIFIED mode only)
    verification_report: Optional["VerificationReport"] = Field(
        None,
        description="Complete verification report with per-section claim details (VERIFIED mode only)"
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


class CodeReferenceItem(BaseModel):
    """A code reference with file path and line numbers."""

    file_path: str
    start_line: int
    end_line: int
    snippet: Optional[str] = None  # Optional code snippet


class ClaimVerificationDetail(BaseModel):
    """Detailed verification information for a single claim."""

    claim_id: str
    claim_text: str
    section: str
    status: str  # verified, partially_verified, unverified, contradicted
    confidence: float
    is_verified: bool  # True if status is 'verified'
    hallucination_risk: str
    needs_sme_review: bool
    evidence_count: int
    evidence_types: list[str] = Field(default_factory=list)  # Types of evidence found
    code_references: list[CodeReferenceItem] = Field(default_factory=list)  # Code locations for hyperlinks


class SectionVerificationReport(BaseModel):
    """Complete verification report for a single BRD section."""

    section_name: str
    status: str  # verified, partially_verified, unverified, contradicted
    confidence: float
    hallucination_risk: str

    # Claim counts
    total_claims: int
    verified_claims: int
    partially_verified_claims: int = 0
    unverified_claims: int
    contradicted_claims: int = 0
    claims_needing_sme: int = 0

    # Verification rate
    verification_rate: float = Field(
        0.0,
        description="Percentage of claims that are verified (0-100)"
    )

    # All claims in this section with their verification status
    claims: list[ClaimVerificationDetail] = Field(
        default_factory=list,
        description="All claims extracted from this section with verification details"
    )


class VerificationReport(BaseModel):
    """Complete verification report for the entire BRD.

    This provides a comprehensive view of verification results including:
    - Overall summary statistics
    - Per-section breakdown with all claims
    - Verification rates and confidence scores
    """

    brd_id: str
    brd_title: str
    generated_at: str

    # Overall summary
    overall_status: str  # verified, partially_verified, unverified
    overall_confidence: float
    hallucination_risk: str
    is_approved: bool

    # Aggregate claim statistics
    total_claims: int
    verified_claims: int
    partially_verified_claims: int = 0
    unverified_claims: int = 0
    contradicted_claims: int = 0
    claims_needing_sme: int

    # Overall verification rate
    verification_rate: float = Field(
        0.0,
        description="Percentage of claims verified (0-100)"
    )

    # Iteration info
    iterations_used: int

    # Evidence gathering stats
    evidence_sources: list[str] = Field(default_factory=list)
    queries_executed: int = 0
    files_analyzed: int = 0

    # Per-section reports
    sections: list[SectionVerificationReport] = Field(
        default_factory=list,
        description="Detailed verification report for each BRD section"
    )


class SectionSummary(BaseModel):
    """Summary of a verified section (lightweight version)."""

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
    verification_report: Optional["VerificationReport"] = Field(
        None,
        description="Complete verification report with per-section claim details"
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


# =============================================================================
# Codebase Statistics - Request/Response Models
# =============================================================================

class LanguageBreakdown(BaseModel):
    """Language statistics for a repository."""
    language: str
    file_count: int
    lines_of_code: int
    percentage: float = Field(ge=0, le=100)


class CodebaseStatistics(BaseModel):
    """Comprehensive codebase statistics."""

    # Basic counts
    total_files: int = Field(0, description="Total number of files")
    total_lines_of_code: int = Field(0, description="Total lines of code")

    # Code structure counts
    total_classes: int = Field(0, description="Total number of classes")
    total_interfaces: int = Field(0, description="Total number of interfaces")
    total_functions: int = Field(0, description="Total number of functions/methods")
    total_components: int = Field(0, description="Total number of UI components (React, Vue, etc.)")

    # API and endpoints
    total_api_endpoints: int = Field(0, description="Total REST/GraphQL endpoints")
    rest_endpoints: int = Field(0, description="Number of REST endpoints")
    graphql_operations: int = Field(0, description="Number of GraphQL operations")

    # Testing
    total_test_files: int = Field(0, description="Number of test files")
    total_test_cases: int = Field(0, description="Number of test cases")

    # Dependencies
    total_dependencies: int = Field(0, description="Number of external dependencies")

    # Database/Models
    total_database_models: int = Field(0, description="Number of database models/entities")

    # Complexity metrics
    avg_cyclomatic_complexity: Optional[float] = Field(None, description="Average cyclomatic complexity")
    max_cyclomatic_complexity: Optional[int] = Field(None, description="Maximum cyclomatic complexity")
    avg_file_size: Optional[float] = Field(None, description="Average file size in lines")

    # Language breakdown
    languages: list[LanguageBreakdown] = Field(default_factory=list)
    primary_language: Optional[str] = Field(None, description="Most used language")

    # Architecture breakdown
    services_count: int = Field(0, description="Number of services/modules")
    controllers_count: int = Field(0, description="Number of controllers")
    repositories_count: int = Field(0, description="Number of repository patterns")

    # UI specific (for frontend repos)
    ui_routes: int = Field(0, description="Number of UI routes/pages")
    ui_components: int = Field(0, description="Number of UI components")

    # Config and infrastructure
    config_files: int = Field(0, description="Number of configuration files")

    # Code quality indicators
    documented_entities: int = Field(0, description="Number of documented functions/classes")
    documentation_coverage: float = Field(0, ge=0, le=100, description="Documentation coverage percentage")


class CodebaseStatisticsResponse(BaseModel):
    """Response model for codebase statistics endpoint."""

    success: bool = True
    repository_id: str
    repository_name: str
    generated_at: datetime

    statistics: CodebaseStatistics

    # Quick summary for display
    summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Quick summary stats for dashboard display"
    )


# =============================================================================
# Business Features Discovery - Request/Response Models
# =============================================================================

class FeatureCategory(str, Enum):
    """Category of discovered business feature."""
    AUTHENTICATION = "authentication"
    USER_MANAGEMENT = "user_management"
    DATA_MANAGEMENT = "data_management"
    WORKFLOW = "workflow"
    REPORTING = "reporting"
    INTEGRATION = "integration"
    PAYMENT = "payment"
    NOTIFICATION = "notification"
    SEARCH = "search"
    ADMIN = "admin"
    CONFIGURATION = "configuration"
    OTHER = "other"


class FeatureComplexity(str, Enum):
    """Complexity level of a feature."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class CodeFootprint(BaseModel):
    """Code footprint for a discovered feature."""
    controllers: list[str] = Field(default_factory=list, description="Controller classes")
    services: list[str] = Field(default_factory=list, description="Service classes")
    repositories: list[str] = Field(default_factory=list, description="Repository classes")
    models: list[str] = Field(default_factory=list, description="Model/Entity classes")
    views: list[str] = Field(default_factory=list, description="View/JSP/Template files")
    config_files: list[str] = Field(default_factory=list, description="Configuration files")
    test_files: list[str] = Field(default_factory=list, description="Test files")
    total_files: int = Field(0, description="Total number of files")
    total_lines: int = Field(0, description="Estimated lines of code")


class FeatureEndpoint(BaseModel):
    """API endpoint associated with a feature."""
    path: str = Field(..., description="Endpoint path (e.g., /api/users)")
    method: str = Field("GET", description="HTTP method")
    controller: str = Field(..., description="Controller handling this endpoint")
    description: Optional[str] = Field(None, description="Endpoint description")


class BusinessFeature(BaseModel):
    """A discovered business feature from the codebase."""
    id: str = Field(..., description="Unique feature identifier")
    name: str = Field(..., description="Feature name")
    description: str = Field(..., description="Auto-generated description of the feature")
    category: FeatureCategory = Field(FeatureCategory.OTHER, description="Feature category")
    complexity: FeatureComplexity = Field(FeatureComplexity.MEDIUM, description="Estimated complexity")
    complexity_score: int = Field(50, ge=0, le=100, description="Complexity score 0-100")

    # Discovery metadata
    discovery_source: str = Field(..., description="How the feature was discovered (webflow, controller, service_cluster)")
    entry_points: list[str] = Field(default_factory=list, description="Entry point classes/methods")

    # Code analysis
    code_footprint: CodeFootprint = Field(default_factory=CodeFootprint)
    endpoints: list[FeatureEndpoint] = Field(default_factory=list, description="Associated API endpoints")

    # Dependencies
    depends_on: list[str] = Field(default_factory=list, description="Other features this depends on")
    depended_by: list[str] = Field(default_factory=list, description="Features that depend on this")

    # Testing
    has_tests: bool = Field(False, description="Whether the feature has test coverage")
    test_coverage_estimate: Optional[float] = Field(None, description="Estimated test coverage %")

    # BRD generation
    brd_generated: bool = Field(False, description="Whether a BRD has been generated")
    brd_id: Optional[str] = Field(None, description="Associated BRD ID if generated")


class FeaturesSummary(BaseModel):
    """Summary statistics for discovered features."""
    total_features: int = Field(0)
    by_category: dict[str, int] = Field(default_factory=dict)
    by_complexity: dict[str, int] = Field(default_factory=dict)
    by_discovery_source: dict[str, int] = Field(default_factory=dict)
    features_with_tests: int = Field(0)
    features_with_brd: int = Field(0)
    avg_complexity_score: float = Field(0.0)


class DiscoveredFeaturesResponse(BaseModel):
    """Response model for discovered business features."""
    success: bool = True
    repository_id: str
    repository_name: str
    generated_at: datetime

    features: list[BusinessFeature] = Field(default_factory=list)
    summary: FeaturesSummary = Field(default_factory=FeaturesSummary)

    # Metadata
    discovery_method: str = Field(
        "hybrid",
        description="Discovery method used: webflow, controller, service_cluster, hybrid"
    )
    discovery_duration_ms: Optional[int] = Field(None, description="Time taken for discovery")
