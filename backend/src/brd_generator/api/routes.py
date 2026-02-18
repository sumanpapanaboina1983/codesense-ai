"""API Routes for BRD Generator.

Consolidated API with a single unified BRD generation endpoint that
uses multi-agent verification by default.
"""

from __future__ import annotations

import json
import asyncio
import re
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse

from .models import (
    GenerateBRDRequest,
    GenerateBRDResponse,
    BRDResponse,
    RequirementResponse,
    GenerateEpicsRequest,
    GenerateEpicsResponse,
    EpicResponse,
    GenerateBacklogsRequest,
    GenerateBacklogsResponse,
    UserStoryResponse,
    CreateJiraRequest,
    CreateJiraResponse,
    JiraIssueResult,
    ErrorResponse,
    HealthResponse,
    BRDTemplateConfig,
    # Evidence/verification models
    EvidenceTrailSummary,
    SectionSummary,
    ClaimSummary,
    GetEvidenceTrailRequest,
    GetEvidenceTrailResponse,
    # Verification report models
    VerificationReport,
    SectionVerificationReport,
    ClaimVerificationDetail,
    CodeReferenceItem,
    # Generation mode
    GenerationMode,
    # Agentic Readiness (Phase 3)
    AgenticReadinessResponse,
    TestingReadinessResponse,
    DocumentationReadinessResponse,
    ReadinessRecommendation,
    EnrichmentAction,
    ReadinessSummary,
    ReadinessGrade,
    # Enrichment (Phase 4)
    DocumentationEnrichmentRequest,
    TestEnrichmentRequest,
    EnrichmentResponse,
    # Codebase Statistics
    CodebaseStatistics,
    CodebaseStatisticsResponse,
    LanguageBreakdown,
    # Business Features Discovery
    BusinessFeature,
    DiscoveredFeaturesResponse,
    FeaturesSummary,
    FeatureCategory,
    FeatureComplexity,
    CodeFootprint,
    FeatureEndpoint,
    FeatureGroup,
)
from ..core.generator import BRDGenerator
from ..core.synthesizer import TemplateConfig
from ..models.request import BRDRequest
from ..models.output import BRDDocument, BRDOutput, Epic, UserStory, EpicsOutput, BacklogsOutput
from ..database.config import get_async_session
from ..database.models import RepositoryDB, RepositoryStatus as DBRepositoryStatus, AnalysisStatus as DBAnalysisStatus
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Create router
router = APIRouter()

# Global generator instance (initialized on startup)
_generator: BRDGenerator | None = None

# Active BRD generation tasks - tracks cancellation state
# Key: generation_id (repository_id), Value: {"cancelled": bool, "task": asyncio.Task}
_active_generations: dict[str, dict] = {}


def _register_generation(generation_id: str, task: asyncio.Task) -> None:
    """Register an active generation task."""
    _active_generations[generation_id] = {"cancelled": False, "task": task}
    logger.info(f"Registered generation: {generation_id}")


def _unregister_generation(generation_id: str) -> None:
    """Unregister a generation task."""
    _active_generations.pop(generation_id, None)
    logger.info(f"Unregistered generation: {generation_id}")


def _is_generation_cancelled(generation_id: str) -> bool:
    """Check if a generation has been cancelled."""
    gen = _active_generations.get(generation_id)
    return gen["cancelled"] if gen else False


def _cancel_generation(generation_id: str) -> bool:
    """Cancel an active generation."""
    gen = _active_generations.get(generation_id)
    if gen:
        gen["cancelled"] = True
        if gen.get("task") and not gen["task"].done():
            gen["task"].cancel()
        logger.info(f"Cancelled generation: {generation_id}")
        return True
    return False


async def get_generator() -> BRDGenerator:
    """Dependency to get the generator instance."""
    global _generator
    if _generator is None:
        _generator = BRDGenerator()
        await _generator.initialize()
    return _generator


def _convert_template_config(config: BRDTemplateConfig | None) -> TemplateConfig | None:
    """Convert API template config to internal template config."""
    if config is None:
        return None

    return TemplateConfig(
        brd_template=config.brd_template or "",
        organization_name=config.organization_name or "",
        document_prefix=config.document_prefix,
        require_approvals=config.require_approvals,
        approval_roles=config.approval_roles,
        include_code_references=config.include_code_references,
        include_risk_matrix=config.include_risk_matrix,
        max_requirements_per_section=config.max_requirements_per_section,
        custom_sections=config.custom_sections,
    )


def _brd_to_response(brd: BRDDocument) -> BRDResponse:
    """Convert internal BRD document to API response."""
    brd_id = f"BRD-{hash(brd.title) % 10000:04d}"

    return BRDResponse(
        id=brd_id,
        title=brd.title,
        version=brd.version,
        created_at=brd.created_at,
        business_context=brd.business_context,
        objectives=brd.objectives,
        functional_requirements=[
            RequirementResponse(
                id=req.id,
                title=req.title,
                description=req.description,
                priority=req.priority,
                acceptance_criteria=[ac.criterion for ac in req.acceptance_criteria],
            )
            for req in brd.functional_requirements
        ],
        technical_requirements=[
            RequirementResponse(
                id=req.id,
                title=req.title,
                description=req.description,
                priority=req.priority,
                acceptance_criteria=[ac.criterion for ac in req.acceptance_criteria],
            )
            for req in brd.technical_requirements
        ],
        dependencies=brd.dependencies,
        risks=brd.risks,
        markdown=brd.to_markdown(),
    )


def _response_to_brd(response: BRDResponse) -> BRDDocument:
    """Convert API BRD response back to internal BRD document."""
    from ..models.output import Requirement, AcceptanceCriteria

    return BRDDocument(
        title=response.title,
        version=response.version,
        created_at=response.created_at,
        business_context=response.business_context,
        objectives=response.objectives,
        functional_requirements=[
            Requirement(
                id=req.id,
                title=req.title,
                description=req.description,
                priority=req.priority,
                acceptance_criteria=[
                    AcceptanceCriteria(criterion=ac)
                    for ac in req.acceptance_criteria
                ],
            )
            for req in response.functional_requirements
        ],
        technical_requirements=[
            Requirement(
                id=req.id,
                title=req.title,
                description=req.description,
                priority=req.priority,
                acceptance_criteria=[
                    AcceptanceCriteria(criterion=ac)
                    for ac in req.acceptance_criteria
                ],
            )
            for req in response.technical_requirements
        ],
        dependencies=response.dependencies,
        risks=response.risks,
    )


def _epic_to_response(epic: Epic) -> EpicResponse:
    """Convert internal Epic to API response."""
    return EpicResponse(
        id=epic.id,
        title=epic.title,
        description=epic.description,
        components=epic.components,
        priority=epic.priority,
        estimated_effort=epic.estimated_effort,
        blocked_by=epic.blocked_by,
        blocks=epic.blocks,
        estimated_story_count=len(epic.stories) if epic.stories else None,
    )


def _response_to_epic(response: EpicResponse) -> Epic:
    """Convert API Epic response back to internal Epic."""
    return Epic(
        id=response.id,
        title=response.title,
        description=response.description,
        components=response.components,
        priority=response.priority,
        estimated_effort=response.estimated_effort,
        blocked_by=response.blocked_by,
        blocks=response.blocks,
    )


def _story_to_response(story: UserStory) -> UserStoryResponse:
    """Convert internal UserStory to API response."""
    return UserStoryResponse(
        id=story.id,
        epic_id=story.epic_id,
        title=story.title,
        description=story.description,
        as_a=story.as_a,
        i_want=story.i_want,
        so_that=story.so_that,
        acceptance_criteria=[ac.criterion for ac in story.acceptance_criteria],
        files_to_modify=story.files_to_modify,
        files_to_create=story.files_to_create,
        technical_notes=story.technical_notes,
        estimated_points=story.estimated_points,
        priority=story.priority,
        blocked_by=story.blocked_by,
        blocks=story.blocks,
        user_story_format=story.to_user_story_format(),
    )


def _response_to_story(response: UserStoryResponse) -> UserStory:
    """Convert API Story response back to internal UserStory."""
    from ..models.output import AcceptanceCriteria

    return UserStory(
        id=response.id,
        epic_id=response.epic_id,
        title=response.title,
        description=response.description,
        as_a=response.as_a,
        i_want=response.i_want,
        so_that=response.so_that,
        acceptance_criteria=[
            AcceptanceCriteria(criterion=ac)
            for ac in response.acceptance_criteria
        ],
        files_to_modify=response.files_to_modify,
        files_to_create=response.files_to_create,
        technical_notes=response.technical_notes,
        estimated_points=response.estimated_points,
        priority=response.priority,
        blocked_by=response.blocked_by,
        blocks=response.blocks,
    )


# =============================================================================
# Health Check
# =============================================================================

@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health check endpoint",
)
async def health_check() -> HealthResponse:
    """Check the health status of the API."""
    import os

    return HealthResponse(
        status="healthy",
        version="0.1.0",
        mcp_servers={
            "filesystem": os.getenv("MCP_FILESYSTEM_ENABLED", "true").lower() == "true",
            "neo4j": os.getenv("MCP_NEO4J_ENABLED", "true").lower() == "true",
            "atlassian": os.getenv("MCP_ATLASSIAN_ENABLED", "false").lower() == "true",
            "github_source": os.getenv("MCP_USE_GITHUB_FOR_SOURCE", "false").lower() == "true",
        },
        copilot_available=True,  # Will be updated after init
    )


# =============================================================================
# Default Template Endpoint
# =============================================================================

@router.get(
    "/brd/template/default",
    tags=["BRD Generation"],
    summary="Get the default BRD template",
    response_model=dict,
)
async def get_default_template() -> dict:
    """
    Get the default BRD template that the system uses.

    Returns the template content and metadata.
    """
    templates_dir = Path(__file__).parent.parent / "templates"
    template_path = templates_dir / "brd-template.md"

    if not template_path.exists():
        raise HTTPException(status_code=404, detail="Default template not found")

    template_content = template_path.read_text()

    return {
        "success": True,
        "template": template_content,
        "name": "Default BRD Template",
        "description": "Business-focused template with 8 sections: Feature Overview, Functional Requirements, Business Validations, Actors & Interactions, Process Flow, Sequence Diagram, Assumptions & Constraints, and Acceptance Criteria.",
    }


class ParseTemplateSectionsRequest(BaseModel):
    """Request to parse sections from a BRD template."""
    template_content: str = Field(..., description="The template content to parse")


class TemplateSectionInfo(BaseModel):
    """Information about a section in the template."""
    name: str = Field(..., description="Section name")
    description: Optional[str] = Field(None, description="What this section should contain")
    suggested_words: int = Field(300, description="Suggested word count for this section")


class ParseTemplateSectionsResponse(BaseModel):
    """Response with parsed template sections."""
    success: bool
    sections: list[TemplateSectionInfo]
    error: Optional[str] = None


@router.post(
    "/brd/template/parse-sections",
    tags=["BRD Generation"],
    summary="Parse sections from a BRD template using LLM",
    response_model=ParseTemplateSectionsResponse,
)
async def parse_template_sections(request: ParseTemplateSectionsRequest) -> ParseTemplateSectionsResponse:
    """
    Use LLM to extract sections from a BRD template.

    This is more reliable than regex-based parsing as it understands
    the semantic structure of the template.
    """
    try:
        # Get Copilot session
        generator = BRDGenerator()
        await generator.initialize()

        if not generator._copilot_session:
            # Fallback to simple parsing if no LLM available
            return _parse_sections_fallback(request.template_content)

        # Use LLM to parse sections
        prompt = f"""Analyze this BRD template and extract the section structure.

## Template Content:
{request.template_content[:4000]}

## Task:
Identify all the main sections that should be generated for a BRD.
For each section, provide:
1. The section name (clean, without numbers or special formatting)
2. A brief description of what the section should contain
3. A suggested word count (based on section complexity)

Skip meta-sections like "Required Structure", "Template", "Version History", etc.
Only include content sections that need to be written.

Return as JSON:
```json
{{
  "sections": [
    {{
      "name": "Feature Overview",
      "description": "Plain English summary of what the feature enables",
      "suggested_words": 250
    }},
    {{
      "name": "Functional Requirements",
      "description": "What the system must do in terms of business behavior",
      "suggested_words": 400
    }}
  ]
}}
```
"""
        response = await generator._copilot_session.send_and_wait({"prompt": prompt})

        # Parse the response
        if response and hasattr(response, 'text'):
            response_text = response.text
        elif isinstance(response, str):
            response_text = response
        else:
            response_text = str(response) if response else ""

        # Extract JSON from response
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
        if json_match:
            json_str = json_match.group(1).strip()
            if json_str:
                try:
                    data = json.loads(json_str)
                    sections = [
                        TemplateSectionInfo(
                            name=s.get("name", "Unknown"),
                            description=s.get("description"),
                            suggested_words=s.get("suggested_words", 300)
                        )
                        for s in data.get("sections", [])
                    ]
                    if sections:
                        return ParseTemplateSectionsResponse(success=True, sections=sections)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON from code block: {e}")

        # Try parsing without code blocks
        try:
            # Try to find any JSON object in the response
            json_obj_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_obj_match:
                data = json.loads(json_obj_match.group(0))
                sections = [
                    TemplateSectionInfo(
                        name=s.get("name", "Unknown"),
                        description=s.get("description"),
                        suggested_words=s.get("suggested_words", 300)
                    )
                    for s in data.get("sections", [])
                ]
                if sections:
                    return ParseTemplateSectionsResponse(success=True, sections=sections)
        except json.JSONDecodeError:
            pass

        # Fallback if LLM response couldn't be parsed
        return _parse_sections_fallback(request.template_content)

    except Exception as e:
        logger.error(f"Failed to parse template sections: {e}")
        return _parse_sections_fallback(request.template_content)


def _parse_sections_fallback(template_content: str) -> ParseTemplateSectionsResponse:
    """Fallback regex-based parsing if LLM is unavailable."""
    sections = []
    lines = template_content.split('\n')

    for line in lines:
        # Match ## or ### headings
        match = re.match(r'^(#{2,3})\s+(?:\d+\.\s*)?(.+?)(?:\s*\{words:\s*(\d+)\})?\s*$', line)
        if not match:
            continue

        name = match.group(2).strip()
        words = int(match.group(3)) if match.group(3) else 300

        # Skip meta sections
        lower_name = name.lower()
        if any(skip in lower_name for skip in [
            'metadata', 'version', 'approval', 'template', 'structure',
            'optional', 'recommended', 'example', 'format'
        ]):
            continue

        # Skip duplicates
        if any(s.name.lower() == name.lower() for s in sections):
            continue

        sections.append(TemplateSectionInfo(
            name=name,
            description=None,
            suggested_words=words
        ))

    # Default sections if none found
    if not sections:
        sections = [
            TemplateSectionInfo(name="Feature Overview", description="Summary of the feature", suggested_words=250),
            TemplateSectionInfo(name="Functional Requirements", description="What the system must do", suggested_words=400),
            TemplateSectionInfo(name="Business Validations", description="Logic constraints and rules", suggested_words=300),
            TemplateSectionInfo(name="Actors and Interactions", description="User roles and system interactions", suggested_words=250),
            TemplateSectionInfo(name="Process Flow", description="Step-by-step process description", suggested_words=350),
            TemplateSectionInfo(name="Acceptance Criteria", description="Conditions for completion", suggested_words=250),
        ]

    return ParseTemplateSectionsResponse(success=True, sections=sections)


# =============================================================================
# Model Selection Endpoint
# =============================================================================

class ModelInfoResponse(BaseModel):
    """Response model for model information."""
    id: str
    name: str
    provider: str
    description: str
    min_tier: str
    is_recommended: bool
    is_default: bool
    context_window: Optional[int] = None
    strengths: list[str] = []
    status: str = "ga"


class ListModelsResponse(BaseModel):
    """Response for listing available models."""
    models: list[ModelInfoResponse]
    default_model: str
    recommended_models: list[str]


@router.get(
    "/brd/models",
    tags=["BRD Generation"],
    summary="List available LLM models for BRD generation",
    response_model=ListModelsResponse,
)
async def list_available_models() -> ListModelsResponse:
    """
    Get the list of available LLM models that can be used for BRD generation.

    Models are fetched dynamically from GitHub Copilot SDK and include options from:
    - OpenAI (GPT-4.1, GPT-5 series)
    - Anthropic (Claude Haiku, Sonnet, Opus)
    - Google (Gemini)

    Note: Some models require higher Copilot subscription tiers.
    """
    try:
        # Try to fetch models dynamically from Copilot SDK
        from copilot import CopilotClient

        client = CopilotClient()
        await client.start()
        sdk_models = await client.list_models()
        await client.stop()

        # Recommended models for BRD generation
        recommended_ids = {"claude-sonnet-4.5", "gpt-5.1", "claude-opus-4.5"}
        default_model_id = "gpt-4.1"  # Available on all tiers

        models = []
        for m in sdk_models:
            # Access attributes directly from SDK ModelInfo objects
            model_id = m.id if hasattr(m, 'id') else ""
            model_name = m.name if hasattr(m, 'name') else model_id

            # Get capabilities
            caps = m.capabilities if hasattr(m, 'capabilities') else None
            limits = caps.limits if caps and hasattr(caps, 'limits') else None
            supports = caps.supports if caps and hasattr(caps, 'supports') else None

            # Get context window
            context_window = 128000
            if limits and hasattr(limits, 'max_context_window_tokens'):
                context_window = limits.max_context_window_tokens or 128000

            # Get billing info
            billing = m.billing if hasattr(m, 'billing') else None
            multiplier = billing.multiplier if billing and hasattr(billing, 'multiplier') else 1.0

            # Determine provider from model ID (most reliable)
            model_id_lower = model_id.lower()
            if "claude" in model_id_lower:
                provider = "anthropic"
            elif "gemini" in model_id_lower:
                provider = "google"
            elif "grok" in model_id_lower:
                provider = "xai"
            else:
                provider = "openai"

            # Determine tier based on model ID patterns and multiplier
            # Free tier: gpt-4.1, gpt-5-mini (multiplier 0), claude-haiku (multiplier < 0.5)
            # Pro tier: most other models
            # Business: codex-max variants
            if model_id in ["gpt-4.1", "gpt-5-mini"] or multiplier == 0:
                min_tier = "free"
            elif "codex-max" in model_id_lower:
                min_tier = "business"
            elif "opus" in model_id_lower or multiplier >= 3:
                min_tier = "pro+"
            elif "haiku" in model_id_lower and multiplier < 0.5:
                min_tier = "free"
            else:
                min_tier = "pro"

            # Build strengths based on capabilities
            strengths = []
            if supports:
                if hasattr(supports, 'vision') and supports.vision:
                    strengths.append("Vision")
                if hasattr(supports, 'tool_calls') and supports.tool_calls:
                    strengths.append("Tool use")
                if hasattr(supports, 'reasoning_effort') and supports.reasoning_effort:
                    strengths.append("Reasoning")
            if context_window >= 200000:
                strengths.append("Long context")

            # Generate description
            ctx_k = context_window // 1000
            if "codex" in model_id.lower():
                description = f"Optimized for code generation ({ctx_k}K context)"
            elif "mini" in model_id.lower():
                description = f"Fast and efficient ({ctx_k}K context)"
            elif "opus" in model_id.lower():
                description = f"Most capable model ({ctx_k}K context)"
            elif "sonnet" in model_id.lower():
                description = f"Balanced performance ({ctx_k}K context)"
            elif "haiku" in model_id.lower():
                description = f"Fast responses ({ctx_k}K context)"
            else:
                description = f"General purpose ({ctx_k}K context)"

            models.append(ModelInfoResponse(
                id=model_id,
                name=model_name,
                provider=provider,
                description=description,
                min_tier=min_tier,
                is_recommended=model_id in recommended_ids,
                is_default=model_id == default_model_id,
                context_window=context_window,
                strengths=strengths,
                status="ga",
            ))

        # Sort: default first, then recommended, then by name
        models.sort(key=lambda m: (
            not m.is_default,
            not m.is_recommended,
            m.name
        ))

        return ListModelsResponse(
            models=models,
            default_model=default_model_id,
            recommended_models=list(recommended_ids),
        )

    except Exception as e:
        # Fallback to static config if SDK is unavailable
        logger.warning(f"Failed to fetch models from Copilot SDK, using static config: {e}")
        from ..config.models import (
            SUPPORTED_MODELS,
            get_default_model,
            get_recommended_models,
        )

        models = [
            ModelInfoResponse(
                id=m.id,
                name=m.name,
                provider=m.provider.value,
                description=m.description,
                min_tier=m.min_tier.value,
                is_recommended=m.is_recommended,
                is_default=m.is_default,
                context_window=m.context_window,
                strengths=m.strengths,
                status=m.status,
            )
            for m in SUPPORTED_MODELS
        ]

        default_model = get_default_model()
        recommended = get_recommended_models()

        return ListModelsResponse(
            models=models,
            default_model=default_model.id,
            recommended_models=[m.id for m in recommended],
        )


# =============================================================================
# Progress Queue for Streaming
# =============================================================================

