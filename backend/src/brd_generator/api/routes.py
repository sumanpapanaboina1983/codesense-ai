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
        },
        copilot_available=True,  # Will be updated after init
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
# Phase 1: Generate BRD with Multi-Agent Verification
# =============================================================================

async def _generate_brd_stream(
    repository_id: str,
    request: GenerateBRDRequest,
    generator: BRDGenerator,
) -> AsyncGenerator[str, None]:
    """Generate BRD using multi-agent architecture with verification."""
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

            verified_generator = VerifiedBRDGenerator(
                copilot_session=generator._copilot_session,
                neo4j_client=generator.neo4j_client,
                filesystem_client=repo_filesystem_client,
                max_iterations=request.max_iterations,
                parsed_template=parsed_template,  # Pass parsed template
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
        "agents": "🤖",
        "generator": "📝",
        "verifier": "🔬",
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

    # Build evidence trail summary
    evidence_summary = None
    evidence_text = None

    if evidence_bundle:
        sections_summary = []
        claims_summary = []

        for section in evidence_bundle.sections:
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
        is_verified=evidence_bundle.is_approved if evidence_bundle else False,
        confidence_score=evidence_bundle.overall_confidence if evidence_bundle else 0.0,
        hallucination_risk=evidence_bundle.hallucination_risk.value if evidence_bundle else "unknown",
        iterations_used=evidence_bundle.iteration if evidence_bundle else 0,
        evidence_trail=evidence_summary,
        evidence_trail_text=evidence_text,
        needs_sme_review=len(sme_claims) > 0,
        sme_review_claims=sme_claims,
        metadata={
            **output.metadata,
            "mode": "multi_agent_verified",
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
    summary="Generate BRD with Multi-Agent Verification",
    description="""
    Generate a verified Business Requirements Document for a repository.

    ## Multi-Agent Architecture

    This endpoint uses two specialized agents that work together:

    ### Agent 1: BRD Generator
    - Generates BRD sections iteratively (executive summary, business context, etc.)
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
    - `complete`: Final complete BRD response with verification results
    - `error`: Error messages

    ## Request Parameters

    - `max_iterations`: Maximum verification iterations (default: 3)
    - `min_confidence`: Minimum confidence for approval (default: 0.7)
    - `show_evidence`: Include evidence trail in response (default: false)

    ## Response

    The complete event includes:
    - Verified BRD document
    - Confidence score (0-1)
    - Hallucination risk level
    - Claims needing SME review
    - Evidence trail (if requested)
    """,
)
async def generate_brd(
    repository_id: str,
    request: GenerateBRDRequest,
    generator: BRDGenerator = Depends(get_generator),
) -> StreamingResponse:
    """Generate BRD with multi-agent verification."""
    return StreamingResponse(
        _generate_brd_stream(repository_id, request, generator),
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
    if brd_id not in _evidence_bundles:
        raise HTTPException(status_code=404, detail=f"Evidence trail not found for BRD: {brd_id}")

    evidence_bundle = _evidence_bundles[brd_id]

    if evidence_bundle is None:
        raise HTTPException(status_code=404, detail=f"Evidence bundle is empty for BRD: {brd_id}")

    # Build summary
    sections_summary = []
    for section in evidence_bundle.sections:
        sections_summary.append(SectionSummary(
            section_name=section.section_name,
            status=section.verification_status.value,
            confidence=section.overall_confidence,
            total_claims=section.total_claims,
            verified_claims=section.verified_claims,
            unverified_claims=section.unverified_claims,
            hallucination_risk=section.hallucination_risk.value,
        ))

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
