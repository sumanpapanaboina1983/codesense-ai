"""API Routes for BRD Generator.

Consolidated API with a single unified BRD generation endpoint that
uses multi-agent verification by default.
"""

from __future__ import annotations

import json
import asyncio
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Depends
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
    """Generate BRD using selected approach.

    CONTEXT_FIRST approach:
    - Aggregator gathers context from codebase (Neo4j + Filesystem)
    - Context is explicitly passed to LLM for BRD generation
    - More reliable, context is visible in logs

    SKILLS_ONLY approach:
    - Simple prompt triggers generate-brd skill
    - Skill instructs LLM to use MCP tools directly
    - Faster, single unified session
    """
    from sqlalchemy import select
    from ..models.repository import Repository as RepositorySchema
    from ..core.aggregator import ContextAggregator
    from .models import GenerationApproach

    progress_queue = ProgressQueue()

    async def run_generation():
        try:
            async def progress_callback(step: str, detail: str) -> None:
                await progress_queue.put(step, detail)

            # Determine approach
            approach = request.approach
            if approach == GenerationApproach.AUTO:
                approach = GenerationApproach.SKILLS_ONLY  # Default for draft mode

            approach_name = "Context-First" if approach == GenerationApproach.CONTEXT_FIRST else "Skills-Only"
            await progress_callback("init", f"🚀 Starting BRD generation ({approach_name})...")

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

            workspace_root = Path(repository.local_path) if repository.local_path else generator.workspace_root

            if approach == GenerationApproach.CONTEXT_FIRST:
                # ==========================================
                # CONTEXT-FIRST APPROACH
                # ==========================================
                await progress_callback("context", "📊 Gathering context from codebase...")
                await progress_callback("context", "Using aggregator to query Neo4j and read files")

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

                await progress_callback("context", f"Context ready: {len(context.architecture.components)} components, {len(context.implementation.key_files)} files")

                await progress_callback("generate", f"📝 Generating BRD with gathered context (detail: {request.detail_level.value})...")

                # Convert sections to dict format if provided
                custom_sections = None
                if request.sections:
                    custom_sections = [
                        {"name": s.name, "description": s.description, "required": s.required}
                        for s in request.sections
                    ]

                # Generate BRD with explicit context
                brd = await generator.synthesizer.generate_brd_with_context(
                    context=context,
                    feature_request=request.feature_description,
                    detail_level=request.detail_level.value,
                    custom_sections=custom_sections,
                )

                await repo_filesystem_client.disconnect()

            else:
                # ==========================================
                # SKILLS-ONLY APPROACH
                # ==========================================
                await progress_callback("generate", "📝 Triggering generate-brd skill...")
                await progress_callback("generate", "SDK will use MCP tools to gather context and generate BRD")

                # Use synthesizer's skill-based method
                brd = await generator.synthesizer.generate_brd_with_skill(
                    feature_request=request.feature_description,
                    affected_components=request.affected_components,
                )

            await progress_callback("complete", f"✅ Draft BRD complete: {brd.title}")

            return brd, repository

        except Exception as e:
            logger.exception("Failed to generate BRD (draft mode)")
            await progress_queue.put("error", str(e))
            return None
        finally:
            progress_queue.mark_done()

    # Start generation task
    generation_task = asyncio.create_task(run_generation())

    # Stream progress
    step_icons = {
        "init": "🚀",
        "database": "🗄️",
        "context": "📊",
        "template": "📋",
        "generate": "📝",
        "complete": "✅",
    }

    while not progress_queue.is_done or not generation_task.done():
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

    # Get result
    try:
        result = await generation_task
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        return

    if result is None:
        return

    brd, repository = result

    # Convert to BRD response
    brd_response = _brd_to_response(brd)

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
            "mode": "draft",
            "repository_id": repository.id,
            "repository_name": repository.name,
            "components_found": len(brd.functional_requirements) + len(brd.technical_requirements),
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

            # Convert sections to dict format if provided
            custom_sections_verified = None
            if request.sections:
                custom_sections_verified = [
                    {"name": s.name, "description": s.description, "required": s.required}
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
    }

    while not progress_queue.is_done or not generation_task.done():
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

    # Get result
    try:
        result = await generation_task
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        return

    if result is None:
        return

    output, evidence_bundle, repository = result

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
                        code_refs.append(CodeReferenceItem(
                            file_path=ref.file_path,
                            start_line=ref.start_line,
                            end_line=ref.end_line,
                            snippet=ref.snippet[:200] if ref.snippet else None,
                        ))

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
    # Dispatch based on mode
    if request.mode == GenerationMode.DRAFT:
        stream_generator = _generate_brd_draft_stream(repository_id, request, generator)
    else:
        stream_generator = _generate_brd_verified_stream(repository_id, request, generator)

    return StreamingResponse(
        stream_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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

            # Extract code references from evidence
            code_refs = []
            for ev in claim.evidence:
                for ref in ev.code_references:
                    code_refs.append(CodeReferenceItem(
                        file_path=ref.file_path,
                        start_line=ref.start_line,
                        end_line=ref.end_line,
                        snippet=ref.snippet[:200] if ref.snippet else None,
                    ))

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
    "/epics/generate",
    response_model=GenerateEpicsResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Phase 2: Epics"],
    summary="Generate Epics from approved BRD",
    description="""
    **Phase 2**: Generate Epics from an approved BRD.

    This endpoint takes the approved BRD from Phase 1 and breaks it down into
    Epics that can be delivered in 2-4 weeks each.

    The generated Epics should be reviewed and approved before proceeding to Phase 3.
    """,
)
async def generate_epics(
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
    "/backlogs/generate",
    response_model=GenerateBacklogsResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Phase 3: Backlogs"],
    summary="Generate User Stories from approved Epics",
    description="""
    **Phase 3**: Generate User Stories (Backlogs) from approved Epics.

    This endpoint takes the approved Epics from Phase 2 and the original BRD
    for context, and breaks each Epic into User Stories that can be completed
    in 1-3 days each.

    The generated Stories should be reviewed and approved before proceeding to Phase 4.
    """,
)
async def generate_backlogs(
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
                # Query 1: Basic file and LOC statistics
                file_stats_query = """
                MATCH (f:File)
                WHERE f.repositoryId = $repository_id
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

                # Query 2: Language breakdown
                lang_query = """
                MATCH (f:File)
                WHERE f.repositoryId = $repository_id AND f.language IS NOT NULL
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

                # Query 3: Classes and interfaces
                class_query = """
                MATCH (c)
                WHERE c.repositoryId = $repository_id
                    AND (c:Class OR c:JavaClass OR c:CSharpClass OR c:CppClass OR c:PythonClass)
                RETURN count(c) as count
                """
                class_result = await generator.neo4j_client.query_code_structure(
                    class_query,
                    {"repository_id": repository_id}
                )
                if class_result and class_result.get("nodes"):
                    stats.total_classes = int(class_result["nodes"][0].get("count", 0) or 0)

                interface_query = """
                MATCH (i)
                WHERE i.repositoryId = $repository_id
                    AND (i:Interface OR i:JavaInterface OR i:CSharpInterface OR i:GoInterface)
                RETURN count(i) as count
                """
                interface_result = await generator.neo4j_client.query_code_structure(
                    interface_query,
                    {"repository_id": repository_id}
                )
                if interface_result and interface_result.get("nodes"):
                    stats.total_interfaces = int(interface_result["nodes"][0].get("count", 0) or 0)

                # Query 4: Functions/Methods
                func_query = """
                MATCH (f)
                WHERE f.repositoryId = $repository_id
                    AND (f:Function OR f:Method OR f:PythonFunction OR f:PythonMethod
                         OR f:JavaMethod OR f:CSharpMethod OR f:GoFunction OR f:GoMethod OR f:CFunction)
                RETURN count(f) as count
                """
                func_result = await generator.neo4j_client.query_code_structure(
                    func_query,
                    {"repository_id": repository_id}
                )
                if func_result and func_result.get("nodes"):
                    stats.total_functions = int(func_result["nodes"][0].get("count", 0) or 0)

                # Query 5: UI Components
                component_query = """
                MATCH (c:Component)
                WHERE c.repositoryId = $repository_id
                RETURN count(c) as count
                """
                comp_result = await generator.neo4j_client.query_code_structure(
                    component_query,
                    {"repository_id": repository_id}
                )
                if comp_result and comp_result.get("nodes"):
                    stats.total_components = int(comp_result["nodes"][0].get("count", 0) or 0)
                    stats.ui_components = stats.total_components

                # Query 6: REST Endpoints (check RestEndpoint or SpringController)
                rest_query = """
                MATCH (e)
                WHERE e.repositoryId = $repository_id
                    AND (e:RestEndpoint OR e:SpringController)
                RETURN count(e) as count
                """
                rest_result = await generator.neo4j_client.query_code_structure(
                    rest_query,
                    {"repository_id": repository_id}
                )
                if rest_result and rest_result.get("nodes"):
                    stats.rest_endpoints = int(rest_result["nodes"][0].get("count", 0) or 0)

                # Query 7: GraphQL Operations
                graphql_query = """
                MATCH (g:GraphQLOperation)
                WHERE g.repositoryId = $repository_id
                RETURN count(g) as count
                """
                gql_result = await generator.neo4j_client.query_code_structure(
                    graphql_query,
                    {"repository_id": repository_id}
                )
                if gql_result and gql_result.get("nodes"):
                    stats.graphql_operations = int(gql_result["nodes"][0].get("count", 0) or 0)

                stats.total_api_endpoints = stats.rest_endpoints + stats.graphql_operations

                # Query 8: Test Files (by name pattern or TestFile label)
                test_query = """
                MATCH (f:File)
                WHERE f.repositoryId = $repository_id
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

                # Query 9: Dependencies (external imports/dependencies)
                dep_query = """
                MATCH (d)
                WHERE d.repositoryId = $repository_id
                    AND (d:GradleDependency OR d:MavenDependency OR d:NpmDependency)
                RETURN count(d) as count
                """
                dep_result = await generator.neo4j_client.query_code_structure(
                    dep_query,
                    {"repository_id": repository_id}
                )
                if dep_result and dep_result.get("nodes"):
                    stats.total_dependencies = int(dep_result["nodes"][0].get("count", 0) or 0)

                # If no explicit dependencies, count unique external imports (top-level packages)
                if stats.total_dependencies == 0:
                    import_query = """
                    MATCH (i:ImportDeclaration)
                    WHERE i.repositoryId = $repository_id
                        AND i.importPath IS NOT NULL
                    WITH split(i.importPath, '.')[0] as topPackage
                    WHERE topPackage IS NOT NULL
                        AND NOT topPackage STARTS WITH 'com'
                        AND NOT topPackage STARTS WITH 'org'
                    RETURN count(DISTINCT topPackage) as count
                    """
                    import_result = await generator.neo4j_client.query_code_structure(
                        import_query,
                        {"repository_id": repository_id}
                    )
                    if import_result and import_result.get("nodes"):
                        dep_count = int(import_result["nodes"][0].get("count", 0) or 0)
                        # If still 0, just count unique import packages
                        if dep_count == 0:
                            fallback_query = """
                            MATCH (i:ImportDeclaration)
                            WHERE i.repositoryId = $repository_id
                                AND i.importPath IS NOT NULL
                            WITH split(i.importPath, '.')[0] + '.' + split(i.importPath, '.')[1] as pkg
                            RETURN count(DISTINCT pkg) as count
                            """
                            fallback_result = await generator.neo4j_client.query_code_structure(
                                fallback_query,
                                {"repository_id": repository_id}
                            )
                            if fallback_result and fallback_result.get("nodes"):
                                dep_count = int(fallback_result["nodes"][0].get("count", 0) or 0)
                        stats.total_dependencies = dep_count

                # Query 10: Database Models (SQL tables, Entity classes, or classes with Entity/Table annotation)
                db_query = """
                MATCH (m)
                WHERE m.repositoryId = $repository_id
                    AND (m:SQLTable OR m:Entity
                         OR m.stereotype = 'Entity'
                         OR (m:JavaClass AND (m.name ENDS WITH 'Entity' OR m.name ENDS WITH 'Model')))
                RETURN count(m) as count
                """
                db_result = await generator.neo4j_client.query_code_structure(
                    db_query,
                    {"repository_id": repository_id}
                )
                if db_result and db_result.get("nodes"):
                    stats.total_database_models = int(db_result["nodes"][0].get("count", 0) or 0)

                # Query 11: Complexity Metrics
                complexity_query = """
                MATCH (f)
                WHERE f.repositoryId = $repository_id
                    AND f.complexity IS NOT NULL
                    AND (f:Function OR f:Method)
                RETURN
                    avg(f.complexity) as avg_complexity,
                    max(f.complexity) as max_complexity
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

                # Query 12: Services, Controllers, Repositories
                service_query = """
                MATCH (s)
                WHERE s.repositoryId = $repository_id
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
                MATCH (c)
                WHERE c.repositoryId = $repository_id
                    AND (c:SpringController OR c.stereotype = 'Controller')
                RETURN count(c) as count
                """
                ctrl_result = await generator.neo4j_client.query_code_structure(
                    controller_query,
                    {"repository_id": repository_id}
                )
                if ctrl_result and ctrl_result.get("nodes"):
                    stats.controllers_count = int(ctrl_result["nodes"][0].get("count", 0) or 0)

                repo_query = """
                MATCH (r)
                WHERE r.repositoryId = $repository_id
                    AND r.stereotype = 'Repository'
                RETURN count(r) as count
                """
                repo_result = await generator.neo4j_client.query_code_structure(
                    repo_query,
                    {"repository_id": repository_id}
                )
                if repo_result and repo_result.get("nodes"):
                    stats.repositories_count = int(repo_result["nodes"][0].get("count", 0) or 0)

                # Query 13: UI Routes/Pages (check UIRoute, UIPage, JSPPage, Component)
                route_query = """
                MATCH (r)
                WHERE r.repositoryId = $repository_id
                    AND (r:UIRoute OR r:UIPage OR r:JSPPage OR r:Component)
                RETURN count(r) as count
                """
                route_result = await generator.neo4j_client.query_code_structure(
                    route_query,
                    {"repository_id": repository_id}
                )
                if route_result and route_result.get("nodes"):
                    count = int(route_result["nodes"][0].get("count", 0) or 0)
                    stats.ui_routes = count
                    stats.ui_components = count

                # Query 14: Documentation Coverage
                doc_query = """
                MATCH (f)
                WHERE f.repositoryId = $repository_id
                    AND (f:Function OR f:Method OR f:JavaMethod OR f:Class OR f:JavaClass)
                RETURN
                    count(f) as total,
                    sum(CASE WHEN f.hasDocumentation = true
                             OR (f.javadoc IS NOT NULL AND f.javadoc <> '')
                             OR (f.docstring IS NOT NULL AND f.docstring <> '')
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

                # Query 15: Config Files (XML, properties, yaml, json, etc.)
                config_query = """
                MATCH (f:File)
                WHERE f.repositoryId = $repository_id
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
                MATCH (wf:SpringWebFlow)
                WHERE wf.repositoryId = $repository_id
                OPTIONAL MATCH (wf)-[:HAS_STATE]->(state)
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
                            code_footprint=footprint,
                            has_tests=False,
                        )
                        features.append(feature)

                logger.info(f"[FEATURES] Found {webflow_count} web flows")

                # =========================================================
                # Step 2: Query all JSP pages
                # =========================================================
                logger.info("[FEATURES] Step 2: Querying JSP pages...")
                jsp_query = """
                MATCH (j:JSPPage)
                WHERE j.repositoryId = $repository_id
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
                MATCH (c)
                WHERE c.repositoryId = $repository_id
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

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        return DiscoveredFeaturesResponse(
            success=True,
            repository_id=repository_id,
            repository_name=repository_name,
            generated_at=datetime.now(),
            features=features,
            summary=summary,
            discovery_method="screen-centric",
            discovery_duration_ms=duration_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to discover business features")
        raise HTTPException(status_code=500, detail=str(e))