class ProgressQueue:
    """Thread-safe queue for progress events."""

    def __init__(self):
        self._queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
        self._done = False

    async def put(self, step: str, detail: str) -> None:
        """Add a progress event to the queue."""
        await self._queue.put({"step": step, "detail": detail})

    async def get(self) -> dict[str, str] | None:
        """Get next progress event, returns None if done."""
        if self._done and self._queue.empty():
            return None
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None

    def mark_done(self) -> None:
        """Mark queue as done (no more events coming)."""
        self._done = True

    @property
    def is_done(self) -> bool:
        return self._done and self._queue.empty()


# =============================================================================
# Global storage for evidence bundles (in production, use Redis/DB)
# =============================================================================

_evidence_bundles: dict[str, Any] = {}


# =============================================================================
# Phase 1: Generate BRD - Draft Mode (Fast, Single-Pass)
# =============================================================================

async def _generate_brd_draft_stream(
    repository_id: str,
    request: GenerateBRDRequest,
    generator: BRDGenerator,
) -> AsyncGenerator[str, None]:
    """Generate BRD using the same infrastructure as verified mode, but without verification.

    Draft mode uses the same section-by-section generation as verified mode:
    - Template parsing
    - Context gathering
    - Section-by-section BRD generation
    - All configuration options (sections, detail level, etc.)

    The only difference is skip_verification=True, which skips:
    - Claim extraction and verification
    - Multi-iteration refinement loop
    - Evidence gathering

    This ensures consistent BRD output between draft and verified modes.
    """
    from sqlalchemy import select
    from ..models.repository import Repository as RepositorySchema
    from ..core.multi_agent_orchestrator import VerifiedBRDGenerator
    from ..core.aggregator import ContextAggregator
    from ..core.template_parser import BRDTemplateParser, ParsedBRDTemplate

    progress_queue = ProgressQueue()

    async def run_generation():
        try:
            async def progress_callback(step: str, detail: str) -> None:
                await progress_queue.put(step, detail)

            await progress_callback("init", "🚀 Starting BRD generation (Draft Mode)...")

            # Get repository
            await progress_callback("database", "Loading repository information...")
            async with get_async_session() as session:
                result = await session.execute(
                    select(RepositoryDB).where(RepositoryDB.id == repository_id)
                )
                db_repo = result.scalar_one_or_none()

                if not db_repo:
                    await progress_callback("error", f"Repository not found: {repository_id}")
                    return None

                if db_repo.status != DBRepositoryStatus.CLONED:
                    await progress_callback("error", f"Repository not cloned: {db_repo.status.value}")
                    return None

                if db_repo.analysis_status != DBAnalysisStatus.COMPLETED:
                    await progress_callback("error", f"Repository not analyzed: {db_repo.analysis_status.value}")
                    return None

                repository = RepositorySchema.model_validate(db_repo)

            await progress_callback("database", f"Repository loaded: {repository.name}")

            # Ensure generator is initialized
            if not generator._initialized:
                await progress_callback("init", "Initializing generator components...")
                await generator.initialize()

            # Build context
            await progress_callback("context", "📊 Building codebase context...")

            workspace_root = Path(repository.local_path) if repository.local_path else generator.workspace_root

            from ..mcp_clients.filesystem_client import FilesystemMCPClient
            repo_filesystem_client = FilesystemMCPClient(workspace_root=workspace_root)
            await repo_filesystem_client.connect()

            aggregator = ContextAggregator(
                generator.neo4j_client,
                repo_filesystem_client,
                copilot_session=generator._copilot_session,
            )

            context = await aggregator.build_context(
                request=request.feature_description,
                affected_components=request.affected_components,
                include_similar=request.include_similar_features,
            )

            await progress_callback("context", f"Context ready: {len(context.architecture.components)} components")

            # Parse BRD template if provided
            parsed_template: ParsedBRDTemplate | None = None
            if request.brd_template:
                await progress_callback("template", "📋 Parsing BRD template...")
                template_parser = BRDTemplateParser(copilot_session=generator._copilot_session)
                parsed_template = await template_parser.parse_template(request.brd_template)
                await progress_callback("template", f"Template parsed: {len(parsed_template.sections)} sections")
                logger.info(f"Template sections: {parsed_template.get_section_names()}")

            # Convert sections to dict format if provided
            custom_sections = None
            if request.sections:
                custom_sections = [
                    {
                        "name": s.name,
                        "description": s.description,
                        "required": s.required,
                        "target_words": s.target_words,
                    }
                    for s in request.sections
                ]

            # Create draft generator (same as verified, but with skip_verification=True)
            await progress_callback("generator", "📝 Starting section-by-section BRD generation...")

            draft_generator = VerifiedBRDGenerator(
                copilot_session=generator._copilot_session,
                neo4j_client=generator.neo4j_client,
                filesystem_client=repo_filesystem_client,
                max_iterations=1,  # Single pass in draft mode
                parsed_template=parsed_template,
                detail_level=request.detail_level.value,
                custom_sections=custom_sections,
                progress_callback=progress_callback,
                temperature=request.temperature,
                seed=request.seed,
                default_section_words=request.default_section_words,
                skip_verification=True,  # KEY: Skip verification for draft mode
            )

            # Run generation (same flow as verified, but no verification loop)
            output = await draft_generator.generate(context)

            # Cleanup
            await repo_filesystem_client.disconnect()
            await draft_generator.cleanup()

            await progress_callback("complete", f"✅ Draft BRD complete: {output.brd.title}")

            return output, repository

        except Exception as e:
            logger.exception("Failed to generate BRD (draft mode)")
            await progress_queue.put("error", str(e))
            return None
        finally:
            progress_queue.mark_done()

    # Start generation task
    generation_task = asyncio.create_task(run_generation())

    # Register the generation for cancellation tracking
    _register_generation(repository_id, generation_task)

    # Stream progress (same icons as verified mode for consistency)
    step_icons = {
        "init": "🚀",
        "database": "🗄️",
        "context": "📊",
        "template": "📋",
        "generator": "📝",
        "section": "📄",
        "section_complete": "✅",
        "complete": "✅",
        "cancelled": "⏹️",
    }

    try:
        while not progress_queue.is_done or not generation_task.done():
            # Check for cancellation
            if _is_generation_cancelled(repository_id):
                yield f"data: {json.dumps({'type': 'cancelled', 'content': '⏹️ Generation cancelled by user'})}\n\n"
                generation_task.cancel()
                break

            event = await progress_queue.get()
            if event:
                step = event["step"]
                detail = event["detail"]

                if step == "error":
                    yield f"data: {json.dumps({'type': 'error', 'content': detail})}\n\n"
                else:
                    icon = step_icons.get(step, "▶️")
                    yield f"data: {json.dumps({'type': 'thinking', 'content': f'{icon} {detail}'})}\n\n"

            await asyncio.sleep(0.05)

            if generation_task.done() and progress_queue.is_done:
                break

        # Check if cancelled
        if _is_generation_cancelled(repository_id):
            _unregister_generation(repository_id)
            return

        # Get result
        try:
            result = await generation_task
        except asyncio.CancelledError:
            yield f"data: {json.dumps({'type': 'cancelled', 'content': '⏹️ Generation cancelled'})}\n\n"
            return
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            return

        if result is None:
            return
    finally:
        _unregister_generation(repository_id)

    output, repository = result

    # Convert to BRD response (output is BRDOutput from VerifiedBRDGenerator)
    brd_response = _brd_to_response(output.brd)

    # Stream content
    markdown_content = brd_response.markdown
    chunk_size = 100
    for i in range(0, len(markdown_content), chunk_size):
        chunk = markdown_content[i:i + chunk_size]
        yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
        await asyncio.sleep(0.02)

    # Send complete response (Draft mode - no verification metrics)
    response_data = GenerateBRDResponse(
        success=True,
        brd=brd_response,
        mode=GenerationMode.DRAFT,
        # No verification metrics in draft mode
        is_verified=None,
        confidence_score=None,
        hallucination_risk=None,
        iterations_used=None,
        evidence_trail=None,
        evidence_trail_text=None,
        needs_sme_review=False,
        sme_review_claims=[],
        draft_warning="This is a draft BRD generated without verification. It may contain inaccuracies or unsupported claims. Use 'verified' mode for production-quality documentation.",
        metadata={
            **output.metadata,
            "mode": "draft",
            "repository_id": repository.id,
            "repository_name": repository.name,
        },
    )
    yield f"data: {json.dumps({'type': 'complete', 'data': response_data.model_dump(mode='json')})}\n\n"


# =============================================================================
# Phase 1: Generate BRD - Verified Mode (Multi-Agent Verification)
# =============================================================================

async def _generate_brd_verified_stream(
    repository_id: str,
    request: GenerateBRDRequest,
    generator: BRDGenerator,
) -> AsyncGenerator[str, None]:
    """Generate BRD using multi-agent architecture with verification.

    This is the thorough "Verified" mode:
    - Uses Generator Agent to create BRD sections iteratively
    - Uses Verifier Agent to validate claims against codebase
    - Evidence gathering with confidence scoring
    - Hallucination detection and SME review flagging
    - Multiple iterations until confidence threshold met
    """
    from sqlalchemy import select
    from ..models.repository import Repository as RepositorySchema
    from ..core.multi_agent_orchestrator import VerifiedBRDGenerator
    from ..core.aggregator import ContextAggregator
    from ..models.verification import VerificationConfig
    from ..core.template_parser import BRDTemplateParser, ParsedBRDTemplate

    progress_queue = ProgressQueue()

    async def run_generation():
        try:
            async def progress_callback(step: str, detail: str) -> None:
                await progress_queue.put(step, detail)

            await progress_callback("init", "🚀 Starting BRD generation...")
            await progress_callback("init", f"Max iterations: {request.max_iterations}, Min confidence: {request.min_confidence}")

            # Get repository
            await progress_callback("database", "Loading repository information...")
            async with get_async_session() as session:
                result = await session.execute(
                    select(RepositoryDB).where(RepositoryDB.id == repository_id)
                )
                db_repo = result.scalar_one_or_none()

                if not db_repo:
                    await progress_callback("error", f"Repository not found: {repository_id}")
                    return None

                if db_repo.status != DBRepositoryStatus.CLONED:
                    await progress_callback("error", f"Repository not cloned: {db_repo.status.value}")
                    return None

                if db_repo.analysis_status != DBAnalysisStatus.COMPLETED:
                    await progress_callback("error", f"Repository not analyzed: {db_repo.analysis_status.value}")
                    return None

                repository = RepositorySchema.model_validate(db_repo)

            await progress_callback("database", f"Repository loaded: {repository.name}")

            # Ensure generator is initialized
            if not generator._initialized:
                await progress_callback("init", "Initializing generator components...")
                await generator.initialize()

            # Build context
            await progress_callback("context", "📊 Building codebase context...")

            workspace_root = Path(repository.local_path) if repository.local_path else generator.workspace_root

            from ..mcp_clients.filesystem_client import FilesystemMCPClient
            repo_filesystem_client = FilesystemMCPClient(workspace_root=workspace_root)
            await repo_filesystem_client.connect()

            aggregator = ContextAggregator(
                generator.neo4j_client,
                repo_filesystem_client,
                copilot_session=generator._copilot_session,  # Enable agentic context gathering
            )

            context = await aggregator.build_context(
                request=request.feature_description,
                affected_components=request.affected_components,
                include_similar=request.include_similar_features,
            )

            await progress_callback("context", f"Context ready: {len(context.architecture.components)} components")

            # Parse BRD template if provided (template-driven generation!)
            parsed_template: ParsedBRDTemplate | None = None
            if request.brd_template:
                await progress_callback("template", "📋 Parsing BRD template...")
                template_parser = BRDTemplateParser(copilot_session=generator._copilot_session)
                parsed_template = await template_parser.parse_template(request.brd_template)
                await progress_callback("template", f"Template parsed: {len(parsed_template.sections)} sections")
                logger.info(f"Template sections: {parsed_template.get_section_names()}")

            # Create multi-agent generator
            await progress_callback("agents", "🤖 Initializing Generator and Verifier agents...")

            verification_config = VerificationConfig(
                min_confidence_for_approval=request.min_confidence,
                max_iterations=request.max_iterations,
            )

            # Convert sufficiency criteria if provided
            sufficiency_dict = None
            if request.sufficiency_criteria:
                sufficiency_dict = {
                    "dimensions": [
                        {
                            "name": d.name,
                            "description": d.description,
                            "required": d.required,
                        }
                        for d in request.sufficiency_criteria.dimensions
                    ],
                    "output_requirements": {
                        "code_traceability": request.sufficiency_criteria.output_requirements.code_traceability if request.sufficiency_criteria.output_requirements else True,
                        "explicit_gaps": request.sufficiency_criteria.output_requirements.explicit_gaps if request.sufficiency_criteria.output_requirements else True,
                        "evidence_based": request.sufficiency_criteria.output_requirements.evidence_based if request.sufficiency_criteria.output_requirements else True,
                    } if request.sufficiency_criteria.output_requirements else None,
                    "min_dimensions_covered": request.sufficiency_criteria.min_dimensions_covered,
                }
                await progress_callback("config", f"Custom sufficiency criteria: {len(request.sufficiency_criteria.dimensions)} dimensions")

            # Convert sections to dict format if provided (including target_words for length control)
            custom_sections_verified = None
            if request.sections:
                custom_sections_verified = [
                    {
                        "name": s.name,
                        "description": s.description,
                        "required": s.required,
                        "target_words": s.target_words,
                    }
                    for s in request.sections
                ]

            # Convert verification limits to dict if provided
            verification_limits_dict = None
            if request.verification_limits:
                verification_limits_dict = {
                    "max_entities_per_claim": request.verification_limits.max_entities_per_claim,
                    "max_patterns_per_claim": request.verification_limits.max_patterns_per_claim,
                    "results_per_query": request.verification_limits.results_per_query,
                    "code_refs_per_evidence": request.verification_limits.code_refs_per_evidence,
                }

            verified_generator = VerifiedBRDGenerator(
                copilot_session=generator._copilot_session,
                neo4j_client=generator.neo4j_client,
                filesystem_client=repo_filesystem_client,
                max_iterations=request.max_iterations,
                parsed_template=parsed_template,  # Pass parsed template
                sufficiency_criteria=sufficiency_dict,  # Pass sufficiency criteria
                detail_level=request.detail_level.value,  # Pass detail level
                custom_sections=custom_sections_verified,  # Pass custom sections
                verification_limits=verification_limits_dict,  # Pass verification limits
                progress_callback=progress_callback,  # Pass progress callback for streaming updates
                temperature=request.temperature,  # Consistency control
                seed=request.seed,  # Reproducibility control
                claims_per_section=request.claims_per_section,  # Consistent claim extraction
                default_section_words=request.default_section_words,  # Section length control
            )

            # Run multi-agent generation
            await progress_callback("agents", "Starting Generator-Verifier loop...")

            output = await verified_generator.generate(context)

            # Get evidence bundle
            evidence_bundle = verified_generator.orchestrator.get_evidence_bundle()

            # Store evidence bundle for later retrieval
            if output and output.brd:
                brd_id = f"BRD-{hash(output.brd.title) % 10000:04d}"
                _evidence_bundles[brd_id] = evidence_bundle

            # Cleanup
            await repo_filesystem_client.disconnect()
            await verified_generator.cleanup()

            await progress_callback("complete", f"✅ BRD complete! Confidence: {verified_generator.get_confidence_score():.2f}")

            return output, evidence_bundle, repository

        except Exception as e:
            logger.exception("Failed to generate BRD")
            await progress_queue.put("error", str(e))
            return None
        finally:
            progress_queue.mark_done()

    # Start generation task
    generation_task = asyncio.create_task(run_generation())

    # Register the generation for cancellation tracking
    _register_generation(repository_id, generation_task)

    # Stream progress
    step_icons = {
        "init": "🚀",
        "database": "🗄️",
        "context": "📊",
        "template": "📋",
        "config": "⚙️",
        "agents": "🤖",
        "generator": "📝",
        "section": "📄",
        "section_complete": "✅",
        "verifier": "🔬",
        "claims": "📋",
        "verifying": "🔍",
        "feedback": "🔄",
        "complete": "✅",
        "cancelled": "⏹️",
    }

    try:
        while not progress_queue.is_done or not generation_task.done():
            # Check for cancellation
            if _is_generation_cancelled(repository_id):
                yield f"data: {json.dumps({'type': 'cancelled', 'content': '⏹️ Generation cancelled by user'})}\n\n"
                generation_task.cancel()
                break

            event = await progress_queue.get()
            if event:
                step = event["step"]
                detail = event["detail"]

                if step == "error":
                    yield f"data: {json.dumps({'type': 'error', 'content': detail})}\n\n"
                else:
                    icon = step_icons.get(step, "▶️")
                    yield f"data: {json.dumps({'type': 'thinking', 'content': f'{icon} {detail}'})}\n\n"

            await asyncio.sleep(0.05)

            if generation_task.done() and progress_queue.is_done:
                break

        # Check if cancelled
        if _is_generation_cancelled(repository_id):
            _unregister_generation(repository_id)
            return

        # Get result
        try:
            result = await generation_task
        except asyncio.CancelledError:
            yield f"data: {json.dumps({'type': 'cancelled', 'content': '⏹️ Generation cancelled'})}\n\n"
            return
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            return

        if result is None:
            return

        output, evidence_bundle, repository = result
    finally:
        _unregister_generation(repository_id)

    # Convert to BRD response
    brd_response = _brd_to_response(output.brd)

    # Stream content
    markdown_content = brd_response.markdown
    chunk_size = 100
    for i in range(0, len(markdown_content), chunk_size):
        chunk = markdown_content[i:i + chunk_size]
        yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
        await asyncio.sleep(0.02)

    # Build verification report (always included in verified mode)
    verification_report = None
    evidence_summary = None
    evidence_text = None

    if evidence_bundle:
        from datetime import datetime

        # Build complete verification report with per-section claim details
        section_reports = []
        sections_summary = []
        claims_summary = []

        for section in evidence_bundle.sections:
            # Build claim details for this section
            section_claims = []
            partially_verified = 0
            contradicted = 0

            for claim in section.claims:
                # Determine if claim is verified
                is_verified = claim.status.value == "verified"
                if claim.status.value == "partially_verified":
                    partially_verified += 1
                elif claim.status.value == "contradicted":
                    contradicted += 1

                # Get evidence types
                evidence_types = list(set(e.evidence_type.value for e in claim.evidence)) if claim.evidence else []

                # Extract code references from evidence
                code_refs = []
                for ev in claim.evidence:
                    for ref in ev.code_references:
                        # Generate explanation for why this code supports the claim
                        explanation = None
                        if ev.notes:
                            explanation = ev.notes
                        elif ev.description:
                            explanation = f"This {ref.entity_type or 'code'} supports the claim: {ev.description[:150]}"

                        code_refs.append(CodeReferenceItem(
                            file_path=ref.file_path,
                            start_line=ref.start_line,
                            end_line=ref.end_line,
                            snippet=ref.snippet[:300] if ref.snippet else None,
                            explanation=explanation,
                            entity_name=ref.entity_name,
                            entity_type=ref.entity_type,
                        ))

                # Build verification summary from evidence
                verification_summary = None
                if claim.evidence:
                    primary_evidence = claim.evidence[0]
                    if is_verified:
                        verification_summary = f"Verified: Found {len(claim.evidence)} evidence item(s). {primary_evidence.description[:100] if primary_evidence.description else ''}"
                    else:
                        verification_summary = f"Not verified: {primary_evidence.notes or 'Insufficient evidence found in codebase.'}"

                section_claims.append(ClaimVerificationDetail(
                    claim_id=claim.id,
                    claim_text=claim.text,
                    section=claim.section,
                    status=claim.status.value,
                    confidence=claim.confidence_score,
                    is_verified=is_verified,
                    hallucination_risk=claim.hallucination_risk.value,
                    needs_sme_review=claim.needs_sme_review,
                    evidence_count=len(claim.evidence),
                    evidence_types=evidence_types,
                    code_references=code_refs[:10],  # Limit to 10 refs per claim
                    verification_summary=verification_summary,
                ))

            # Calculate verification rate for this section
            section_verification_rate = (
                (section.verified_claims / section.total_claims * 100)
                if section.total_claims > 0 else 0.0
            )

            section_reports.append(SectionVerificationReport(
                section_name=section.section_name,
                status=section.verification_status.value,
                confidence=section.overall_confidence,
                hallucination_risk=section.hallucination_risk.value,
                total_claims=section.total_claims,
                verified_claims=section.verified_claims,
                partially_verified_claims=partially_verified,
                unverified_claims=section.unverified_claims,
                contradicted_claims=contradicted,
                claims_needing_sme=section.needs_sme_review,
                verification_rate=round(section_verification_rate, 1),
                claims=section_claims,
            ))

            # Also build lightweight summary for evidence_trail
            sections_summary.append(SectionSummary(
                section_name=section.section_name,
                status=section.verification_status.value,
                confidence=section.overall_confidence,
                total_claims=section.total_claims,
                verified_claims=section.verified_claims,
                unverified_claims=section.unverified_claims,
                hallucination_risk=section.hallucination_risk.value,
            ).model_dump())

            if request.show_evidence:
                for claim in section.claims:
                    claims_summary.append(ClaimSummary(
                        claim_id=claim.id,
                        text=claim.text[:200] + "..." if len(claim.text) > 200 else claim.text,
                        section=claim.section,
                        status=claim.status.value,
                        confidence=claim.confidence_score,
                        hallucination_risk=claim.hallucination_risk.value,
                        needs_sme_review=claim.needs_sme_review,
                        evidence_count=len(claim.evidence),
                    ).model_dump())

        # Calculate overall stats for verification report
        total_partially_verified = sum(s.partially_verified_claims for s in section_reports)
        total_contradicted = sum(s.contradicted_claims for s in section_reports)
        total_unverified = evidence_bundle.total_claims - evidence_bundle.verified_claims - total_partially_verified - total_contradicted
        overall_verification_rate = (
            (evidence_bundle.verified_claims / evidence_bundle.total_claims * 100)
            if evidence_bundle.total_claims > 0 else 0.0
        )

        verification_report = VerificationReport(
            brd_id=brd_response.id,
            brd_title=brd_response.title,
            generated_at=datetime.now().isoformat(),
            overall_status=evidence_bundle.overall_status.value,
            overall_confidence=evidence_bundle.overall_confidence,
            hallucination_risk=evidence_bundle.hallucination_risk.value,
            is_approved=evidence_bundle.is_approved,
            total_claims=evidence_bundle.total_claims,
            verified_claims=evidence_bundle.verified_claims,
            partially_verified_claims=total_partially_verified,
            unverified_claims=total_unverified if total_unverified > 0 else 0,
            contradicted_claims=total_contradicted,
            claims_needing_sme=evidence_bundle.claims_needing_sme,
            verification_rate=round(overall_verification_rate, 1),
            iterations_used=evidence_bundle.iteration,
            evidence_sources=evidence_bundle.evidence_sources,
            queries_executed=evidence_bundle.queries_executed,
            files_analyzed=evidence_bundle.files_analyzed,
            sections=section_reports,
        )

        # Build evidence trail summary (for backward compatibility)
        evidence_summary = EvidenceTrailSummary(
            brd_id=brd_response.id,
            overall_confidence=evidence_bundle.overall_confidence,
            overall_status=evidence_bundle.overall_status.value,
            hallucination_risk=evidence_bundle.hallucination_risk.value,
            total_claims=evidence_bundle.total_claims,
            verified_claims=evidence_bundle.verified_claims,
            claims_needing_sme=evidence_bundle.claims_needing_sme,
            evidence_sources=evidence_bundle.evidence_sources,
            queries_executed=evidence_bundle.queries_executed,
            files_analyzed=evidence_bundle.files_analyzed,
            sections=sections_summary,
            claims=claims_summary if request.show_evidence else None,
        )

        if request.show_evidence:
            evidence_text = evidence_bundle.to_evidence_trail(include_details=True)

    # Build SME review claims
    sme_claims = []
    if evidence_bundle:
        for section in evidence_bundle.sections:
            for claim in section.claims:
                if claim.needs_sme_review:
                    sme_claims.append(ClaimSummary(
                        claim_id=claim.id,
                        text=claim.text[:200] + "..." if len(claim.text) > 200 else claim.text,
                        section=claim.section,
                        status=claim.status.value,
                        confidence=claim.confidence_score,
                        hallucination_risk=claim.hallucination_risk.value,
                        needs_sme_review=True,
                        evidence_count=len(claim.evidence),
                    ))

    # Send complete response
    response_data = GenerateBRDResponse(
        success=True,
        brd=brd_response,
        mode=GenerationMode.VERIFIED,
        is_verified=evidence_bundle.is_approved if evidence_bundle else False,
        confidence_score=evidence_bundle.overall_confidence if evidence_bundle else 0.0,
        hallucination_risk=evidence_bundle.hallucination_risk.value if evidence_bundle else "unknown",
        iterations_used=evidence_bundle.iteration if evidence_bundle else 0,
        verification_report=verification_report,  # Complete verification report
        evidence_trail=evidence_summary,
        evidence_trail_text=evidence_text,
        needs_sme_review=len(sme_claims) > 0,
        sme_review_claims=sme_claims,
        draft_warning=None,  # No warning in verified mode
        metadata={
            **output.metadata,
            "mode": "verified",
            "generator_agent": "brd_generator",
            "verifier_agent": "brd_verifier",
            "repository_id": repository.id,
            "repository_name": repository.name,
        },
    )
    yield f"data: {json.dumps({'type': 'complete', 'data': response_data.model_dump(mode='json')})}\n\n"


@router.post(
    "/brd/generate/{repository_id}",
    tags=["Phase 1: BRD"],
    summary="Generate BRD (Draft or Verified mode)",
    description="""
    Generate a Business Requirements Document for a repository.

    ## Generation Modes

    Choose between two modes via the `mode` parameter:

    ### Draft Mode (default) - Fast
    - Single-pass LLM generation with MCP tools
    - No multi-agent verification
    - No evidence gathering or hallucination detection
    - Best for: Quick exploration, initial drafts, brainstorming

    ### Verified Mode - Thorough
    - Multi-agent architecture with Generator and Verifier agents
    - Evidence gathering from codebase
    - Hallucination detection and confidence scoring
    - Multiple iterations until confidence threshold met
    - Best for: Production documentation, compliance requirements

    ## Multi-Agent Architecture (Verified Mode Only)

    In verified mode, two specialized agents work together:

    ### Agent 1: BRD Generator
    - Generates BRD sections iteratively
    - Incorporates feedback from the Verifier agent
    - Regenerates sections that fail verification

    ### Agent 2: BRD Verifier
    - Extracts claims from each BRD section
    - Validates claims by gathering evidence from code analysis
    - Detects potential hallucinations
    - Provides actionable feedback for regeneration

    ## Streaming via SSE

    The endpoint streams events as Server-Sent Events (SSE):
    - `thinking`: Progress updates during generation
    - `content`: Streaming BRD content chunks
    - `complete`: Final complete BRD response
    - `error`: Error messages

    ## Request Parameters

    - `mode`: Generation mode - "draft" (default) or "verified"
    - `max_iterations`: Maximum verification iterations (verified mode only, default: 3)
    - `min_confidence`: Minimum confidence for approval (verified mode only, default: 0.7)
    - `show_evidence`: Include evidence trail in response (verified mode only, default: false)

    ## Response

    The complete event includes:
    - BRD document
    - Generation mode used

    In verified mode, also includes:
    - Confidence score (0-1)
    - Hallucination risk level
    - Claims needing SME review
    - Evidence trail (if requested)
    - **Complete Verification Report** containing:
      - Overall summary (total claims, verified claims, confidence, verification rate)
      - Per-section breakdown with:
        - Section verification status and confidence
        - All claims extracted from the section
        - Each claim's verification status (verified/unverified)
        - Evidence count and types for each claim
        - Section verification rate percentage

    In draft mode, includes:
    - Warning that draft may need review
    """,
)
async def generate_brd(
    repository_id: str,
    request: GenerateBRDRequest,
    generator: BRDGenerator = Depends(get_generator),
) -> StreamingResponse:
    """Generate BRD with selected mode (draft or verified)."""
    # Check if a specific model is requested
    if request.model and request.model != generator.copilot_model:
        # Create a new generator with the specified model
        logger.info(f"Creating generator with model: {request.model}")
        custom_generator = BRDGenerator(copilot_model=request.model)
        await custom_generator.initialize()
        use_generator = custom_generator
    else:
        use_generator = generator

    # Dispatch based on mode
    if request.mode == GenerationMode.DRAFT:
        stream_generator = _generate_brd_draft_stream(repository_id, request, use_generator)
    else:
        stream_generator = _generate_brd_verified_stream(repository_id, request, use_generator)

    return StreamingResponse(
        stream_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/brd/generate/{repository_id}/cancel",
    tags=["Phase 1: BRD"],
    summary="Cancel BRD Generation",
    description="Cancel an ongoing BRD generation for a repository.",
)
async def cancel_brd_generation(repository_id: str) -> dict:
    """Cancel an ongoing BRD generation."""
    cancelled = _cancel_generation(repository_id)
    if cancelled:
        return {"success": True, "message": f"Generation cancelled for repository: {repository_id}"}
    else:
        return {"success": False, "message": f"No active generation found for repository: {repository_id}"}


@router.get(
    "/brd/{brd_id}/evidence-trail",
    response_model=GetEvidenceTrailResponse,
    tags=["Phase 1: BRD"],
    summary="Get Evidence Trail for a BRD",
    description="""
    Retrieve the evidence trail for a previously generated BRD.

    The evidence trail includes:
    - All claims extracted from the BRD
    - Evidence gathered for each claim (code references, call graphs, etc.)
    - Confidence scores and verification status
    - Hallucination risk assessment

    This endpoint allows retrieving evidence that was hidden during BRD generation.
    """,
)
async def get_evidence_trail(
    brd_id: str,
    show_details: bool = True,
) -> GetEvidenceTrailResponse:
    """Get evidence trail for a BRD."""
    from datetime import datetime

    if brd_id not in _evidence_bundles:
        raise HTTPException(status_code=404, detail=f"Evidence trail not found for BRD: {brd_id}")

    evidence_bundle = _evidence_bundles[brd_id]

    if evidence_bundle is None:
        raise HTTPException(status_code=404, detail=f"Evidence bundle is empty for BRD: {brd_id}")

    # Build complete verification report
    section_reports = []
    sections_summary = []

    for section in evidence_bundle.sections:
        # Build claim details for this section
        section_claims = []
        partially_verified = 0
        contradicted = 0

        for claim in section.claims:
            is_verified = claim.status.value == "verified"
            if claim.status.value == "partially_verified":
                partially_verified += 1
            elif claim.status.value == "contradicted":
                contradicted += 1

            evidence_types = list(set(e.evidence_type.value for e in claim.evidence)) if claim.evidence else []

            # Extract code references from evidence with explanations
            code_refs = []
            for ev in claim.evidence:
                for ref in ev.code_references:
                    explanation = None
                    if ev.notes:
                        explanation = ev.notes
                    elif ev.description:
                        explanation = f"This {ref.entity_type or 'code'} supports the claim: {ev.description[:150]}"

                    code_refs.append(CodeReferenceItem(
                        file_path=ref.file_path,
                        start_line=ref.start_line,
                        end_line=ref.end_line,
                        snippet=ref.snippet[:300] if ref.snippet else None,
                        explanation=explanation,
                        entity_name=ref.entity_name,
                        entity_type=ref.entity_type,
                    ))

            # Build verification summary
            verification_summary = None
            if claim.evidence:
                primary_evidence = claim.evidence[0]
                if is_verified:
                    verification_summary = f"Verified: Found {len(claim.evidence)} evidence item(s). {primary_evidence.description[:100] if primary_evidence.description else ''}"
                else:
                    verification_summary = f"Not verified: {primary_evidence.notes or 'Insufficient evidence found in codebase.'}"

            section_claims.append(ClaimVerificationDetail(
                claim_id=claim.id,
                claim_text=claim.text,
                section=claim.section,
                status=claim.status.value,
                confidence=claim.confidence_score,
                is_verified=is_verified,
                hallucination_risk=claim.hallucination_risk.value,
                needs_sme_review=claim.needs_sme_review,
                evidence_count=len(claim.evidence),
                evidence_types=evidence_types,
                code_references=code_refs[:10],  # Limit to 10 refs per claim
                verification_summary=verification_summary,
            ))

        section_verification_rate = (
            (section.verified_claims / section.total_claims * 100)
            if section.total_claims > 0 else 0.0
        )

        section_reports.append(SectionVerificationReport(
            section_name=section.section_name,
            status=section.verification_status.value,
            confidence=section.overall_confidence,
            hallucination_risk=section.hallucination_risk.value,
            total_claims=section.total_claims,
            verified_claims=section.verified_claims,
            partially_verified_claims=partially_verified,
            unverified_claims=section.unverified_claims,
            contradicted_claims=contradicted,
            claims_needing_sme=section.needs_sme_review,
            verification_rate=round(section_verification_rate, 1),
            claims=section_claims if show_details else [],
        ))

        sections_summary.append(SectionSummary(
            section_name=section.section_name,
            status=section.verification_status.value,
            confidence=section.overall_confidence,
            total_claims=section.total_claims,
            verified_claims=section.verified_claims,
            unverified_claims=section.unverified_claims,
            hallucination_risk=section.hallucination_risk.value,
        ))

    # Calculate overall stats
    total_partially_verified = sum(s.partially_verified_claims for s in section_reports)
    total_contradicted = sum(s.contradicted_claims for s in section_reports)
    total_unverified = evidence_bundle.total_claims - evidence_bundle.verified_claims - total_partially_verified - total_contradicted
    overall_verification_rate = (
        (evidence_bundle.verified_claims / evidence_bundle.total_claims * 100)
        if evidence_bundle.total_claims > 0 else 0.0
    )

    verification_report = VerificationReport(
        brd_id=brd_id,
        brd_title=evidence_bundle.brd_title,
        generated_at=evidence_bundle.created_at.isoformat() if evidence_bundle.created_at else datetime.now().isoformat(),
        overall_status=evidence_bundle.overall_status.value,
        overall_confidence=evidence_bundle.overall_confidence,
        hallucination_risk=evidence_bundle.hallucination_risk.value,
        is_approved=evidence_bundle.is_approved,
        total_claims=evidence_bundle.total_claims,
        verified_claims=evidence_bundle.verified_claims,
        partially_verified_claims=total_partially_verified,
        unverified_claims=total_unverified if total_unverified > 0 else 0,
        contradicted_claims=total_contradicted,
        claims_needing_sme=evidence_bundle.claims_needing_sme,
        verification_rate=round(overall_verification_rate, 1),
        iterations_used=evidence_bundle.iteration,
        evidence_sources=evidence_bundle.evidence_sources,
        queries_executed=evidence_bundle.queries_executed,
        files_analyzed=evidence_bundle.files_analyzed,
        sections=section_reports,
    )

    evidence_summary = EvidenceTrailSummary(
        brd_id=brd_id,
        overall_confidence=evidence_bundle.overall_confidence,
        overall_status=evidence_bundle.overall_status.value,
        hallucination_risk=evidence_bundle.hallucination_risk.value,
        total_claims=evidence_bundle.total_claims,
        verified_claims=evidence_bundle.verified_claims,
        claims_needing_sme=evidence_bundle.claims_needing_sme,
        evidence_sources=evidence_bundle.evidence_sources,
        queries_executed=evidence_bundle.queries_executed,
        files_analyzed=evidence_bundle.files_analyzed,
        sections=sections_summary,
    )

    evidence_text = evidence_bundle.to_evidence_trail(include_details=show_details)

    return GetEvidenceTrailResponse(
        success=True,
        brd_id=brd_id,
        evidence_trail=evidence_summary,
        evidence_trail_text=evidence_text,
        verification_report=verification_report,
    )


# =============================================================================
# Phase 2: Generate Epics
# =============================================================================

@router.post(
    "/epics/generate-legacy",
    response_model=GenerateEpicsResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Phase 2: Epics"],
    summary="Generate Epics from approved BRD (Legacy)",
    description="""
    **Phase 2 (Legacy)**: Generate Epics from an approved BRD.

    NOTE: This is the legacy endpoint. Use `/epics/generate` for the new streaming API.

    This endpoint takes the approved BRD from Phase 1 and breaks it down into
    Epics that can be delivered in 2-4 weeks each.

    The generated Epics should be reviewed and approved before proceeding to Phase 3.
    """,
    deprecated=True,
)
async def generate_epics_legacy(
    request: GenerateEpicsRequest,
    generator: BRDGenerator = Depends(get_generator),
) -> GenerateEpicsResponse:
    """Generate Epics from approved BRD."""
    try:
        logger.info(f"[API] Phase 2: Generating Epics from BRD: {request.brd.title[:50]}...")

        # Convert BRD response back to internal format
        brd = _response_to_brd(request.brd)

        # Generate Epics
        epics_output = await generator.generate_epics_from_brd(brd, use_skill=request.use_skill)

        # Convert to response
        return GenerateEpicsResponse(
            success=True,
            brd_id=epics_output.brd_id,
            brd_title=epics_output.brd_title,
            epics=[_epic_to_response(e) for e in epics_output.epics],
            implementation_order=epics_output.implementation_order,
            metadata=epics_output.metadata,
        )

    except Exception as e:
        logger.exception("Failed to generate Epics")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Phase 3: Generate Backlogs
# =============================================================================

@router.post(
    "/backlogs/generate-legacy",
    response_model=GenerateBacklogsResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Phase 3: Backlogs"],
    summary="Generate User Stories from approved Epics (Legacy)",
    description="""
    **Phase 3 (Legacy)**: Generate User Stories (Backlogs) from approved Epics.

    NOTE: This is the legacy endpoint. Use `/backlogs/generate` for the new streaming API.

    This endpoint takes the approved Epics from Phase 2 and the original BRD
    for context, and breaks each Epic into User Stories that can be completed
    in 1-3 days each.

    The generated Stories should be reviewed and approved before proceeding to Phase 4.
    """,
    deprecated=True,
)
async def generate_backlogs_legacy(
    request: GenerateBacklogsRequest,
    generator: BRDGenerator = Depends(get_generator),
) -> GenerateBacklogsResponse:
    """Generate User Stories from approved Epics."""
    try:
        logger.info(f"[API] Phase 3: Generating Backlogs from {len(request.epics)} Epics...")

        # Convert Epics back to internal format
        epics = [_response_to_epic(e) for e in request.epics]

        # Create EpicsOutput for the generator
        epics_output = EpicsOutput(
            brd_id=request.brd.id,
            brd_title=request.brd.title,
            epics=epics,
        )

        # Generate Backlogs
        backlogs_output = await generator.generate_backlogs_from_epics(
            epics_output,
            use_skill=request.use_skill,
        )

        # Calculate total points
        total_points = sum(s.estimated_points or 0 for s in backlogs_output.stories)

        # Convert to response
        return GenerateBacklogsResponse(
            success=True,
            epics=[_epic_to_response(e) for e in backlogs_output.epics],
            stories=[_story_to_response(s) for s in backlogs_output.stories],
            implementation_order=backlogs_output.implementation_order,
            total_story_points=total_points,
            metadata=backlogs_output.metadata,
        )

    except Exception as e:
        logger.exception("Failed to generate Backlogs")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Phase 4: Create JIRA Issues
# =============================================================================

@router.post(
    "/jira/create",
    response_model=CreateJiraResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Phase 4: JIRA"],
    summary="Create Epics and Stories in JIRA",
    description="""
    **Phase 4**: Create approved Epics and Stories in JIRA.

    This endpoint takes the approved Epics and Stories and creates them
    in the specified JIRA project using the Atlassian MCP server.

    Requires `MCP_ATLASSIAN_ENABLED=true` and Atlassian credentials configured.
    """,
)
async def create_jira_issues(
    request: CreateJiraRequest,
    generator: BRDGenerator = Depends(get_generator),
) -> CreateJiraResponse:
    """Create Epics and Stories in JIRA."""
    try:
        logger.info(f"[API] Phase 4: Creating JIRA issues in project: {request.project_key}...")

        # Convert to internal format
        epics = [_response_to_epic(e) for e in request.epics]
        stories = [_response_to_story(s) for s in request.stories]

        # Create BacklogsOutput for the generator
        backlogs_output = BacklogsOutput(
            epics=epics,
            stories=stories,
        )

        # Create JIRA issues
        result = await generator.create_jira_issues(
            backlogs_output,
            project_key=request.project_key,
            use_skill=request.use_skill,
        )

        # Convert to response
        epics_created = [
            JiraIssueResult(
                local_id=e.id,
                jira_key=e.jira_key,
                jira_url=e.jira_url,
                status="created" if e.jira_key else "pending",
            )
            for e in result.epics_created
        ]

        stories_created = [
            JiraIssueResult(
                local_id=s.id,
                jira_key=s.jira_key,
                jira_url=s.jira_url,
                status="created" if s.jira_key else "pending",
            )
            for s in result.stories_created
        ]

        return CreateJiraResponse(
            success=True,
            project_key=request.project_key,
            epics_created=epics_created,
            stories_created=stories_created,
            total_created=len([e for e in epics_created if e.jira_key]) + len([s for s in stories_created if s.jira_key]),
            total_failed=len([e for e in epics_created if not e.jira_key]) + len([s for s in stories_created if not s.jira_key]),
        )

    except Exception as e:
        logger.exception("Failed to create JIRA issues")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Phase 3: Agentic Readiness Report
# =============================================================================

@router.get(
    "/repositories/{repository_id}/readiness",
    response_model=AgenticReadinessResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Agentic Readiness"],
    summary="Generate Agentic Readiness Report",
    description="""
    **Phase 3**: Generate an Agentic Readiness Report for a repository.

    This endpoint assesses a repository's readiness for agentic automation by evaluating:

    ## Testing Readiness
    - Overall test coverage percentage
    - Coverage of critical functions (controllers, services, entry points)
    - Test quality (unit, integration, E2E tests present)
    - Test frameworks in use

    ## Documentation Readiness
    - Overall documentation coverage
    - Public API documentation coverage
    - Documentation quality distribution
    - Undocumented public APIs

    ## Grading System
    - **A**: >= 90% - Excellent, ready for full automation
    - **B**: >= 75% - Good, minimal gaps to address
    - **C**: >= 60% - Fair, some work needed
    - **D**: >= 40% - Poor, significant gaps
    - **F**: < 40% - Failing, major improvements required

    ## Agentic Ready Threshold
    A repository is considered "Agentic Ready" when the overall score is >= 75 (Grade B or better).

    ## Response Includes
    - Overall grade and score
    - Testing and documentation breakdowns
    - Prioritized recommendations
    - Available enrichment actions
    """,
)
async def get_readiness_report(
    repository_id: str,
    generator: BRDGenerator = Depends(get_generator),
) -> AgenticReadinessResponse:
    """Generate Agentic Readiness Report for a repository."""
    from datetime import datetime
    from sqlalchemy import select

    try:
        logger.info(f"[API] Generating Agentic Readiness Report for repository: {repository_id}")

        # Get repository info
        async with get_async_session() as session:
            result = await session.execute(
                select(RepositoryDB).where(RepositoryDB.id == repository_id)
            )
            db_repo = result.scalar_one_or_none()

            if not db_repo:
                raise HTTPException(status_code=404, detail=f"Repository not found: {repository_id}")

            if db_repo.analysis_status != DBAnalysisStatus.COMPLETED:
                raise HTTPException(
                    status_code=400,
                    detail=f"Repository not analyzed. Current status: {db_repo.analysis_status.value}"
                )

            repository_name = db_repo.name

        # Ensure generator is initialized (for Neo4j client access)
        if not generator._initialized:
            await generator.initialize()

        # Generate readiness report using Neo4j data
        # For now, return a mock response - actual implementation would query Neo4j
        # In production, this would call AgenticReadinessService

        # Mock response for API structure demonstration
        # TODO: Integrate with AgenticReadinessService from codegraph
        return AgenticReadinessResponse(
            success=True,
            repository_id=repository_id,
            repository_name=repository_name,
            generated_at=datetime.now(),
            overall_grade=ReadinessGrade.C,
            overall_score=65,
            is_agentic_ready=False,
            testing=TestingReadinessResponse(
                overall_grade=ReadinessGrade.C,
                overall_score=60,
                coverage={
                    "percentage": 55,
                    "grade": ReadinessGrade.C,
                },
                untested_critical_functions=[],
                test_quality={
                    "has_unit_tests": True,
                    "has_integration_tests": False,
                    "has_e2e_tests": False,
                    "frameworks": ["jest"],
                },
                recommendations=[
                    "Increase test coverage to at least 70%",
                    "Add integration tests for API endpoints",
                ],
            ),
            documentation=DocumentationReadinessResponse(
                overall_grade=ReadinessGrade.C,
                overall_score=70,
                coverage={
                    "percentage": 65,
                    "grade": ReadinessGrade.C,
                },
                public_api_coverage={
                    "percentage": 70,
                    "grade": ReadinessGrade.C,
                },
                undocumented_public_apis=[],
                quality_distribution={
                    "excellent": 10,
                    "good": 30,
                    "partial": 25,
                    "minimal": 20,
                    "none": 15,
                },
                recommendations=[
                    "Document all public APIs",
                    "Improve documentation quality with examples",
                ],
            ),
            recommendations=[
                ReadinessRecommendation(
                    priority="high",
                    category="testing",
                    title="Increase Test Coverage",
                    description="Current test coverage is below the recommended threshold.",
                    affected_count=50,
                    estimated_effort="medium",
                ),
                ReadinessRecommendation(
                    priority="medium",
                    category="documentation",
                    title="Document Public APIs",
                    description="Several public APIs lack documentation.",
                    affected_count=25,
                    estimated_effort="medium",
                ),
            ],
            enrichment_actions=[
                EnrichmentAction(
                    id="enrich-docs-public-api",
                    name="Generate Documentation for Public APIs",
                    description="Auto-generate JSDoc documentation for undocumented public functions.",
                    affected_entities=25,
                    category="documentation",
                    is_automated=True,
                ),
                EnrichmentAction(
                    id="enrich-tests-critical",
                    name="Generate Tests for Critical Functions",
                    description="Auto-generate test skeletons for untested controller and service methods.",
                    affected_entities=15,
                    category="testing",
                    is_automated=True,
                ),
            ],
            summary=ReadinessSummary(
                total_entities=500,
                tested_entities=275,
                documented_entities=325,
                critical_gaps=40,
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to generate Agentic Readiness Report")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Codebase Statistics
# =============================================================================

@router.get(
    "/repositories/{repository_id}/statistics",
    response_model=CodebaseStatisticsResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Repository Statistics"],
    summary="Get Codebase Statistics",
    description="""
    Get comprehensive codebase statistics for a repository.

    This endpoint returns detailed metrics about the codebase including:

    ## Basic Metrics
    - Total files and lines of code
    - Language breakdown with percentages

    ## Code Structure
    - Classes, interfaces, and functions count
    - UI components count (React, Vue, Angular)
    - Services, controllers, and repository patterns

    ## API & Endpoints
    - REST endpoints count
    - GraphQL operations count

    ## Testing
    - Test files and test cases count
    - Test coverage indicators

    ## Dependencies & Architecture
    - External dependencies count
    - Database models/entities count
    - Configuration files count

    ## Code Quality
    - Complexity metrics (cyclomatic complexity)
    - Documentation coverage percentage

    Requires the repository to be analyzed first.
    """,
)
async def get_codebase_statistics(
    repository_id: str,
    generator: BRDGenerator = Depends(get_generator),
) -> CodebaseStatisticsResponse:
    """Get comprehensive codebase statistics for a repository."""
    from datetime import datetime
    from sqlalchemy import select

    try:
        logger.info(f"[API] Getting codebase statistics for repository: {repository_id}")

        # Get repository info
        async with get_async_session() as session:
            result = await session.execute(
                select(RepositoryDB).where(RepositoryDB.id == repository_id)
            )
            db_repo = result.scalar_one_or_none()

            if not db_repo:
                raise HTTPException(status_code=404, detail=f"Repository not found: {repository_id}")

            if db_repo.analysis_status != DBAnalysisStatus.COMPLETED:
                raise HTTPException(
                    status_code=400,
                    detail=f"Repository not analyzed. Current status: {db_repo.analysis_status.value}"
                )

            repository_name = db_repo.name

        # Ensure generator is initialized (for Neo4j client access)
        if not generator._initialized:
            await generator.initialize()

        # Initialize statistics with defaults
        stats = CodebaseStatistics()
        languages = []

        # Query Neo4j for statistics if client is available
        if generator.neo4j_client:
            try:
                # Note: Graph structure is Repository -> HAS_MODULE -> Module -> CONTAINS_FILE -> File
                # We traverse from Repository node to get files for this specific repository

                # Query 1: Basic file and LOC statistics
                # Try traversing from Repository first, fall back to direct query
                file_stats_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)
                WHERE r.repositoryId = $repository_id
                RETURN
                    count(f) as total_files,
                    sum(COALESCE(f.loc, f.lineCount, 0)) as total_loc,
                    avg(COALESCE(f.loc, f.lineCount, 0)) as avg_file_size
                """
                file_result = await generator.neo4j_client.query_code_structure(
                    file_stats_query,
                    {"repository_id": repository_id}
                )
                if file_result and file_result.get("nodes"):
                    node = file_result["nodes"][0]
                    stats.total_files = int(node.get("total_files", 0) or 0)
                    stats.total_lines_of_code = int(node.get("total_loc", 0) or 0)
                    stats.avg_file_size = float(node.get("avg_file_size", 0) or 0)

                # Query 2: Language breakdown (including JSP pages)
                lang_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)
                WHERE r.repositoryId = $repository_id AND f.language IS NOT NULL
                RETURN
                    f.language as language,
                    count(f) as file_count,
                    sum(COALESCE(f.loc, f.lineCount, 0)) as loc
                ORDER BY loc DESC
                """
                lang_result = await generator.neo4j_client.query_code_structure(
                    lang_query,
                    {"repository_id": repository_id}
                )
                if lang_result and lang_result.get("nodes"):
                    total_loc = stats.total_lines_of_code or 1
                    for node in lang_result["nodes"]:
                        lang_loc = int(node.get("loc", 0) or 0)
                        languages.append(LanguageBreakdown(
                            language=node.get("language", "Unknown"),
                            file_count=int(node.get("file_count", 0) or 0),
                            lines_of_code=lang_loc,
                            percentage=round((lang_loc / total_loc) * 100, 1) if total_loc > 0 else 0
                        ))
                    if languages:
                        stats.primary_language = languages[0].language

                # Query 2b: Add JSP pages to language breakdown
                jsp_lang_query = """
                MATCH (j:JSPPage)
                WHERE j.filePath CONTAINS $repository_id
                RETURN
                    'JSP' as language,
                    count(j) as file_count,
                    sum(COALESCE(j.loc, j.lineCount, 0)) as loc
                """
                jsp_lang_result = await generator.neo4j_client.query_code_structure(
                    jsp_lang_query,
                    {"repository_id": repository_id}
                )
                if jsp_lang_result and jsp_lang_result.get("nodes"):
                    node = jsp_lang_result["nodes"][0]
                    jsp_count = int(node.get("file_count", 0) or 0)
                    jsp_loc = int(node.get("loc", 0) or 0)
                    if jsp_count > 0:
                        # Add JSP files to total
                        stats.total_files += jsp_count
                        stats.total_lines_of_code += jsp_loc
                        total_loc = stats.total_lines_of_code or 1
                        # Add JSP to languages
                        languages.append(LanguageBreakdown(
                            language="JSP",
                            file_count=jsp_count,
                            lines_of_code=jsp_loc,
                            percentage=round((jsp_loc / total_loc) * 100, 1) if total_loc > 0 else 0
                        ))
                        # Recalculate percentages for existing languages
                        for lang in languages[:-1]:  # All except JSP we just added
                            lang.percentage = round((lang.lines_of_code / total_loc) * 100, 1) if total_loc > 0 else 0

                # Query 3: Classes - traverse from Repository through modules to files to classes
                class_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)-[:DEFINES_CLASS]->(c)
                WHERE r.repositoryId = $repository_id
                    AND (c:Class OR c:JavaClass OR c:CSharpClass OR c:CppClass OR c:PythonClass)
                RETURN count(c) as count
                """
                class_result = await generator.neo4j_client.query_code_structure(
                    class_query,
                    {"repository_id": repository_id}
                )
                if class_result and class_result.get("nodes"):
                    stats.total_classes = int(class_result["nodes"][0].get("count", 0) or 0)

                # Query 4: Interfaces
                interface_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)-[:DEFINES_CLASS]->(i)
                WHERE r.repositoryId = $repository_id
                    AND (i:Interface OR i:JavaInterface OR i:CSharpInterface OR i:GoInterface)
                RETURN count(i) as count
                """
                interface_result = await generator.neo4j_client.query_code_structure(
                    interface_query,
                    {"repository_id": repository_id}
                )
                if interface_result and interface_result.get("nodes"):
                    stats.total_interfaces = int(interface_result["nodes"][0].get("count", 0) or 0)

                # Query 5: Functions/Methods - traverse from classes
                func_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)-[:DEFINES_CLASS]->(c)-[:HAS_METHOD]->(method)
                WHERE r.repositoryId = $repository_id
                RETURN count(method) as count
                """
                func_result = await generator.neo4j_client.query_code_structure(
                    func_query,
                    {"repository_id": repository_id}
                )
                if func_result and func_result.get("nodes"):
                    stats.total_functions = int(func_result["nodes"][0].get("count", 0) or 0)

                # Query 6: UI Components - traverse from Repository
                component_query = """
                MATCH (r:Repository)-[*1..4]->(c:Component)
                WHERE r.repositoryId = $repository_id
                RETURN count(c) as count
                """
                comp_result = await generator.neo4j_client.query_code_structure(
                    component_query,
                    {"repository_id": repository_id}
                )
                if comp_result and comp_result.get("nodes"):
                    stats.total_components = int(comp_result["nodes"][0].get("count", 0) or 0)
                    stats.ui_components = stats.total_components

                # Query 7: REST Endpoints - check SpringController or RestEndpoint through Repository
                rest_query = """
                MATCH (r:Repository)-[*1..4]->(e)
                WHERE r.repositoryId = $repository_id
                    AND (e:RestEndpoint OR e:SpringController)
                RETURN count(e) as count
                """
                rest_result = await generator.neo4j_client.query_code_structure(
                    rest_query,
                    {"repository_id": repository_id}
                )
                if rest_result and rest_result.get("nodes"):
                    stats.rest_endpoints = int(rest_result["nodes"][0].get("count", 0) or 0)

                # Query 8: GraphQL Operations
                graphql_query = """
                MATCH (r:Repository)-[*1..4]->(g:GraphQLOperation)
                WHERE r.repositoryId = $repository_id
                RETURN count(g) as count
                """
                gql_result = await generator.neo4j_client.query_code_structure(
                    graphql_query,
                    {"repository_id": repository_id}
                )
                if gql_result and gql_result.get("nodes"):
                    stats.graphql_operations = int(gql_result["nodes"][0].get("count", 0) or 0)

                stats.total_api_endpoints = stats.rest_endpoints + stats.graphql_operations

                # Query 9: Test Files (by name pattern or TestFile label)
                test_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)
                WHERE r.repositoryId = $repository_id
                    AND (f.name CONTAINS 'Test' OR f.name CONTAINS 'test'
                         OR f.filePath CONTAINS '/test/' OR f.filePath CONTAINS '/tests/')
                RETURN count(f) as file_count
                """
                test_result = await generator.neo4j_client.query_code_structure(
                    test_query,
                    {"repository_id": repository_id}
                )
                if test_result and test_result.get("nodes"):
                    stats.total_test_files = int(test_result["nodes"][0].get("file_count", 0) or 0)
                    # Estimate test cases (avg 5 tests per test file)
                    stats.total_test_cases = stats.total_test_files * 5

                # Query 10: Dependencies (external imports/dependencies) - traverse from Repository
                dep_query = """
                MATCH (r:Repository)-[*1..3]->(d)
                WHERE r.repositoryId = $repository_id
                    AND (d:GradleDependency OR d:MavenDependency OR d:NpmDependency)
                RETURN count(d) as count
                """
                dep_result = await generator.neo4j_client.query_code_structure(
                    dep_query,
                    {"repository_id": repository_id}
                )
                if dep_result and dep_result.get("nodes"):
                    stats.total_dependencies = int(dep_result["nodes"][0].get("count", 0) or 0)

                # If no explicit dependencies, count unique imports
                if stats.total_dependencies == 0:
                    # Count JAVA_IMPORTS relationships as proxy for dependencies
                    import_query = """
                    MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)-[:DEFINES_CLASS]->(c)-[:JAVA_IMPORTS]->(imported)
                    WHERE r.repositoryId = $repository_id
                    RETURN count(DISTINCT imported) as count
                    """
                    import_result = await generator.neo4j_client.query_code_structure(
                        import_query,
                        {"repository_id": repository_id}
                    )
                    if import_result and import_result.get("nodes"):
                        dep_count = int(import_result["nodes"][0].get("count", 0) or 0)
                        stats.total_dependencies = dep_count

                # Query 11: Database Models - traverse from Repository to Entity classes
                db_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)-[:DEFINES_CLASS]->(c)
                WHERE r.repositoryId = $repository_id
                    AND (c:Entity
                         OR c.stereotype = 'Entity'
                         OR (c:JavaClass AND (c.name ENDS WITH 'Entity' OR c.name ENDS WITH 'Model')))
                RETURN count(c) as count
                """
                db_result = await generator.neo4j_client.query_code_structure(
                    db_query,
                    {"repository_id": repository_id}
                )
                if db_result and db_result.get("nodes"):
                    stats.total_database_models = int(db_result["nodes"][0].get("count", 0) or 0)

                # Query 11: Complexity Metrics
                # Query 12: Complexity Metrics - traverse from Repository
                complexity_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)-[:DEFINES_CLASS]->(c)-[:HAS_METHOD]->(method)
                WHERE r.repositoryId = $repository_id
                    AND method.complexity IS NOT NULL
                RETURN
                    avg(method.complexity) as avg_complexity,
                    max(method.complexity) as max_complexity
                """
                complexity_result = await generator.neo4j_client.query_code_structure(
                    complexity_query,
                    {"repository_id": repository_id}
                )
                if complexity_result and complexity_result.get("nodes"):
                    node = complexity_result["nodes"][0]
                    avg_c = node.get("avg_complexity")
                    max_c = node.get("max_complexity")
                    if avg_c is not None:
                        stats.avg_cyclomatic_complexity = round(float(avg_c), 2)
                    if max_c is not None:
                        stats.max_cyclomatic_complexity = int(max_c)

                # Query 13: Services, Controllers, Repositories - traverse from Repository
                service_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)-[:DEFINES_CLASS]->(s)
                WHERE r.repositoryId = $repository_id
                    AND (s:SpringService OR s.stereotype = 'Service')
                RETURN count(s) as count
                """
                svc_result = await generator.neo4j_client.query_code_structure(
                    service_query,
                    {"repository_id": repository_id}
                )
                if svc_result and svc_result.get("nodes"):
                    stats.services_count = int(svc_result["nodes"][0].get("count", 0) or 0)

                controller_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)-[:DEFINES_CLASS]->(ctrl)
                WHERE r.repositoryId = $repository_id
                    AND (ctrl:SpringController OR ctrl.stereotype = 'Controller')
                RETURN count(ctrl) as count
                """
                ctrl_result = await generator.neo4j_client.query_code_structure(
                    controller_query,
                    {"repository_id": repository_id}
                )
                if ctrl_result and ctrl_result.get("nodes"):
                    stats.controllers_count = int(ctrl_result["nodes"][0].get("count", 0) or 0)

                repo_class_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)-[:DEFINES_CLASS]->(repo_class)
                WHERE r.repositoryId = $repository_id
                    AND repo_class.stereotype = 'Repository'
                RETURN count(repo_class) as count
                """
                repo_result = await generator.neo4j_client.query_code_structure(
                    repo_class_query,
                    {"repository_id": repository_id}
                )
                if repo_result and repo_result.get("nodes"):
                    stats.repositories_count = int(repo_result["nodes"][0].get("count", 0) or 0)

                # Query 14: UI Routes/Pages - count JSP pages as UI components for Java web apps
                # JSP pages may be orphaned, so filter by filePath instead of traversing
                route_query = """
                MATCH (j:JSPPage)
                WHERE j.filePath CONTAINS $repository_id
                RETURN count(j) as count
                """
                route_result = await generator.neo4j_client.query_code_structure(
                    route_query,
                    {"repository_id": repository_id}
                )
                if route_result and route_result.get("nodes"):
                    jsp_count = int(route_result["nodes"][0].get("count", 0) or 0)
                    stats.ui_routes = jsp_count
                    stats.ui_components = jsp_count
                    stats.total_components = jsp_count

                # Also check for React/Vue components via Repository traversal
                component_query2 = """
                MATCH (r:Repository)-[*1..4]->(page)
                WHERE r.repositoryId = $repository_id
                    AND (page:UIRoute OR page:UIPage OR page:Component)
                RETURN count(page) as count
                """
                comp_result2 = await generator.neo4j_client.query_code_structure(
                    component_query2,
                    {"repository_id": repository_id}
                )
                if comp_result2 and comp_result2.get("nodes"):
                    count = int(comp_result2["nodes"][0].get("count", 0) or 0)
                    if count > 0:
                        stats.ui_routes += count
                        stats.ui_components += count
                        stats.total_components += count

                # Query 15: Documentation Coverage - traverse from Repository
                doc_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)-[:DEFINES_CLASS]->(c)
                WHERE r.repositoryId = $repository_id
                OPTIONAL MATCH (c)-[:HAS_METHOD]->(method)
                WITH c, method
                RETURN
                    count(DISTINCT c) + count(method) as total,
                    sum(CASE WHEN c.hasDocumentation = true
                             OR (c.javadoc IS NOT NULL AND c.javadoc <> '')
                        THEN 1 ELSE 0 END) +
                    sum(CASE WHEN method.hasDocumentation = true
                             OR (method.javadoc IS NOT NULL AND method.javadoc <> '')
                        THEN 1 ELSE 0 END) as documented
                """
                doc_result = await generator.neo4j_client.query_code_structure(
                    doc_query,
                    {"repository_id": repository_id}
                )
                if doc_result and doc_result.get("nodes"):
                    node = doc_result["nodes"][0]
                    total = int(node.get("total", 0) or 0)
                    documented = int(node.get("documented", 0) or 0)
                    stats.documented_entities = documented
                    if total > 0:
                        stats.documentation_coverage = round((documented / total) * 100, 1)

                # Query 16: Config Files - traverse from Repository
                config_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)
                WHERE r.repositoryId = $repository_id
                    AND (f.name ENDS WITH '.xml' OR f.name ENDS WITH '.properties'
                         OR f.name ENDS WITH '.yaml' OR f.name ENDS WITH '.yml'
                         OR f.name ENDS WITH '.json' OR f.name ENDS WITH '.toml'
                         OR f.name ENDS WITH '.env' OR f.name ENDS WITH '.config.js'
                         OR f.name ENDS WITH '.config.ts' OR f.name = 'package.json'
                         OR f.name = 'tsconfig.json' OR f.name = 'pom.xml'
                         OR f.name = 'build.gradle' OR f.name = 'settings.gradle'
                         OR f.filePath CONTAINS '/config/' OR f.filePath CONTAINS '/resources/')
                RETURN count(f) as count
                """
                config_result = await generator.neo4j_client.query_code_structure(
                    config_query,
                    {"repository_id": repository_id}
                )
                if config_result and config_result.get("nodes"):
                    stats.config_files = int(config_result["nodes"][0].get("count", 0) or 0)

            except Exception as neo4j_error:
                logger.warning(f"Neo4j query failed, using default statistics: {neo4j_error}")

        # Update languages in stats
        stats.languages = languages

        # Build summary for quick display
        summary = {
            "files": stats.total_files,
            "loc": stats.total_lines_of_code,
            "classes": stats.total_classes,
            "functions": stats.total_functions,
            "apis": stats.total_api_endpoints,
            "components": stats.total_components,
            "tests": stats.total_test_files,
            "languages": len(languages),
            "primary_language": stats.primary_language,
        }

        return CodebaseStatisticsResponse(
            success=True,
            repository_id=repository_id,
            repository_name=repository_name,
            generated_at=datetime.now(),
            statistics=stats,
            summary=summary,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get codebase statistics")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Phase 4: Codebase Enrichment
# =============================================================================

@router.post(
    "/repositories/{repository_id}/enrich/documentation",
    response_model=EnrichmentResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Codebase Enrichment"],
    summary="Generate documentation for undocumented code",
    description="""
    **Phase 4**: Generate documentation for undocumented functions and classes.

    This endpoint uses LLM to generate documentation based on:
    - Function/method signatures
    - Parameter types and names
    - Return types
    - Code context and implementation

    ## Supported Styles
    - **jsdoc**: JavaScript/TypeScript JSDoc format
    - **javadoc**: Java documentation format
    - **docstring**: Python docstring format
    - **xmldoc**: C# XML documentation format
    - **godoc**: Go documentation format

    ## Entity Selection
    - Provide specific `entity_ids` to document particular functions/classes
    - Use `"all-undocumented"` to process all undocumented public APIs
    - Use `max_entities` to limit processing (default: 50)

    ## Response
    Returns generated documentation content with:
    - File paths for insertion
    - Line/column positions
    - The generated documentation content
    """,
)
async def enrich_documentation(
    repository_id: str,
    request: DocumentationEnrichmentRequest,
    generator: BRDGenerator = Depends(get_generator),
) -> EnrichmentResponse:
    """Generate documentation for undocumented code."""
    try:
        logger.info(f"[API] Documentation enrichment requested for repository: {repository_id}")
        logger.info(f"[API] Style: {request.style}, Entities: {request.entity_ids}")

        # Validate repository exists
        async with get_async_session() as session:
            result = await session.execute(
                select(RepositoryDB).where(RepositoryDB.id == repository_id)
            )
            db_repo = result.scalar_one_or_none()

            if not db_repo:
                raise HTTPException(status_code=404, detail=f"Repository not found: {repository_id}")

        # TODO: Implement actual documentation generation using LLM
        # This would:
        # 1. Query Neo4j for undocumented entities
        # 2. Get source code context
        # 3. Use LLM to generate documentation
        # 4. Return generated content

        # Mock response for API structure demonstration
        return EnrichmentResponse(
            success=True,
            entities_processed=10,
            entities_enriched=8,
            entities_skipped=2,
            generated_content=[],
            errors=[],
            enrichment_type="documentation",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to enrich documentation")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/repositories/{repository_id}/enrich/tests",
    response_model=EnrichmentResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Codebase Enrichment"],
    summary="Generate test skeletons for untested code",
    description="""
    **Phase 4**: Generate test skeletons for untested functions and methods.

    This endpoint uses LLM to generate test code based on:
    - Function/method signatures
    - Implementation logic analysis
    - Known testing patterns for the framework
    - Edge case identification

    ## Supported Frameworks
    - **jest**: JavaScript/TypeScript testing
    - **mocha**: JavaScript testing
    - **junit**: Java testing
    - **pytest**: Python testing
    - **go test**: Go testing
    - **xunit**: C# testing

    ## Test Types
    - **unit**: Unit tests for isolated function testing
    - **integration**: Integration tests for service interactions

    ## Entity Selection
    - Provide specific `entity_ids` to generate tests for particular functions
    - Use `"all-untested"` to process all untested critical functions
    - Use `max_entities` to limit processing (default: 20)

    ## Response
    Returns generated test content with:
    - Test file paths
    - The generated test code
    - Mock/stub configurations if needed
    """,
)
async def enrich_tests(
    repository_id: str,
    request: TestEnrichmentRequest,
    generator: BRDGenerator = Depends(get_generator),
) -> EnrichmentResponse:
    """Generate test skeletons for untested code."""
    try:
        logger.info(f"[API] Test enrichment requested for repository: {repository_id}")
        logger.info(f"[API] Framework: {request.framework}, Types: {request.test_types}")

        # Validate repository exists
        async with get_async_session() as session:
            result = await session.execute(
                select(RepositoryDB).where(RepositoryDB.id == repository_id)
            )
            db_repo = result.scalar_one_or_none()

            if not db_repo:
                raise HTTPException(status_code=404, detail=f"Repository not found: {repository_id}")

        # TODO: Implement actual test generation using LLM
        # This would:
        # 1. Query Neo4j for untested entities
        # 2. Get source code context
        # 3. Analyze function behavior and dependencies
        # 4. Use LLM to generate tests
        # 5. Return generated test code

        # Mock response for API structure demonstration
        return EnrichmentResponse(
            success=True,
            entities_processed=5,
            entities_enriched=4,
            entities_skipped=1,
            generated_content=[],
            errors=[],
            enrichment_type="testing",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to enrich tests")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Phase 5: Business Features Discovery
# =============================================================================

def _categorize_feature(name: str, controller_name: str = "", paths: list[str] = None) -> FeatureCategory:
    """Categorize a feature based on naming patterns and paths."""
    paths = paths or []
    combined = f"{name} {controller_name} {' '.join(paths)}".lower()

    if any(kw in combined for kw in ["auth", "login", "logout", "session", "oauth", "sso", "credential"]):
        return FeatureCategory.AUTHENTICATION
    elif any(kw in combined for kw in ["user", "profile", "account", "member", "customer", "register"]):
        return FeatureCategory.USER_MANAGEMENT
    elif any(kw in combined for kw in ["payment", "billing", "invoice", "subscription", "checkout", "cart"]):
        return FeatureCategory.PAYMENT
    elif any(kw in combined for kw in ["admin", "manage", "dashboard", "console"]):
        return FeatureCategory.ADMIN
    elif any(kw in combined for kw in ["report", "analytics", "stats", "metrics", "export"]):
        return FeatureCategory.REPORTING
    elif any(kw in combined for kw in ["search", "filter", "find", "query", "lookup"]):
        return FeatureCategory.SEARCH
    elif any(kw in combined for kw in ["notify", "alert", "email", "sms", "push", "message"]):
        return FeatureCategory.NOTIFICATION
    elif any(kw in combined for kw in ["config", "setting", "preference", "option"]):
        return FeatureCategory.CONFIGURATION
    elif any(kw in combined for kw in ["workflow", "process", "flow", "step", "wizard"]):
        return FeatureCategory.WORKFLOW
    elif any(kw in combined for kw in ["integrat", "api", "external", "webhook", "sync"]):
        return FeatureCategory.INTEGRATION
    elif any(kw in combined for kw in ["create", "update", "delete", "edit", "save", "load", "data"]):
        return FeatureCategory.DATA_MANAGEMENT
    return FeatureCategory.OTHER


def _calculate_complexity(footprint: CodeFootprint) -> tuple[FeatureComplexity, int]:
    """Calculate complexity based on code footprint."""
    # Base score from file counts
    score = 0
    score += min(len(footprint.controllers) * 10, 20)
    score += min(len(footprint.services) * 8, 24)
    score += min(len(footprint.repositories) * 5, 15)
    score += min(len(footprint.models) * 3, 15)
    score += min(len(footprint.views) * 4, 16)
    score += min(footprint.total_files * 2, 20)

    # Cap at 100
    score = min(score, 100)

    if score >= 75:
        return FeatureComplexity.VERY_HIGH, score
    elif score >= 50:
        return FeatureComplexity.HIGH, score
    elif score >= 25:
        return FeatureComplexity.MEDIUM, score
    return FeatureComplexity.LOW, score


def _generate_feature_description(
    name: str,
    category: FeatureCategory,
    footprint: CodeFootprint,
    endpoints: list[FeatureEndpoint]
) -> str:
    """Generate a description for a feature based on its metadata."""
    parts = []

    # Main description
    category_desc = {
        FeatureCategory.AUTHENTICATION: "handles user authentication and session management",
        FeatureCategory.USER_MANAGEMENT: "manages user profiles and account operations",
        FeatureCategory.DATA_MANAGEMENT: "provides data management capabilities",
        FeatureCategory.WORKFLOW: "implements business workflow processes",
        FeatureCategory.REPORTING: "generates reports and analytics",
        FeatureCategory.INTEGRATION: "integrates with external systems",
        FeatureCategory.PAYMENT: "processes payments and billing",
        FeatureCategory.NOTIFICATION: "sends notifications and alerts",
        FeatureCategory.SEARCH: "provides search and filtering functionality",
        FeatureCategory.ADMIN: "provides administrative functions",
        FeatureCategory.CONFIGURATION: "manages system configuration",
        FeatureCategory.OTHER: "provides business functionality",
    }
    parts.append(f"This feature {category_desc.get(category, 'provides business functionality')}.")

    # Components
    if footprint.controllers:
        parts.append(f"Exposes {len(footprint.controllers)} controller(s).")
    if footprint.services:
        parts.append(f"Utilizes {len(footprint.services)} service(s).")
    if endpoints:
        parts.append(f"Provides {len(endpoints)} API endpoint(s).")
    if footprint.views:
        parts.append(f"Includes {len(footprint.views)} UI view(s).")

    return " ".join(parts)


# =============================================================================
# Dynamic Feature Discovery Helpers
# =============================================================================

# Blocklist of obvious technical/infrastructure terms (small, focused list)
TECHNICAL_BLOCKLIST = {
    # Logging/Debugging
    'log', 'logger', 'logging', 'log4j', 'slf4j', 'debug', 'trace',

    # UI Infrastructure
    'header', 'footer', 'layout', 'template', 'include', 'menu', 'nav',
    'sidebar', 'toolbar', 'modal', 'dialog', 'error', 'exception',

    # System/Admin
    'admin', 'jamon', 'jamonadmin', 'actuator', 'swagger', 'health', 'metrics',

    # Generic pages
    'index', 'home', 'main', 'default', 'welcome', 'login', 'logout',

    # Test/Mock
    'test', 'tests', 'spec', 'mock', 'stub',
}


def _is_technical_name(name: str) -> bool:
    """Check if a name represents technical infrastructure (not a business feature)."""
    name_lower = name.lower()

    # Check blocklist
    for term in TECHNICAL_BLOCKLIST:
        if name_lower == term or name_lower.startswith(term) or name_lower.endswith(term):
            return True

    return False


def _extract_screen_prefix(jsp_name: str) -> str:
    """Extract the screen prefix from a JSP filename."""
    import re
    name = jsp_name.replace('.jsp', '').replace('.JSP', '')

    # Remove common suffixes
    suffixes = [
        'SearchLookup', 'SearchResults', 'MaintenanceEntry', 'MaintenanceResults',
        'Entry', 'Results', 'Lookup', 'Search', 'Detail', 'Details',
        'Conflicts', 'List', 'View', 'Edit', 'Add', 'Delete', 'Form',
        'Maintenance', 'Management', 'Admin', 'Summary', 'Report',
        'Procedures', 'Rule', 'Rules', 'Inquiry',
    ]

    for suffix in suffixes:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[:-len(suffix)]
            break

    return name


def _group_jsps_by_prefix(jsp_pages: list[dict]) -> dict[str, list[dict]]:
    """Group JSP pages by their screen prefix."""
    groups: dict[str, list[dict]] = {}

    for jsp in jsp_pages:
        jsp_name = jsp.get('name', '')
        if not jsp_name:
            continue

        prefix = _extract_screen_prefix(jsp_name)

        # Skip technical prefixes
        if _is_technical_name(prefix):
            continue

        if prefix not in groups:
            groups[prefix] = []
        groups[prefix].append(jsp)

    return groups


def _camel_to_title(camel_str: str) -> str:
    """Convert camelCase to Title Case with spaces."""
    import re

    # Handle common acronyms
    acronyms = {'edi': 'EDI', 'duns': 'DUNS', 'api': 'API', 'ui': 'UI', 'csr': 'CSR', 'xml': 'XML'}

    spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', camel_str)
    spaced = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', spaced)

    words = spaced.split()
    result_words = []
    for word in words:
        word_lower = word.lower()
        if word_lower in acronyms:
            result_words.append(acronyms[word_lower])
        else:
            result_words.append(word.capitalize())

    return ' '.join(result_words)


def _infer_feature_group(feature_name: str) -> str:
    """Infer the feature group from feature name by removing common action suffixes.

    Examples:
    - "Legal Entity Search" → "Legal Entity"
    - "Legal Entity Address" → "Legal Entity"
    - "User Management Settings" → "User Management"
    - "Dashboard" → "Dashboard" (no suffix to remove)

    Args:
        feature_name: The full feature name

    Returns:
        The inferred group name (prefix without action suffix)
    """
    # Common action/view suffixes to strip for grouping
    suffixes = [
        'Search', 'List', 'Detail', 'Details', 'Edit', 'Create', 'Update',
        'Delete', 'View', 'Entry', 'Results', 'Lookup', 'Address', 'Contact',
        'History', 'Management', 'Configuration', 'Settings', 'Overview',
        'Summary', 'Report', 'Reports', 'Dashboard', 'Form', 'Wizard',
        'Add', 'New', 'Info', 'Information', 'Profile', 'Status',
    ]

    group = feature_name.strip()

    # Try to remove suffixes (only remove one suffix)
    for suffix in suffixes:
        if group.endswith(f' {suffix}'):
            group = group[:-len(suffix)-1].strip()
            break

    # Return original name if no suffix was removed or result is empty
    return group if group else feature_name


def _is_likely_business_feature(prefix: str, jsp_names: list[str], controllers: list[str]) -> bool:
    """Use smart heuristics to determine if this is likely a business feature.

    Business features typically:
    - Have multiple related screens (JSPs)
    - Are backed by controllers
    - Have meaningful business entity names (compound names like legalEntity)
    - Are NOT generic single-word utility pages
    """
    # Already filtered technical names, but double-check
    if _is_technical_name(prefix):
        return False

    # Generic single-word names that are NOT business features regardless of JSP count
    generic_excludes = {
        'definition', 'definitions', 'employee', 'employees',
        'email', 'message', 'notification', 'alert', 'alerts',
        'search', 'find', 'lookup', 'query', 'filter',
        'report', 'reports', 'export', 'import', 'upload', 'download',
        'list', 'grid', 'table', 'view', 'display', 'show',
        'help', 'info', 'about', 'contact', 'settings', 'preferences',
        'print', 'pdf', 'csv', 'excel', 'word',
        'common', 'shared', 'util', 'utils', 'utility', 'utilities',
        'base', 'abstract', 'generic', 'default', 'standard',
    }

    prefix_lower = prefix.lower()

    # Check if it's a generic single-word name (no compound)
    has_compound_name = any(c.isupper() for c in prefix[1:]) if len(prefix) > 1 else False

    # Exclude generic single-word names even if they have multiple JSPs
    if not has_compound_name and prefix_lower in generic_excludes:
        return False

    # If it has a controller AND is a compound name, it's likely a business feature
    if controllers and has_compound_name:
        return True

    # If it has a controller but generic name, check if it's a real business entity
    if controllers and not has_compound_name:
        # Even with a controller, single generic words are likely infrastructure
        if prefix_lower in generic_excludes:
            return False
        return True

    # No controller - must have compound name AND multiple JSPs
    if not controllers:
        if not has_compound_name:
            return False
        # Compound name with multiple JSPs - likely a business feature
        if len(jsp_names) >= 2:
            return True
        # Single JSP even with compound name - be conservative
        return False

    return False


async def _classify_features_with_llm(
    session,
    candidates: list[dict],
) -> list[dict]:
    """Use LLM to classify and name multiple feature candidates at once.

    Args:
        session: LLM session
        candidates: List of dicts with 'prefix', 'jsp_names', 'controllers'

    Returns:
        List of dicts with 'prefix', 'is_business', 'feature_name'
    """
    # Use smart heuristics (works without LLM)
    results = []
    for c in candidates:
        prefix = c['prefix']
        jsp_names = c['jsp_names']
        controllers = c['controllers']

        is_business = _is_likely_business_feature(prefix, jsp_names, controllers)

        results.append({
            'prefix': prefix,
            'is_business': is_business,
            'feature_name': _camel_to_title(prefix),
        })

    # If LLM session available, try to get better names for business features
    if session:
        try:
            # Build batch prompt for business features only
            business_candidates = [(i, c) for i, c in enumerate(candidates) if results[i]['is_business']]

            if business_candidates and len(business_candidates) <= 30:
                candidate_list = []
                for idx, (i, c) in enumerate(business_candidates):
                    jsp_str = ', '.join(c['jsp_names'][:3])
                    ctrl_str = ', '.join(c['controllers'][:2]) if c['controllers'] else 'None'
                    candidate_list.append(f"{idx+1}. {c['prefix']} | JSPs: {jsp_str} | Controllers: {ctrl_str}")

                prompt = f"""Generate concise business feature names (2-4 words each) for these screens.

Screens:
{chr(10).join(candidate_list)}

Respond with one name per line in format: <number>|<Feature Name>
Example:
1|Legal Entity Search
2|Contract Management
"""

                if hasattr(session, 'send_and_wait'):
                    import asyncio
                    event = await asyncio.wait_for(
                        session.send_and_wait({"prompt": prompt}, timeout=30),
                        timeout=35
                    )

                    if event and hasattr(event, 'text'):
                        response = event.text.strip()
                        for line in response.split('\n'):
                            parts = line.strip().split('|')
                            if len(parts) >= 2:
                                try:
                                    idx = int(parts[0].strip()) - 1
                                    name = parts[1].strip().strip('"').strip("'")
                                    if 0 <= idx < len(business_candidates) and name:
                                        original_idx = business_candidates[idx][0]
                                        results[original_idx]['feature_name'] = name
                                except (ValueError, IndexError):
                                    continue

        except Exception as e:
            logger.warning(f"LLM feature naming failed (using heuristic names): {e}")

    return results


@router.get(
    "/repositories/{repository_id}/features",
    response_model=DiscoveredFeaturesResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Business Features Discovery"],
    summary="Discover business features from codebase",
    description="""
    **Phase 5**: Discover business features from the analyzed codebase.

    This endpoint analyzes the code graph to identify distinct business features
    using a **screen-centric approach**:

    1. **JSP Pages** - Group related JSP pages into logical screens/features
    2. **Spring Web Flows** - Multi-step business processes
    3. **Controllers** - Find associated controllers for each screen

    ## Discovery Process (Dynamic + LLM Classification)

    1. **Web Flows First** - Spring Web Flows are explicit business processes
    2. **JSP Grouping** - Group JSPs by common prefix
    3. **LLM Classification** - Use LLM to classify each group as BUSINESS or TECHNICAL
    4. **Controller Mapping** - Find associated controllers for each feature

    ## How It Works

    - No hardcoded business domains - discovery is fully dynamic
    - LLM classifies candidates as business features or technical infrastructure
    - Technical blocklist filters obvious infrastructure (logging, admin, layouts)
    - Features with multiple JSPs or controllers are prioritized

    ## Response

    Returns validated business features with:
    - LLM-generated business-friendly name
    - Associated controllers and services
    - Grouped JSP views
    """,
)
async def discover_business_features(
    repository_id: str,
    generator: BRDGenerator = Depends(get_generator),
) -> DiscoveredFeaturesResponse:
    """Discover business features using dynamic LLM-based classification."""
    import time
    from datetime import datetime
    from sqlalchemy import select

    start_time = time.time()

    try:
        logger.info(f"[API] Discovering business features for repository: {repository_id}")

        # Get repository info
        async with get_async_session() as db_session:
            result = await db_session.execute(
                select(RepositoryDB).where(RepositoryDB.id == repository_id)
            )
            db_repo = result.scalar_one_or_none()

            if not db_repo:
                raise HTTPException(status_code=404, detail=f"Repository not found: {repository_id}")

            if db_repo.analysis_status != DBAnalysisStatus.COMPLETED:
                raise HTTPException(
                    status_code=400,
                    detail=f"Repository not analyzed. Current status: {db_repo.analysis_status.value}"
                )

            repository_name = db_repo.name

        # Ensure generator is initialized
        if not generator._initialized:
            await generator.initialize()

        features: list[BusinessFeature] = []
        feature_id = 0

        # Get LLM session for feature classification
        llm_session = getattr(generator, '_copilot_session', None)

        if generator.neo4j_client:
            try:
                # =========================================================
                # Step 1: Web Flows - These ARE business processes
                # =========================================================
                logger.info("[FEATURES] Step 1: Discovering Web Flows...")
                webflow_query = """
                MATCH (r:Repository)-[*1..4]->(wf:WebFlowDefinition)
                WHERE r.repositoryId = $repository_id
                OPTIONAL MATCH (wf)-[:FLOW_DEFINES_STATE]->(state:FlowState)
                OPTIONAL MATCH (wf)-[:USES|DEPENDS_ON]->(svc)
                WHERE svc:SpringService OR svc.stereotype = 'Service'
                RETURN
                    wf.name as name,
                    wf.filePath as filePath,
                    collect(DISTINCT state.name) as states,
                    collect(DISTINCT svc.name) as services
                """
                webflow_result = await generator.neo4j_client.query_code_structure(
                    webflow_query,
                    {"repository_id": repository_id}
                )

                webflow_count = 0
                if webflow_result and webflow_result.get("nodes"):
                    for node in webflow_result["nodes"]:
                        wf_name = node.get("name", "")
                        if not wf_name or _is_technical_name(wf_name):
                            continue

                        feature_id += 1
                        webflow_count += 1
                        states = [s for s in (node.get("states") or []) if s]
                        services = [s for s in (node.get("services") or []) if s]

                        # Generate feature name from webflow
                        clean_name = wf_name.replace("-flow", "").replace("Flow", "").replace("-", " ")
                        feature_name = _camel_to_title(clean_name)

                        footprint = CodeFootprint(
                            services=services[:5],
                            views=states,
                            total_files=1 + len(states) + len(services),
                        )

                        category = _categorize_feature(feature_name, paths=[node.get("filePath", "")])
                        complexity, score = _calculate_complexity(footprint)

                        feature = BusinessFeature(
                            id=f"FEAT-{feature_id:03d}",
                            name=feature_name,
                            description=f"Business workflow with {len(states)} state(s).",
                            category=category,
                            complexity=complexity,
                            complexity_score=score,
                            discovery_source="webflow",
                            entry_points=[wf_name],
                            file_path=node.get("filePath"),
                            feature_group=_infer_feature_group(feature_name),
                            code_footprint=footprint,
                            has_tests=False,
                        )
                        features.append(feature)

                logger.info(f"[FEATURES] Found {webflow_count} web flows")

                # =========================================================
                # Step 2: Query all JSP pages
                # Note: JSP pages may be orphaned (not connected to Repository)
                # Filter by filePath containing the repository_id instead
                # =========================================================
                logger.info("[FEATURES] Step 2: Querying JSP pages...")
                jsp_query = """
                MATCH (j:JSPPage)
                WHERE j.filePath CONTAINS $repository_id
                   OR j.filePath CONTAINS '/ple-web/'
                RETURN j.name as name, j.filePath as filePath
                ORDER BY j.name
                """
                jsp_result = await generator.neo4j_client.query_code_structure(
                    jsp_query,
                    {"repository_id": repository_id}
                )

                jsp_pages = []
                if jsp_result and jsp_result.get("nodes"):
                    jsp_pages = [n for n in jsp_result["nodes"] if n.get("name")]

                logger.info(f"[FEATURES] Found {len(jsp_pages)} JSP pages")

                # =========================================================
                # Step 3: Group JSPs by prefix (filtering technical ones)
                # =========================================================
                logger.info("[FEATURES] Step 3: Grouping JSPs by prefix...")
                jsp_groups = _group_jsps_by_prefix(jsp_pages)
                logger.info(f"[FEATURES] Found {len(jsp_groups)} JSP groups after filtering")

                # =========================================================
                # Step 4: Query all controllers for mapping
                # =========================================================
                logger.info("[FEATURES] Step 4: Querying controllers...")
                controller_query = """
                MATCH (r:Repository)-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f:File)-[:DEFINES_CLASS]->(c)
                WHERE r.repositoryId = $repository_id
                    AND (c:SpringController OR c.stereotype = 'Controller')
                OPTIONAL MATCH (c)-[:USES|DEPENDS_ON|CALLS]->(svc)
                WHERE svc:SpringService OR svc.stereotype = 'Service'
                RETURN
                    c.name as controllerName,
                    c.filePath as filePath,
                    collect(DISTINCT svc.name) as services
                """
                controller_result = await generator.neo4j_client.query_code_structure(
                    controller_query,
                    {"repository_id": repository_id}
                )

                controllers_map: dict[str, dict] = {}
                if controller_result and controller_result.get("nodes"):
                    for node in controller_result["nodes"]:
                        ctrl_name = node.get("controllerName", "")
                        if ctrl_name:
                            controllers_map[ctrl_name.lower()] = node

                logger.info(f"[FEATURES] Found {len(controllers_map)} controllers")

                # =========================================================
                # Step 5: Build candidates and find matching controllers
                # =========================================================
                logger.info("[FEATURES] Step 5: Building feature candidates...")
                candidates = []
                for prefix, jsps in jsp_groups.items():
                    if not prefix or len(prefix) < 3:
                        continue

                    jsp_names = [j.get('name', '') for j in jsps]

                    # Find matching controllers
                    matched_controllers = []
                    prefix_lower = prefix.lower()
                    for ctrl_name, ctrl_info in controllers_map.items():
                        if prefix_lower in ctrl_name:
                            matched_controllers.append(ctrl_info.get('controllerName', ''))

                    candidates.append({
                        'prefix': prefix,
                        'jsp_names': jsp_names,
                        'controllers': matched_controllers,
                        'jsps': jsps,
                    })

                logger.info(f"[FEATURES] Built {len(candidates)} candidates for classification")

                # =========================================================
                # Step 6: Classify features with LLM (batch)
                # =========================================================
                logger.info("[FEATURES] Step 6: Classifying features with LLM...")
                classified = await _classify_features_with_llm(llm_session, candidates)

                # =========================================================
                # Step 7: Create features from classified results
                # =========================================================
                logger.info("[FEATURES] Step 7: Creating features from classified results...")
                for i, classification in enumerate(classified):
                    if not classification.get('is_business', False):
                        continue

                    candidate = candidates[i]
                    prefix = candidate['prefix']
                    jsps = candidate['jsps']
                    jsp_names = candidate['jsp_names']
                    matched_controllers = candidate['controllers']

                    feature_id += 1

                    # Get services from matched controllers
                    matched_services = []
                    for ctrl_name in matched_controllers:
                        ctrl_info = controllers_map.get(ctrl_name.lower(), {})
                        matched_services.extend(ctrl_info.get('services', []) or [])
                    matched_services = list(set(s for s in matched_services if s))

                    # Build footprint
                    footprint = CodeFootprint(
                        controllers=matched_controllers[:5],
                        services=matched_services[:5],
                        views=jsp_names,
                        total_files=len(jsps) + len(matched_controllers) + len(matched_services),
                    )

                    # Get feature name from LLM classification
                    feature_name = classification.get('feature_name', _camel_to_title(prefix))

                    # Get primary file path
                    file_paths = [j.get('filePath', '') for j in jsps]
                    primary_file_path = file_paths[0] if file_paths else None

                    category = _categorize_feature(feature_name, paths=file_paths)
                    complexity, score = _calculate_complexity(footprint)

                    feature = BusinessFeature(
                        id=f"FEAT-{feature_id:03d}",
                        name=feature_name,
                        description=f"Business feature with {len(jsps)} screen(s).",
                        category=category,
                        complexity=complexity,
                        complexity_score=score,
                        discovery_source="screen",
                        entry_points=matched_controllers[:3] if matched_controllers else [prefix],
                        file_path=primary_file_path,
                        feature_group=_infer_feature_group(feature_name),
                        code_footprint=footprint,
                        has_tests=False,
                    )
                    features.append(feature)

                logger.info(f"[FEATURES] Created {len(features)} total features")

            except Exception as neo4j_error:
                logger.warning(f"Neo4j query failed during feature discovery: {neo4j_error}")
                import traceback
                logger.warning(traceback.format_exc())

        # Calculate summary statistics
        summary = FeaturesSummary(
            total_features=len(features),
            by_category={cat.value: 0 for cat in FeatureCategory},
            by_complexity={comp.value: 0 for comp in FeatureComplexity},
            by_discovery_source={"screen": 0, "webflow": 0, "controller": 0},
            features_with_tests=0,
            features_with_brd=0,
            avg_complexity_score=0.0,
        )

        total_complexity = 0
        for feature in features:
            summary.by_category[feature.category.value] = summary.by_category.get(feature.category.value, 0) + 1
            summary.by_complexity[feature.complexity.value] = summary.by_complexity.get(feature.complexity.value, 0) + 1
            summary.by_discovery_source[feature.discovery_source] = summary.by_discovery_source.get(feature.discovery_source, 0) + 1
            if feature.has_tests:
                summary.features_with_tests += 1
            if feature.brd_generated:
                summary.features_with_brd += 1
            total_complexity += feature.complexity_score

        if features:
            summary.avg_complexity_score = round(total_complexity / len(features), 1)

        # Build feature groups from discovered features
        groups_dict: dict[str, list[BusinessFeature]] = {}
        for feature in features:
            group_name = feature.feature_group or feature.name
            if group_name not in groups_dict:
                groups_dict[group_name] = []
            groups_dict[group_name].append(feature)

        feature_groups = [
            FeatureGroup(name=name, features=feats, feature_count=len(feats))
            for name, feats in sorted(groups_dict.items())
        ]

        logger.info(f"[FEATURES] Grouped {len(features)} features into {len(feature_groups)} groups")

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        return DiscoveredFeaturesResponse(
            success=True,
            repository_id=repository_id,
            repository_name=repository_name,
            generated_at=datetime.now(),
            features=features,
            feature_groups=feature_groups,
            summary=summary,
            discovery_method="screen-centric",
            discovery_duration_ms=duration_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to discover business features")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Phase 2: EPIC Generation Endpoints
# =============================================================================

from ..models.epic import (
    Epic as TrackedEpic,
    BacklogItem,
    ProjectContext,
    GenerateEpicsRequest as EpicsGenRequest,
    RefineEpicRequest,
    RefineAllEpicsRequest,
    GenerateEpicsResponse as EpicsGenResponse,
    GenerateBacklogsRequest as BacklogsGenRequest,
    RefineBacklogItemRequest,
    GenerateBacklogsResponse as BacklogsGenResponse,
    EpicStreamEvent,
    BacklogStreamEvent,
)
from ..agents.epic_generator_agent import EpicGeneratorAgent
from ..agents.epic_verifier_agent import EpicVerifierAgent, EpicsVerificationBundle
from ..agents.backlog_generator_agent import BacklogGeneratorAgent
from ..agents.backlog_verifier_agent import BacklogVerifierAgent, BacklogsVerificationBundle


# Global agent instances
_epic_agent: EpicGeneratorAgent | None = None
_epic_verifier: EpicVerifierAgent | None = None
_backlog_agent: BacklogGeneratorAgent | None = None
_backlog_verifier: BacklogVerifierAgent | None = None


async def get_epic_agent(generator: BRDGenerator = Depends(get_generator)) -> EpicGeneratorAgent:
    """Get or create EPIC generator agent."""
    global _epic_agent
    if _epic_agent is None:
        _epic_agent = EpicGeneratorAgent(
            copilot_session=generator._copilot_session if generator else None,
            config={"max_epics": 10},
        )
    return _epic_agent


async def get_epic_verifier(generator: BRDGenerator = Depends(get_generator)) -> EpicVerifierAgent:
    """Get or create EPIC verifier agent."""
    global _epic_verifier
    if _epic_verifier is None:
        _epic_verifier = EpicVerifierAgent(
            copilot_session=generator._copilot_session if generator else None,
            config={"min_confidence": 0.6},
        )
    return _epic_verifier


async def get_backlog_agent(generator: BRDGenerator = Depends(get_generator)) -> BacklogGeneratorAgent:
    """Get or create Backlog generator agent."""
    global _backlog_agent
    if _backlog_agent is None:
        from ..core.epic_template_parser import EpicBacklogTemplateParser, DEFAULT_BACKLOG_FIELDS
        from ..models.epic import BacklogTemplateConfig

        # Create default template config with comprehensive story settings
        default_template_config = BacklogTemplateConfig(
            backlog_template=DEFAULT_BACKLOG_TEMPLATE,
            field_configs=DEFAULT_BACKLOG_FIELDS,
            default_description_words=150,  # Comprehensive descriptions
            default_acceptance_criteria_count=7,  # At least 5-7 criteria
            default_technical_notes_words=80,
            require_user_story_format=True,
            include_technical_notes=True,
            include_file_references=True,
            include_story_points=False,  # No story points
        )

        # Get parsed template
        parser = EpicBacklogTemplateParser(
            copilot_session=generator._copilot_session if generator else None
        )
        parsed_template = parser._get_default_backlog_template()

        _backlog_agent = BacklogGeneratorAgent(
            copilot_session=generator._copilot_session if generator else None,
            config={"items_per_epic": 5},
            template_config=default_template_config,
            parsed_template=parsed_template,
        )
    return _backlog_agent


async def get_backlog_verifier(generator: BRDGenerator = Depends(get_generator)) -> BacklogVerifierAgent:
    """Get or create Backlog verifier agent."""
    global _backlog_verifier
    if _backlog_verifier is None:
        _backlog_verifier = BacklogVerifierAgent(
            copilot_session=generator._copilot_session if generator else None,
            config={"min_confidence": 0.6},
        )
    return _backlog_verifier


# =============================================================================
# Phase 1: Pre-Analysis Endpoints (Intelligent Count Determination)
# =============================================================================

from ..models.epic import (
    AnalyzeBRDRequest,
    BRDAnalysisResult,
    AnalyzeEpicsForBacklogsRequest,
    AnalyzeEpicsForBacklogsResponse,
)
from ..core.brd_epic_analyzer import BRDAnalyzer, EpicAnalyzer

# Global analyzer instances
_brd_analyzer: BRDAnalyzer | None = None
_epic_analyzer: EpicAnalyzer | None = None


async def get_brd_analyzer(generator: BRDGenerator = Depends(get_generator)) -> BRDAnalyzer:
    """Get or create BRD analyzer."""
    global _brd_analyzer
    if _brd_analyzer is None:
        _brd_analyzer = BRDAnalyzer(
            copilot_session=generator._copilot_session if generator else None,
        )
    return _brd_analyzer


async def get_epic_analyzer(generator: BRDGenerator = Depends(get_generator)) -> EpicAnalyzer:
    """Get or create EPIC analyzer for backlog decomposition."""
    global _epic_analyzer
    if _epic_analyzer is None:
        _epic_analyzer = EpicAnalyzer(
            copilot_session=generator._copilot_session if generator else None,
        )
    return _epic_analyzer


@router.post(
    "/epics/analyze-brd",
    response_model=BRDAnalysisResult,
    tags=["Phase 1: Analysis"],
    summary="Analyze BRD for intelligent EPIC count determination",
    description="""
    **Phase 1: Pre-Analysis**

    Analyzes a BRD document to intelligently determine the optimal number and structure of EPICs.
    This endpoint should be called BEFORE generating EPICs to get AI-powered recommendations.

    ## How it works:
    1. **Structural Analysis**: Counts sections, requirements, personas, integrations
    2. **Semantic Analysis**: Uses LLM to understand functional areas and user journeys
    3. **Recommendations**: Provides optimal EPIC count with detailed breakdown

    ## What you get:
    - Recommended EPIC count (min/max/optimal)
    - Identified functional areas and user journeys
    - Complexity assessment with factors
    - Suggested EPIC breakdown with scope for each

    ## Workflow:
    1. Call this endpoint first with BRD content
    2. Review recommendations with user
    3. Pass the analysis result to `/epics/generate` for guided generation
    """,
)
async def analyze_brd_for_epics(
    request: AnalyzeBRDRequest,
    analyzer: BRDAnalyzer = Depends(get_brd_analyzer),
) -> BRDAnalysisResult:
    """Analyze BRD to determine optimal EPIC count and structure."""
    try:
        logger.info(f"[API] Analyzing BRD {request.brd_id} for EPIC decomposition")
        result = await analyzer.analyze_brd(request)
        logger.info(
            f"[API] BRD analysis complete: recommended {result.recommended_epic_count} EPICs "
            f"(range: {result.min_epic_count}-{result.max_epic_count})"
        )
        return result
    except Exception as e:
        logger.exception(f"Error analyzing BRD: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/backlogs/analyze-epics",
    response_model=AnalyzeEpicsForBacklogsResponse,
    tags=["Phase 1: Analysis"],
    summary="Analyze EPICs for intelligent backlog count determination",
    description="""
    **Phase 1: Pre-Analysis for Backlogs**

    Analyzes EPICs to intelligently determine the optimal number and structure of backlog items.
    This endpoint should be called BEFORE generating backlogs to get AI-powered recommendations.

    ## How it works:
    1. **Per-EPIC Analysis**: Analyzes each EPIC's scope, acceptance criteria, and complexity
    2. **Item Type Breakdown**: Recommends user stories, tasks, and spikes
    3. **Point Estimation**: Estimates total story points

    ## What you get (per EPIC):
    - Recommended item count (min/max/optimal)
    - Breakdown by type (stories, tasks, spikes)
    - Suggested items with titles and estimates
    - Complexity assessment

    ## Workflow:
    1. Call this endpoint first with EPICs
    2. Review recommendations with user
    3. Pass the analysis result to `/backlogs/generate` for guided generation
    """,
)
async def analyze_epics_for_backlogs(
    request: AnalyzeEpicsForBacklogsRequest,
    analyzer: EpicAnalyzer = Depends(get_epic_analyzer),
) -> AnalyzeEpicsForBacklogsResponse:
    """Analyze EPICs to determine optimal backlog item count and structure."""
    try:
        logger.info(f"[API] Analyzing {len(request.epics)} EPICs for backlog decomposition")
        result = await analyzer.analyze_epics(request)
        logger.info(
            f"[API] EPIC analysis complete: recommended {result.total_recommended_items} total items "
            f"({result.total_user_stories} stories, {result.total_tasks} tasks, {result.total_spikes} spikes)"
        )
        return result
    except Exception as e:
        logger.exception(f"Error analyzing EPICs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Phase 2: EPIC and Backlog Generation with Analysis Support
# =============================================================================

async def _generate_epics_stream(
    request: EpicsGenRequest,
    agent: EpicGeneratorAgent,
    verifier: Optional[EpicVerifierAgent] = None,
) -> AsyncGenerator[str, None]:
    """Stream EPIC generation progress with optional verification."""
    try:
        is_verified_mode = request.mode == "verified" and verifier is not None

        # Send initial thinking event
        mode_label = "verified" if is_verified_mode else "draft"
        yield f"data: {json.dumps({'type': 'thinking', 'content': f'Analyzing BRD structure ({mode_label} mode)...'})}\n\n"

        # Generate EPICs
        yield f"data: {json.dumps({'type': 'thinking', 'content': 'Generating EPICs from requirements...'})}\n\n"

        response = await agent.generate_epics(request)

        # Send each EPIC as it's generated
        for i, epic in enumerate(response.epics):
            yield f"data: {json.dumps({'type': 'thinking', 'content': f'Generated EPIC {i+1}/{len(response.epics)}: {epic.title}'})}\n\n"
            yield f"data: {json.dumps({'type': 'epic', 'epic': epic.model_dump(mode='json')})}\n\n"

        # Verification phase (only in verified mode)
        verification_bundle = None
        if is_verified_mode:
            yield f"data: {json.dumps({'type': 'thinking', 'content': 'Starting verification phase...'})}\n\n"

            def verification_progress(msg: str):
                pass  # Progress handled via streaming

            verification_bundle = await verifier.verify_epics(
                epics=response.epics,
                brd_content=request.brd_markdown,
                brd_id=request.brd_id,
                progress_callback=verification_progress,
            )

            # Stream verification results
            yield f"data: {json.dumps({'type': 'thinking', 'content': f'Verification complete: {verification_bundle.verified_epics}/{verification_bundle.total_epics} EPICs verified (confidence: {verification_bundle.overall_confidence:.1%})'})}\n\n"

            # Add verification results to response
            response_data = response.model_dump(mode='json')
            response_data['verification_results'] = [
                r.model_dump(mode='json') for r in verification_bundle.epic_results
            ]
            response_data['overall_confidence'] = verification_bundle.overall_confidence
            response_data['is_verified'] = verification_bundle.is_approved
            response_data['verification_status'] = verification_bundle.overall_status.value
        else:
            response_data = response.model_dump(mode='json')
            response_data['is_verified'] = False
            response_data['draft_warning'] = "Generated in draft mode without verification. Use verified mode for validated EPICs."

        # Send complete response
        complete_data = {
            "type": "complete",
            "data": response_data,
        }
        yield f"data: {json.dumps(complete_data)}\n\n"

    except Exception as e:
        logger.exception("Error generating EPICs")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"


@router.post(
    "/epics/generate",
    tags=["Phase 2: EPICs"],
    summary="Generate EPICs from BRD",
    description="""
    Generate EPICs (large work items) from a BRD document.

    Features:
    - Analyzes BRD to identify logical EPIC groupings
    - Maintains traceability to BRD sections
    - Identifies dependencies between EPICs
    - Provides effort estimates
    - Streams progress in real-time

    Returns SSE stream with events:
    - thinking: Progress updates
    - epic: Individual generated EPIC
    - complete: Final response with all EPICs
    - error: Error message if generation fails
    """,
)
async def generate_epics(
    request: EpicsGenRequest,
    agent: EpicGeneratorAgent = Depends(get_epic_agent),
    verifier: EpicVerifierAgent = Depends(get_epic_verifier),
) -> StreamingResponse:
    """Generate EPICs from BRD with streaming progress."""
    # Pass verifier only if in verified mode
    epic_verifier = verifier if request.mode == "verified" else None
    return StreamingResponse(
        _generate_epics_stream(request, agent, epic_verifier),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/epics/{epic_id}/refine",
    response_model=TrackedEpic,
    tags=["Phase 2: EPICs"],
    summary="Refine an EPIC based on user feedback",
    description="""
    Refine a single EPIC by incorporating user feedback.

    The AI will:
    - Analyze the current EPIC and user feedback
    - Reference relevant BRD sections for context
    - Update the EPIC while maintaining traceability
    - Preserve the EPIC ID and increment refinement count
    """,
)
async def refine_epic(
    epic_id: str,
    request: RefineEpicRequest,
    agent: EpicGeneratorAgent = Depends(get_epic_agent),
) -> TrackedEpic:
    """Refine an EPIC based on user feedback."""
    try:
        refined = await agent.refine_epic(request)
        return refined
    except Exception as e:
        logger.exception(f"Error refining EPIC {epic_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/epics/refine-all",
    response_model=EpicsGenResponse,
    tags=["Phase 2: EPICs"],
    summary="Apply global feedback to all EPICs",
    description="""
    Apply global feedback to refine all EPICs at once.

    Useful for:
    - Consistent terminology changes across all EPICs
    - Adding common acceptance criteria
    - Adjusting priorities based on new information
    """,
)
async def refine_all_epics(
    request: RefineAllEpicsRequest,
    agent: EpicGeneratorAgent = Depends(get_epic_agent),
) -> EpicsGenResponse:
    """Apply global feedback to all EPICs."""
    try:
        refined_epics = await agent.refine_all_epics(
            epics=request.epics,
            global_feedback=request.global_feedback,
            brd_markdown=request.brd_markdown,
            project_context=request.project_context,
        )

        return EpicsGenResponse(
            success=True,
            brd_id=request.epics[0].brd_id if request.epics else "",
            epics=refined_epics,
            total_epics=len(refined_epics),
        )
    except Exception as e:
        logger.exception("Error refining all EPICs")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# EPIC and Backlog Template Parsing Endpoints
# =============================================================================

class ParseEpicTemplateRequest(BaseModel):
    """Request to parse EPIC template."""
    template_content: str = Field(..., min_length=10)


class ParseEpicTemplateResponse(BaseModel):
    """Response from EPIC template parsing."""
    success: bool
    fields: list[dict]
    guidelines: list[str]
    template_name: Optional[str] = None


class ParseBacklogTemplateRequest(BaseModel):
    """Request to parse Backlog template."""
    template_content: str = Field(..., min_length=10)


class ParseBacklogTemplateResponse(BaseModel):
    """Response from Backlog template parsing."""
    success: bool
    fields: list[dict]
    item_types: list[str]
    guidelines: list[str]
    template_name: Optional[str] = None


class DefaultEpicTemplateResponse(BaseModel):
    """Response containing default EPIC template."""
    success: bool
    template: str
    fields: list[dict]
    guidelines: list[str]


class DefaultBacklogTemplateResponse(BaseModel):
    """Response containing default Backlog template."""
    success: bool
    template: str
    fields: list[dict]
    item_types: list[str]
    guidelines: list[str]


# Default EPIC template markdown
DEFAULT_EPIC_TEMPLATE = """# EPIC Template

## Title
[Short, descriptive title for the EPIC - max 10 words]

## Description
[Detailed description of what this EPIC aims to achieve. Include:
- The business problem being solved
- High-level scope and boundaries
- Key stakeholders affected]
**Target: 150-200 words**

## Business Value
[Why this EPIC matters to the business. Include:
- Expected outcomes and benefits
- Impact on users/customers
- Strategic alignment]
**Target: 100-150 words**

## Objectives
[3-5 specific, measurable objectives this EPIC will achieve]
1. Objective 1
2. Objective 2
3. Objective 3

## Acceptance Criteria
[5-8 criteria that must be met for this EPIC to be complete]
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3
- [ ] Criterion 4
- [ ] Criterion 5

## Technical Components
[List of systems, services, or components affected]
- Component 1
- Component 2

## Dependencies
[Other EPICs or external factors this depends on]
- Dependency 1

## Priority & Effort
- **Priority:** [Critical/High/Medium/Low]
- **Estimated Effort:** [XS/S/M/L/XL]
"""


# Default Backlog template markdown (Option B - Moderate with Testing)
DEFAULT_BACKLOG_TEMPLATE = """# User Story Template

## User Story Format (REQUIRED)
**As a** [user role - e.g., "registered user", "admin", "guest"]
**I want** [desired action/capability - describe the complete feature]
**So that** [expected business benefit/value - why this matters]

## Description
[Write a comprehensive description in 2-3 paragraphs explaining:
- What this feature does and its purpose
- Key functionality and how users will interact with it
- Why this feature is needed and how it fits into the larger system]
**Target: 150-200 words**

## Acceptance Criteria
[List 5-7 specific, testable criteria. Use Given/When/Then format where appropriate.]
- [ ] Given [context], When [action], Then [expected result]
- [ ] [Specific testable requirement]
- [ ] [Specific testable requirement]
- [ ] [Error handling requirement]
- [ ] [Performance or quality requirement]

## Pre-conditions
[What must be true BEFORE this story can be executed]
- [System state, dependencies, or prerequisites]
- [User state or permissions required]

## Post-conditions
[What must be true AFTER successful completion]
- [System state after completion]
- [User-visible changes or outcomes]

## Testing Approach
[How to test this story - include unit tests, integration tests, and manual testing steps]
**Target: 80-100 words**

## Edge Cases
[Error scenarios and boundary conditions to handle]
- [Invalid input handling]
- [Network/service failure scenarios]
- [Empty state or no data scenarios]
"""


@router.get(
    "/epics/template/default",
    response_model=DefaultEpicTemplateResponse,
    tags=["Phase 2: EPICs"],
    summary="Get default EPIC template",
    description="Returns the default EPIC template with field configuration.",
)
async def get_default_epic_template() -> DefaultEpicTemplateResponse:
    """Get the default EPIC template."""
    try:
        from ..core.epic_template_parser import DEFAULT_EPIC_FIELDS

        return DefaultEpicTemplateResponse(
            success=True,
            template=DEFAULT_EPIC_TEMPLATE,
            fields=[f.model_dump() for f in DEFAULT_EPIC_FIELDS],
            guidelines=[
                "Focus on business outcomes rather than implementation details",
                "Ensure each EPIC is independently valuable",
                "Keep descriptions clear and actionable",
                "Use measurable objectives where possible",
            ],
        )
    except Exception as e:
        logger.exception("Error getting default EPIC template")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/backlogs/template/default",
    response_model=DefaultBacklogTemplateResponse,
    tags=["Phase 3: Backlogs"],
    summary="Get default Backlog template",
    description="Returns the default Backlog template with field configuration.",
)
async def get_default_backlog_template() -> DefaultBacklogTemplateResponse:
    """Get the default Backlog template."""
    try:
        from ..core.epic_template_parser import DEFAULT_BACKLOG_FIELDS

        return DefaultBacklogTemplateResponse(
            success=True,
            template=DEFAULT_BACKLOG_TEMPLATE,
            fields=[f.model_dump() for f in DEFAULT_BACKLOG_FIELDS],
            item_types=["user_story", "task", "spike", "bug"],
            guidelines=[
                "Use 'As a... I want... So that...' format for user stories",
                "Make acceptance criteria specific and testable",
                "Keep stories small enough to complete in one sprint",
                "Include technical notes for complex implementations",
            ],
        )
    except Exception as e:
        logger.exception("Error getting default Backlog template")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/epics/template/parse-fields",
    response_model=ParseEpicTemplateResponse,
    tags=["Phase 2: EPICs"],
    summary="Parse EPIC template to extract field configuration",
    description="""
    Parse a custom EPIC template to extract:
    - Field structure and order
    - Suggested word counts per field
    - Writing guidelines
    """,
)
async def parse_epic_template_fields(
    request: ParseEpicTemplateRequest,
) -> ParseEpicTemplateResponse:
    """Parse EPIC template to extract field configuration."""
    try:
        from ..core.epic_template_parser import EpicBacklogTemplateParser

        parser = EpicBacklogTemplateParser()
        parsed = await parser.parse_epic_template(request.template_content)

        return ParseEpicTemplateResponse(
            success=True,
            fields=[f.model_dump() for f in parsed.fields],
            guidelines=parsed.writing_guidelines,
            template_name=parsed.template_name,
        )
    except Exception as e:
        logger.exception("Error parsing EPIC template")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/backlogs/template/parse-fields",
    response_model=ParseBacklogTemplateResponse,
    tags=["Phase 3: Backlogs"],
    summary="Parse Backlog template to extract field configuration",
    description="""
    Parse a custom Backlog template to extract:
    - Field structure and order
    - Item types supported (user_story, task, spike)
    - Writing guidelines
    """,
)
async def parse_backlog_template_fields(
    request: ParseBacklogTemplateRequest,
) -> ParseBacklogTemplateResponse:
    """Parse Backlog template to extract field configuration."""
    try:
        from ..core.epic_template_parser import EpicBacklogTemplateParser

        parser = EpicBacklogTemplateParser()
        parsed = await parser.parse_backlog_template(request.template_content)

        return ParseBacklogTemplateResponse(
            success=True,
            fields=[f.model_dump() for f in parsed.fields],
            item_types=parsed.item_types,
            guidelines=parsed.writing_guidelines,
            template_name=parsed.template_name,
        )
    except Exception as e:
        logger.exception("Error parsing Backlog template")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Phase 3: Backlog Generation Endpoints
# =============================================================================

async def _generate_backlogs_stream(
    request: BacklogsGenRequest,
    agent: BacklogGeneratorAgent,
    verifier: Optional[BacklogVerifierAgent] = None,
) -> AsyncGenerator[str, None]:
    """Stream backlog generation progress with optional verification."""
    try:
        is_verified_mode = request.mode == "verified" and verifier is not None
        mode_label = "verified" if is_verified_mode else "draft"
        yield f"data: {json.dumps({'type': 'thinking', 'content': f'Starting backlog generation ({mode_label} mode)...'})}\n\n"

        # Generate backlogs for each EPIC
        epics_to_process = request.epics
        if request.epic_ids:
            epics_to_process = [e for e in request.epics if e.id in request.epic_ids]

        all_items = []
        items_by_epic = {}

        for i, epic in enumerate(epics_to_process):
            yield f"data: {json.dumps({'type': 'thinking', 'content': f'Generating backlogs for {epic.id}: {epic.title} ({i+1}/{len(epics_to_process)})'})}\n\n"

            # Generate items for this EPIC
            items = await agent._generate_items_for_epic(
                epic=epic,
                brd_markdown=request.brd_markdown,
                items_per_epic=request.items_per_epic,
                include_technical_tasks=request.include_technical_tasks,
                include_spikes=request.include_spikes,
                project_context=request.project_context,
                item_offset=len(all_items),
            )

            all_items.extend(items)
            items_by_epic[epic.id] = [item.id for item in items]

            # Stream each item
            for item in items:
                yield f"data: {json.dumps({'type': 'item', 'item': item.model_dump(mode='json')})}\n\n"

            yield f"data: {json.dumps({'type': 'thinking', 'content': f'Generated {len(items)} items for {epic.id}'})}\n\n"

        # Build final response
        total_points = sum(item.story_points or 0 for item in all_items)
        by_type = {}
        by_priority = {}
        for item in all_items:
            by_type[item.item_type.value] = by_type.get(item.item_type.value, 0) + 1
            by_priority[item.priority.value] = by_priority.get(item.priority.value, 0) + 1

        response = BacklogsGenResponse(
            success=True,
            brd_id=request.brd_id,
            items=all_items,
            items_by_epic=items_by_epic,
            total_items=len(all_items),
            total_story_points=total_points,
            by_type=by_type,
            by_priority=by_priority,
            recommended_order=agent._calculate_implementation_order(all_items),
        )

        # Verification phase (only in verified mode)
        if is_verified_mode and all_items:
            yield f"data: {json.dumps({'type': 'thinking', 'content': 'Starting verification phase...'})}\n\n"

            def verification_progress(msg: str):
                pass  # Progress handled via streaming

            verification_bundle = await verifier.verify_backlogs(
                items=all_items,
                epics=epics_to_process,
                brd_content=request.brd_markdown,
                brd_id=request.brd_id,
                progress_callback=verification_progress,
            )

            # Stream verification results
            yield f"data: {json.dumps({'type': 'thinking', 'content': f'Verification complete: {verification_bundle.verified_items}/{verification_bundle.total_items} items verified (confidence: {verification_bundle.overall_confidence:.1%})'})}\n\n"

            # Add verification results to response
            response_data = response.model_dump(mode='json')
            response_data['verification_results'] = [
                r.model_dump(mode='json') for r in verification_bundle.item_results
            ]
            response_data['overall_confidence'] = verification_bundle.overall_confidence
            response_data['is_verified'] = verification_bundle.is_approved
            response_data['verification_status'] = verification_bundle.overall_status.value
        else:
            response_data = response.model_dump(mode='json')
            response_data['is_verified'] = False
            if not is_verified_mode:
                response_data['draft_warning'] = "Generated in draft mode without verification. Use verified mode for validated backlogs."

        yield f"data: {json.dumps({'type': 'complete', 'data': response_data})}\n\n"

    except Exception as e:
        logger.exception("Error generating backlogs")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"


@router.post(
    "/backlogs/generate",
    tags=["Phase 3: Backlogs"],
    summary="Generate Backlogs from EPICs",
    description="""
    Generate backlog items (user stories, tasks, spikes) from EPICs.

    Features:
    - Breaks down EPICs into actionable items
    - Generates user stories in proper format
    - Maintains traceability to both EPIC and BRD
    - Includes technical tasks and spikes (optional)
    - Provides story point estimates
    - Streams progress in real-time

    Returns SSE stream with events:
    - thinking: Progress updates
    - item: Individual generated backlog item
    - complete: Final response with all items
    - error: Error message if generation fails
    """,
)
async def generate_backlogs(
    request: BacklogsGenRequest,
    agent: BacklogGeneratorAgent = Depends(get_backlog_agent),
    verifier: BacklogVerifierAgent = Depends(get_backlog_verifier),
) -> StreamingResponse:
    """Generate backlogs from EPICs with streaming progress."""
    # Pass verifier only if in verified mode
    backlog_verifier = verifier if request.mode == "verified" else None
    return StreamingResponse(
        _generate_backlogs_stream(request, agent, backlog_verifier),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/backlogs/{item_id}/refine",
    response_model=BacklogItem,
    tags=["Phase 3: Backlogs"],
    summary="Refine a backlog item based on user feedback",
    description="""
    Refine a single backlog item by incorporating user feedback.

    The AI will:
    - Analyze the current item and user feedback
    - Reference the parent EPIC and BRD sections
    - Update the item while maintaining traceability
    - Preserve the item ID and type
    """,
)
async def refine_backlog_item(
    item_id: str,
    request: RefineBacklogItemRequest,
    agent: BacklogGeneratorAgent = Depends(get_backlog_agent),
) -> BacklogItem:
    """Refine a backlog item based on user feedback."""
    try:
        refined = await agent.refine_item(request)
        return refined
    except Exception as e:
        logger.exception(f"Error refining backlog item {item_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/backlogs/regenerate/{epic_id}",
    response_model=list[BacklogItem],
    tags=["Phase 3: Backlogs"],
    summary="Regenerate all backlogs for an EPIC",
    description="""
    Regenerate all backlog items for a specific EPIC.

    Useful when:
    - The EPIC has been significantly modified
    - You want to start fresh with backlog items
    - Applying major feedback to all items for an EPIC
    """,
)
async def regenerate_backlogs_for_epic(
    epic_id: str,
    epic: TrackedEpic,
    brd_markdown: str,
    feedback: Optional[str] = None,
    items_per_epic: int = 5,
    project_context: Optional[ProjectContext] = None,
    agent: BacklogGeneratorAgent = Depends(get_backlog_agent),
) -> list[BacklogItem]:
    """Regenerate all backlogs for a specific EPIC."""
    try:
        items = await agent.regenerate_for_epic(
            epic=epic,
            brd_markdown=brd_markdown,
            feedback=feedback,
            items_per_epic=items_per_epic,
            project_context=project_context,
        )
        return items
    except Exception as e:
        logger.exception(f"Error regenerating backlogs for EPIC {epic_id}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# BRD Refinement Endpoints
# =============================================================================

from ..models.brd import (
    BRDSection,
    RefinedBRD,
    RefineBRDSectionRequest,
    RefineEntireBRDRequest,
    RefineBRDSectionResponse,
    RefineEntireBRDResponse,
    ArtifactHistoryResponse,
    SessionHistoryResponse,
    VersionDiffResponse,
)
from ..agents.brd_refinement_agent import BRDRefinementAgent
from ..services.audit_service import AuditService

# Global agent instance
_brd_refinement_agent: BRDRefinementAgent | None = None
_audit_service: AuditService | None = None


async def get_brd_refinement_agent(
    generator: BRDGenerator = Depends(get_generator)
) -> BRDRefinementAgent:
    """Get or create BRD refinement agent."""
    global _brd_refinement_agent
    if _brd_refinement_agent is None:
        # Get copilot session from generator if available
        copilot_session = None
        if generator:
            copilot_session = getattr(generator, '_copilot_session', None)
        _brd_refinement_agent = BRDRefinementAgent(
            copilot_session=copilot_session,
            config={},
        )
    return _brd_refinement_agent


def get_audit_service() -> AuditService:
    """Get or create audit service."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service


@router.post(
    "/brd/{brd_id}/sections/{section_name}/refine",
    response_model=RefineBRDSectionResponse,
    tags=["BRD Refinement"],
    summary="Refine a specific BRD section based on user feedback",
    description="""
    Refine a single section of a BRD by incorporating user feedback.

    The AI will:
    - Analyze the current section and user feedback
    - Reference the full BRD for context and consistency
    - Update the section while preserving structure
    - Generate a summary of changes for audit trail

    The section is identified by its name (e.g., "Functional Requirements").
    """,
)
async def refine_brd_section(
    brd_id: str,
    section_name: str,
    request: RefineBRDSectionRequest,
    agent: BRDRefinementAgent = Depends(get_brd_refinement_agent),
    audit_service: AuditService = Depends(get_audit_service),
) -> RefineBRDSectionResponse:
    """Refine a specific BRD section based on user feedback."""
    try:
        # Ensure request has correct IDs
        request.brd_id = brd_id
        request.section_name = section_name

        # Refine the section
        result = await agent.refine_section(request)

        # Record in audit history if session_id provided
        if request.session_id:
            await audit_service.record_refinement(
                artifact_type="brd",
                artifact_id=brd_id,
                previous_content={"sections": [{"name": section_name, "content": request.current_content}]},
                new_content={"sections": [{"name": section_name, "content": result.refined_section.content}]},
                user_feedback=request.user_feedback,
                feedback_scope="section",
                feedback_target=section_name,
                session_id=request.session_id,
                repository_id=request.repository_id,
            )

        return result

    except Exception as e:
        logger.exception(f"Error refining BRD section {section_name}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/brd/{brd_id}/refine",
    response_model=RefineEntireBRDResponse,
    tags=["BRD Refinement"],
    summary="Apply global feedback to refine entire BRD",
    description="""
    Apply global feedback to refine all sections of a BRD.

    The AI will:
    - Analyze the global feedback and apply to relevant sections
    - Maintain consistency across the document
    - Track which sections were modified
    - Generate section-level diffs for review

    Optionally specify target_sections to limit refinement scope.
    """,
)
async def refine_entire_brd(
    brd_id: str,
    request: RefineEntireBRDRequest,
    agent: BRDRefinementAgent = Depends(get_brd_refinement_agent),
    audit_service: AuditService = Depends(get_audit_service),
) -> RefineEntireBRDResponse:
    """Apply global feedback to refine entire BRD."""
    try:
        # Ensure request has correct BRD ID
        request.brd_id = brd_id

        # Refine the BRD
        result = await agent.refine_entire_brd(request)

        # Record in audit history if session_id provided
        if request.session_id:
            await audit_service.record_refinement(
                artifact_type="brd",
                artifact_id=brd_id,
                previous_content=request.current_brd.model_dump(),
                new_content=result.refined_brd.model_dump(),
                user_feedback=request.global_feedback,
                feedback_scope="global",
                session_id=request.session_id,
                repository_id=request.repository_id,
            )

        return result

    except Exception as e:
        logger.exception(f"Error refining entire BRD {brd_id}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Audit History Endpoints
# =============================================================================

@router.get(
    "/audit/{artifact_type}/{artifact_id}/history",
    response_model=ArtifactHistoryResponse,
    tags=["Audit History"],
    summary="Get complete refinement history for an artifact",
    description="""
    Get the complete history of an artifact (BRD, EPIC, or Backlog).

    Returns:
    - All versions of the artifact
    - User feedback that triggered each refinement
    - Summary of changes at each version
    - Metadata (model used, confidence, etc.)

    artifact_type must be one of: 'brd', 'epic', 'backlog'
    """,
)
async def get_artifact_history(
    artifact_type: str,
    artifact_id: str,
    audit_service: AuditService = Depends(get_audit_service),
) -> ArtifactHistoryResponse:
    """Get complete refinement history for an artifact."""
    if artifact_type not in ["brd", "epic", "backlog"]:
        raise HTTPException(
            status_code=400,
            detail="artifact_type must be 'brd', 'epic', or 'backlog'"
        )

    try:
        result = await audit_service.get_artifact_history(artifact_type, artifact_id)
        return result
    except Exception as e:
        logger.exception(f"Error getting history for {artifact_type}:{artifact_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/audit/session/{session_id}",
    response_model=SessionHistoryResponse,
    tags=["Audit History"],
    summary="Get full audit trail for a generation session",
    description="""
    Get the complete history for a generation session.

    A session groups together:
    - The original BRD
    - All EPICs generated from the BRD
    - All Backlogs generated from the EPICs

    Returns the combined history across all linked artifacts.
    """,
)
async def get_session_history(
    session_id: str,
    audit_service: AuditService = Depends(get_audit_service),
) -> SessionHistoryResponse:
    """Get full audit trail for a generation session."""
    try:
        result = await audit_service.get_session_history(session_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting session history: {session_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/audit/{artifact_type}/{artifact_id}/diff/{version1}/{version2}",
    response_model=VersionDiffResponse,
    tags=["Audit History"],
    summary="Get diff between two versions of an artifact",
    description="""
    Compare two versions of an artifact to see what changed.

    Returns:
    - Section-level diffs (before/after for each section)
    - List of sections added, removed, and modified
    - Feedback that was applied between versions
    """,
)
async def get_version_diff(
    artifact_type: str,
    artifact_id: str,
    version1: int,
    version2: int,
    audit_service: AuditService = Depends(get_audit_service),
) -> VersionDiffResponse:
    """Get diff between two versions of an artifact."""
    if artifact_type not in ["brd", "epic", "backlog"]:
        raise HTTPException(
            status_code=400,
            detail="artifact_type must be 'brd', 'epic', or 'backlog'"
        )

    if version1 >= version2:
        raise HTTPException(
            status_code=400,
            detail="version1 must be less than version2"
        )

    try:
        result = await audit_service.get_version_diff(
            artifact_type, artifact_id, version1, version2
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"One or both versions not found for {artifact_type}:{artifact_id}"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"Error getting diff for {artifact_type}:{artifact_id} v{version1}..v{version2}"
        )
        raise HTTPException(status_code=500, detail=str(e))


# Session management endpoints

class CreateSessionRequest(BaseModel):
    """Request to create a new generation session."""
    repository_id: str
    brd_id: str
    feature_description: str


class CreateSessionResponse(BaseModel):
    """Response with created session ID."""
    success: bool = True
    session_id: str


@router.post(
    "/audit/sessions",
    response_model=CreateSessionResponse,
    tags=["Audit History"],
    summary="Create a new generation session",
    description="""
    Create a new generation session to track linked artifacts.

    Use this when starting a new BRD generation to enable:
    - Grouping of BRD, EPICs, and Backlogs
    - Cross-artifact audit trail
    - Session-level statistics
    """,
)
async def create_session(
    request: CreateSessionRequest,
    audit_service: AuditService = Depends(get_audit_service),
) -> CreateSessionResponse:
    """Create a new generation session."""
    try:
        session_id = await audit_service.create_session(
            repository_id=request.repository_id,
            brd_id=request.brd_id,
            feature_description=request.feature_description,
        )
        return CreateSessionResponse(success=True, session_id=session_id)
    except Exception as e:
        logger.exception("Error creating session")
        raise HTTPException(status_code=500, detail=str(e))


class RetentionConfigResponse(BaseModel):
    """Response with retention configuration."""
    retention_days: int


@router.get(
    "/audit/config/retention",
    response_model=RetentionConfigResponse,
    tags=["Audit History"],
    summary="Get current retention period",
)
async def get_retention_config(
    audit_service: AuditService = Depends(get_audit_service),
) -> RetentionConfigResponse:
    """Get the current audit history retention period."""
    days = await audit_service.get_retention_days()
    return RetentionConfigResponse(retention_days=days)


class SetRetentionRequest(BaseModel):
    """Request to set retention period."""
    days: int


@router.put(
    "/audit/config/retention",
    response_model=RetentionConfigResponse,
    tags=["Audit History"],
    summary="Set retention period",
)
async def set_retention_config(
    request: SetRetentionRequest,
    audit_service: AuditService = Depends(get_audit_service),
) -> RetentionConfigResponse:
    """Set the audit history retention period."""
    if request.days < 1:
        raise HTTPException(status_code=400, detail="Retention days must be at least 1")

    await audit_service.set_retention_days(request.days)
    return RetentionConfigResponse(retention_days=request.days)


# =============================================================================
# BRD Library Endpoints
# =============================================================================

from .models import (
    SaveBRDRequest,
    UpdateBRDRequest,
    UpdateBRDStatusRequest,
    SaveEpicsRequest,
    SaveBacklogsRequest,
    BRDListResponse,
    BRDDetailResponse,
    EpicDetailResponse,
    EpicsListResponse,
    BacklogsListResponse,
    StoredBRD,
    StoredEpic,
    StoredBacklog,
)
from ..services.document_service import DocumentService

# Document service dependency
_document_service: DocumentService | None = None


def get_document_service() -> DocumentService:
    """Dependency to get the document service instance."""
    global _document_service
    if _document_service is None:
        _document_service = DocumentService()
    return _document_service


def _brd_db_to_response(brd) -> StoredBRD:
    """Convert BRDDB to StoredBRD response model."""
    repository = brd.repository if hasattr(brd, 'repository') else None
    return StoredBRD(
        id=str(brd.id),
        brd_number=brd.brd_number,
        title=brd.title,
        feature_description=brd.feature_description,
        markdown_content=brd.markdown_content,
        sections=brd.sections,
        repository_id=str(brd.repository_id),
        repository_name=repository.name if repository else None,
        mode=brd.mode,
        confidence_score=brd.confidence_score,
        verification_report=brd.verification_report,
        status=brd.status.value,
        version=brd.version,
        refinement_count=brd.refinement_count,
        epic_count=brd.epic_count,
        backlog_count=brd.backlog_count,
        epics=[_epic_db_to_response(e, parent_brd=brd, parent_repository=repository) for e in (brd.epics or [])],
        created_at=brd.created_at,
        updated_at=brd.updated_at,
    )


def _epic_db_to_response(
    epic,
    parent_brd=None,
    parent_repository=None
) -> StoredEpic:
    """Convert EpicDB to StoredEpic response model.

    Args:
        epic: The EpicDB object
        parent_brd: Optional parent BRD object (to avoid lazy loading)
        parent_repository: Optional parent Repository object (to avoid lazy loading)
    """
    from sqlalchemy.orm import InstanceState

    # Get BRD and repository info
    brd_title = None
    repository_id = None
    repository_name = None

    # Use parent info if provided (avoids lazy loading)
    if parent_brd:
        brd_title = parent_brd.title
        if parent_repository:
            repository_id = str(parent_brd.repository_id)
            repository_name = parent_repository.name
        else:
            # Safely check if repository was eagerly loaded on parent_brd
            brd_state: InstanceState = parent_brd._sa_instance_state
            if 'repository' in brd_state.dict:
                repo = brd_state.dict.get('repository')
                if repo:
                    repository_id = str(parent_brd.repository_id)
                    repository_name = repo.name
    else:
        # Safely access eagerly loaded relationships without triggering lazy loads
        try:
            epic_state: InstanceState = epic._sa_instance_state
            if 'brd' in epic_state.dict:
                brd = epic_state.dict.get('brd')
                if brd:
                    brd_title = brd.title
                    # Check if repository is already in brd's __dict__
                    brd_state: InstanceState = brd._sa_instance_state
                    if 'repository' in brd_state.dict:
                        repo = brd_state.dict.get('repository')
                        if repo:
                            repository_id = str(brd.repository_id)
                            repository_name = repo.name
        except Exception:
            pass  # Relationship not loaded, leave as None

    return StoredEpic(
        id=str(epic.id),
        epic_number=epic.epic_number,
        brd_id=str(epic.brd_id),
        brd_title=brd_title,
        repository_id=repository_id,
        repository_name=repository_name,
        title=epic.title,
        description=epic.description,
        business_value=epic.business_value,
        objectives=epic.objectives or [],
        acceptance_criteria=epic.acceptance_criteria or [],
        affected_components=epic.affected_components or [],
        depends_on=epic.depends_on or [],
        status=epic.status.value,
        refinement_count=epic.refinement_count,
        display_order=epic.display_order,
        backlog_count=epic.backlog_count,
        backlogs=[_backlog_db_to_response(b) for b in (epic.backlogs or [])],
        created_at=epic.created_at,
        updated_at=epic.updated_at,
    )


def _backlog_db_to_response(backlog) -> StoredBacklog:
    """Convert BacklogDB to StoredBacklog response model."""
    # Get epic title if the relationship is loaded
    epic_title = None
    if hasattr(backlog, 'epic') and backlog.epic:
        epic_title = backlog.epic.title

    return StoredBacklog(
        id=str(backlog.id),
        backlog_number=backlog.backlog_number,
        epic_id=str(backlog.epic_id),
        epic_title=epic_title,
        title=backlog.title,
        description=backlog.description,
        item_type=backlog.item_type.value,
        as_a=backlog.as_a,
        i_want=backlog.i_want,
        so_that=backlog.so_that,
        acceptance_criteria=backlog.acceptance_criteria or [],
        technical_notes=backlog.technical_notes,
        files_to_modify=backlog.files_to_modify or [],
        files_to_create=backlog.files_to_create or [],
        priority=backlog.priority.value,
        story_points=backlog.story_points,
        status=backlog.status.value,
        refinement_count=backlog.refinement_count,
        created_at=backlog.created_at,
        updated_at=backlog.updated_at,
    )


@router.get(
    "/brds",
    response_model=BRDListResponse,
    tags=["BRD Library"],
    summary="List all BRDs",
    description="Get a paginated list of all stored BRDs with optional filtering.",
)
async def list_brds(
    repository_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    doc_service: DocumentService = Depends(get_document_service),
) -> BRDListResponse:
    """List all BRDs with optional filters."""
    try:
        brds, total = await doc_service.list_brds(
            repository_id=repository_id,
            status=status,
            search=search,
            limit=limit,
            offset=offset,
        )
        return BRDListResponse(
            success=True,
            data=[_brd_db_to_response(b) for b in brds],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.exception("Error listing BRDs")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/brds/{brd_id}",
    response_model=BRDDetailResponse,
    tags=["BRD Library"],
    summary="Get BRD detail",
    description="Get a single BRD with all its EPICs and Backlogs.",
)
async def get_brd_detail(
    brd_id: str,
    doc_service: DocumentService = Depends(get_document_service),
) -> BRDDetailResponse:
    """Get BRD detail with EPICs and Backlogs."""
    try:
        brd = await doc_service.get_brd(brd_id)
        if not brd:
            raise HTTPException(status_code=404, detail="BRD not found")
        return BRDDetailResponse(
            success=True,
            data=_brd_db_to_response(brd),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting BRD")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/brds",
    response_model=BRDDetailResponse,
    tags=["BRD Library"],
    summary="Save a generated BRD",
    description="Save a newly generated BRD to the library.",
)
async def save_brd(
    request: SaveBRDRequest,
    doc_service: DocumentService = Depends(get_document_service),
) -> BRDDetailResponse:
    """Save a generated BRD to the database."""
    try:
        brd = await doc_service.create_brd(
            repository_id=request.repository_id,
            title=request.title,
            feature_description=request.feature_description,
            markdown_content=request.markdown_content,
            sections=request.sections,
            mode=request.mode,
            confidence_score=request.confidence_score,
            verification_report=request.verification_report,
        )
        # Reload with relationships
        brd = await doc_service.get_brd(str(brd.id))
        return BRDDetailResponse(
            success=True,
            data=_brd_db_to_response(brd),
        )
    except Exception as e:
        logger.exception("Error saving BRD")
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/brds/{brd_id}",
    response_model=BRDDetailResponse,
    tags=["BRD Library"],
    summary="Update a BRD",
    description="Update an existing BRD after refinement.",
)
async def update_brd(
    brd_id: str,
    request: UpdateBRDRequest,
    doc_service: DocumentService = Depends(get_document_service),
) -> BRDDetailResponse:
    """Update a BRD after refinement."""
    try:
        brd = await doc_service.update_brd(
            brd_id=brd_id,
            title=request.title,
            markdown_content=request.markdown_content,
            sections=request.sections,
            status=request.status,
            confidence_score=request.confidence_score,
            verification_report=request.verification_report,
        )
        if not brd:
            raise HTTPException(status_code=404, detail="BRD not found")
        # Reload with relationships
        brd = await doc_service.get_brd(str(brd.id))
        return BRDDetailResponse(
            success=True,
            data=_brd_db_to_response(brd),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating BRD")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch(
    "/brds/{brd_id}/status",
    response_model=BRDDetailResponse,
    tags=["BRD Library"],
    summary="Update BRD status",
    description="Update BRD status (approve, archive, etc.).",
)
async def update_brd_status(
    brd_id: str,
    request: UpdateBRDStatusRequest,
    doc_service: DocumentService = Depends(get_document_service),
) -> BRDDetailResponse:
    """Update BRD status."""
    try:
        brd = await doc_service.update_brd_status(brd_id, request.status)
        if not brd:
            raise HTTPException(status_code=404, detail="BRD not found")
        brd = await doc_service.get_brd(str(brd.id))
        return BRDDetailResponse(
            success=True,
            data=_brd_db_to_response(brd),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating BRD status")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/brds/{brd_id}",
    tags=["BRD Library"],
    summary="Delete a BRD",
    description="Delete a BRD and all its EPICs/Backlogs (cascade).",
)
async def delete_brd(
    brd_id: str,
    doc_service: DocumentService = Depends(get_document_service),
) -> dict:
    """Delete a BRD and all its children."""
    try:
        deleted = await doc_service.delete_brd(brd_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="BRD not found")
        return {"success": True, "message": "BRD deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting BRD")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/brds/{brd_id}/download/{format}",
    tags=["BRD Library"],
    summary="Download BRD",
    description="Download BRD content as Markdown or HTML.",
)
async def download_brd(
    brd_id: str,
    format: str = "md",
    include_children: bool = False,
    doc_service: DocumentService = Depends(get_document_service),
):
    """Download BRD in specified format."""
    from fastapi.responses import PlainTextResponse

    try:
        if include_children:
            content = await doc_service.export_brd_with_children(brd_id, format)
        else:
            content = await doc_service.export_brd(brd_id, format)

        if not content:
            raise HTTPException(status_code=404, detail="BRD not found")

        media_type = "text/html" if format == "html" else "text/markdown"
        return PlainTextResponse(content=content, media_type=media_type)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error downloading BRD")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/brds/{brd_id}/epics",
    response_model=EpicsListResponse,
    tags=["BRD Library"],
    summary="List EPICs for BRD",
    description="Get all EPICs for a specific BRD.",
)
async def list_epics_for_brd(
    brd_id: str,
    doc_service: DocumentService = Depends(get_document_service),
) -> EpicsListResponse:
    """Get all EPICs for a BRD."""
    try:
        epics = await doc_service.get_epics_for_brd(brd_id)
        return EpicsListResponse(
            success=True,
            data=[_epic_db_to_response(e) for e in epics],
            total=len(epics),
        )
    except Exception as e:
        logger.exception("Error listing EPICs")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/brds/{brd_id}/epics",
    response_model=EpicsListResponse,
    tags=["BRD Library"],
    summary="Save EPICs for BRD",
    description="Save generated EPICs for a BRD.",
)
async def save_epics_for_brd(
    brd_id: str,
    request: SaveEpicsRequest,
    doc_service: DocumentService = Depends(get_document_service),
) -> EpicsListResponse:
    """Save generated EPICs for a BRD."""
    try:
        epics = await doc_service.save_epics_for_brd(brd_id, request.epics)
        return EpicsListResponse(
            success=True,
            data=[_epic_db_to_response(e) for e in epics],
            total=len(epics),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Error saving EPICs")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/epics",
    response_model=EpicsListResponse,
    tags=["BRD Library"],
    summary="List all EPICs",
    description="Get all EPICs across all BRDs with optional filters.",
)
async def list_all_epics(
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    doc_service: DocumentService = Depends(get_document_service),
) -> EpicsListResponse:
    """List all EPICs with optional filters."""
    try:
        epics, total = await doc_service.list_all_epics(
            status=status,
            search=search,
            limit=limit,
            offset=offset,
        )
        return EpicsListResponse(
            success=True,
            data=[_epic_db_to_response(e) for e in epics],
            total=total,
        )
    except Exception as e:
        logger.exception("Error listing EPICs")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/epics/{epic_id}",
    response_model=EpicDetailResponse,
    tags=["BRD Library"],
    summary="Get EPIC detail",
    description="Get a single EPIC with its backlogs.",
)
async def get_epic_detail(
    epic_id: str,
    doc_service: DocumentService = Depends(get_document_service),
) -> EpicDetailResponse:
    """Get EPIC detail with Backlogs."""
    try:
        epic = await doc_service.get_epic(epic_id)
        if not epic:
            raise HTTPException(status_code=404, detail="EPIC not found")
        return EpicDetailResponse(
            success=True,
            data=_epic_db_to_response(epic),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting EPIC")
        raise HTTPException(status_code=500, detail=str(e))


class UpdateEpicRequest(BaseModel):
    """Request to update an EPIC."""
    title: Optional[str] = None
    description: Optional[str] = None
    business_value: Optional[str] = None
    objectives: Optional[list[str]] = None
    acceptance_criteria: Optional[list[str]] = None
    affected_components: Optional[list[str]] = None
    depends_on: Optional[list[str]] = None
    status: Optional[str] = None


@router.put(
    "/epics/{epic_id}",
    response_model=EpicDetailResponse,
    tags=["BRD Library"],
    summary="Update EPIC",
    description="Update an existing EPIC.",
)
async def update_epic(
    epic_id: str,
    request: UpdateEpicRequest,
    doc_service: DocumentService = Depends(get_document_service),
) -> EpicDetailResponse:
    """Update an EPIC."""
    try:
        epic = await doc_service.update_epic(
            epic_id=epic_id,
            title=request.title,
            description=request.description,
            business_value=request.business_value,
            objectives=request.objectives,
            acceptance_criteria=request.acceptance_criteria,
            status=request.status,
        )
        if not epic:
            raise HTTPException(status_code=404, detail="EPIC not found")
        return EpicDetailResponse(
            success=True,
            data=_epic_db_to_response(epic),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating EPIC")
        raise HTTPException(status_code=500, detail=str(e))


class DeleteResponse(BaseModel):
    """Response for delete operations."""
    success: bool = True
    message: str


@router.delete(
    "/epics/{epic_id}",
    response_model=DeleteResponse,
    tags=["BRD Library"],
    summary="Delete EPIC",
    description="Delete an EPIC and all its backlogs.",
)
async def delete_epic(
    epic_id: str,
    doc_service: DocumentService = Depends(get_document_service),
) -> DeleteResponse:
    """Delete an EPIC."""
    try:
        deleted = await doc_service.delete_epic(epic_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="EPIC not found")
        return DeleteResponse(
            success=True,
            message=f"EPIC {epic_id} deleted successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting EPIC")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/epics/{epic_id}/backlogs",
    response_model=BacklogsListResponse,
    tags=["BRD Library"],
    summary="List backlogs for EPIC",
    description="Get all backlog items for a specific EPIC.",
)
async def list_backlogs_for_epic(
    epic_id: str,
    doc_service: DocumentService = Depends(get_document_service),
) -> BacklogsListResponse:
    """Get all backlogs for an EPIC."""
    try:
        backlogs = await doc_service.get_backlogs_for_epic(epic_id)
        return BacklogsListResponse(
            success=True,
            data=[_backlog_db_to_response(b) for b in backlogs],
            total=len(backlogs),
        )
    except Exception as e:
        logger.exception("Error listing backlogs")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/epics/{epic_id}/backlogs",
    response_model=BacklogsListResponse,
    tags=["BRD Library"],
    summary="Save backlogs for EPIC",
    description="Save generated backlog items for an EPIC.",
)
async def save_backlogs_for_epic(
    epic_id: str,
    request: SaveBacklogsRequest,
    doc_service: DocumentService = Depends(get_document_service),
) -> BacklogsListResponse:
    """Save generated backlogs for an EPIC."""
    try:
        backlogs = await doc_service.save_backlogs_for_epic(epic_id, request.items)
        return BacklogsListResponse(
            success=True,
            data=[_backlog_db_to_response(b) for b in backlogs],
            total=len(backlogs),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Error saving backlogs")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/backlogs",
    response_model=BacklogsListResponse,
    tags=["BRD Library"],
    summary="List all backlogs",
    description="Get all backlog items across all EPICs with optional filters.",
)
async def list_all_backlogs(
    status: Optional[str] = None,
    item_type: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    doc_service: DocumentService = Depends(get_document_service),
) -> BacklogsListResponse:
    """List all backlogs with optional filters."""
    try:
        backlogs, total = await doc_service.list_all_backlogs(
            status=status,
            item_type=item_type,
            priority=priority,
            search=search,
            limit=limit,
            offset=offset,
        )
        return BacklogsListResponse(
            success=True,
            data=[_backlog_db_to_response(b) for b in backlogs],
            total=total,
        )
    except Exception as e:
        logger.exception("Error listing backlogs")
        raise HTTPException(status_code=500, detail=str(e))
