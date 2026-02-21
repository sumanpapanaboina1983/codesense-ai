"""API routes for Business Logic Blueprint generation."""

from datetime import datetime
from typing import Optional, List
from enum import Enum

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
import json
import asyncio
import tempfile
import os

from ..services.blueprint_service import get_blueprint_service, BlueprintService
from ..utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/blueprint", tags=["Business Logic Blueprint"])


# =============================================================================
# Request/Response Models
# =============================================================================

class BlueprintFormat(str, Enum):
    """Output format for blueprint document."""
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    DOCX = "docx"


class BlueprintScope(str, Enum):
    """Scope of blueprint generation."""
    FULL = "full"  # Entire codebase
    FEATURE = "feature"  # Single feature
    MENU = "menu"  # Single menu section


class GenerateBlueprintRequest(BaseModel):
    """Request to generate a blueprint."""
    scope: BlueprintScope = Field(BlueprintScope.FULL, description="Scope of generation")
    feature_name: Optional[str] = Field(None, description="Feature name if scope is 'feature'")
    menu_path: Optional[List[str]] = Field(None, description="Menu path for navigation context")
    format: BlueprintFormat = Field(BlueprintFormat.MARKDOWN, description="Output format")
    include_sections: Optional[List[str]] = Field(
        None,
        description="Sections to include (default: all). Options: overview, fields, actions, validations, security, errors"
    )


class BlueprintStatusResponse(BaseModel):
    """Blueprint generation status."""
    status: str
    progress: float
    current_step: Optional[str]
    message: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]


class BlueprintMetadata(BaseModel):
    """Metadata about generated blueprint."""
    repository_id: str
    generated_at: str
    generation_time_seconds: float
    total_menus: int
    total_screens: int
    total_fields: int
    total_rules: int
    sections: int


class BlueprintResponse(BaseModel):
    """Blueprint generation response."""
    success: bool
    document: Optional[str] = None
    metadata: Optional[BlueprintMetadata] = None
    download_url: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None


class FeatureSuggestion(BaseModel):
    """Feature suggestion for search."""
    name: str
    menu_path: List[str]
    screen_count: int


class FeatureListResponse(BaseModel):
    """List of available features."""
    features: List[FeatureSuggestion]
    total: int


# =============================================================================
# Background Job Tracking
# =============================================================================

_generation_jobs: dict = {}


class GenerationJob:
    """Tracks a blueprint generation job."""

    def __init__(self, job_id: str, repository_id: str):
        self.job_id = job_id
        self.repository_id = repository_id
        self.status = "pending"
        self.progress = 0.0
        self.current_step = None
        self.message = None
        self.started_at = datetime.utcnow().isoformat()
        self.completed_at = None
        self.result = None
        self.error = None

    async def update_progress(self, step: str, detail: str):
        """Update job progress."""
        self.current_step = step
        self.message = detail
        self.progress = min(self.progress + 0.1, 0.95)

    def complete(self, result: dict):
        """Mark job as complete."""
        self.status = "completed"
        self.progress = 1.0
        self.result = result
        self.completed_at = datetime.utcnow().isoformat()

    def fail(self, error: str):
        """Mark job as failed."""
        self.status = "failed"
        self.error = error
        self.completed_at = datetime.utcnow().isoformat()


# =============================================================================
# API Endpoints
# =============================================================================

@router.get(
    "/repositories/{repository_id}/features",
    response_model=FeatureListResponse,
    summary="List available features for blueprint generation",
)
async def list_features(repository_id: str):
    """Get list of all features that can be documented."""
    try:
        service = get_blueprint_service()

        # Query for all menu items with screens
        query = """
        MATCH (m:MenuItem)
        WHERE m.menuLevel = 2 OR (m.menuLevel IS NULL AND m.parentMenu IS NOT NULL)
        OPTIONAL MATCH (m)-[:MENU_OPENS_FLOW]->(flow:WebFlowDefinition)
        OPTIONAL MATCH (flow)-[:FLOW_DEFINES_STATE]->(state:FlowState)
        WHERE state.stateType = 'view-state'
        OPTIONAL MATCH (parent:MenuItem)-[:HAS_MENU_ITEM]->(m)

        WITH m, parent, count(DISTINCT state) as screenCount
        RETURN {
            name: m.label,
            menuPath: [parent.label, m.label],
            screenCount: screenCount
        } as feature
        ORDER BY parent.label, m.label
        """

        result = await service.neo4j_client.execute_query(query, {"repositoryId": repository_id})

        features = [
            FeatureSuggestion(
                name=f["name"],
                menu_path=[p for p in f.get("menuPath", []) if p],
                screen_count=f.get("screenCount", 0)
            )
            for f in (result or [])
            if f.get("name")
        ]

        return FeatureListResponse(features=features, total=len(features))

    except Exception as e:
        logger.exception(f"Failed to list features: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/repositories/{repository_id}/generate",
    response_model=BlueprintResponse,
    summary="Generate Business Logic Blueprint",
)
async def generate_blueprint(
    repository_id: str,
    request: GenerateBlueprintRequest,
    background_tasks: BackgroundTasks,
):
    """Generate a Business Logic Blueprint document.

    For full codebase blueprints, this runs in the background.
    Use the /status endpoint to check progress.
    """
    try:
        service = get_blueprint_service()

        if request.scope == BlueprintScope.FULL:
            # Start background generation for full blueprint
            job_id = f"blueprint_{repository_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            job = GenerationJob(job_id, repository_id)
            _generation_jobs[job_id] = job

            background_tasks.add_task(
                _run_full_blueprint_generation,
                job,
                service,
                repository_id,
            )

            return BlueprintResponse(
                success=True,
                message=f"Blueprint generation started. Job ID: {job_id}",
                metadata=None,
            )

        elif request.scope == BlueprintScope.FEATURE:
            if not request.feature_name:
                raise HTTPException(
                    status_code=400,
                    detail="feature_name is required when scope is 'feature'"
                )

            # Generate feature-specific blueprint synchronously
            result = await service.generate_feature_blueprint(
                repository_id=repository_id,
                feature_name=request.feature_name,
                menu_path=request.menu_path,
            )

            if "error" in result:
                return BlueprintResponse(
                    success=False,
                    error=result["error"],
                    document=None,
                )

            return BlueprintResponse(
                success=True,
                document=result.get("document"),
                metadata=BlueprintMetadata(**result.get("metadata", {})) if result.get("metadata") else None,
            )

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported scope: {request.scope}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Blueprint generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/repositories/{repository_id}/generate/stream",
    summary="Generate blueprint with streaming progress",
)
async def generate_blueprint_stream(
    repository_id: str,
    scope: BlueprintScope = Query(BlueprintScope.FULL),
    feature_name: Optional[str] = Query(None),
):
    """Generate blueprint with streaming progress updates (SSE)."""

    async def event_stream():
        """Generate SSE events for blueprint generation progress."""
        try:
            service = get_blueprint_service()

            async def progress_callback(step: str, detail: str):
                event = {
                    "type": "progress",
                    "step": step,
                    "detail": detail,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                yield f"data: {json.dumps(event)}\n\n"

            yield f"data: {json.dumps({'type': 'start', 'scope': scope.value})}\n\n"

            if scope == BlueprintScope.FULL:
                result = await service.generate_full_blueprint(
                    repository_id,
                    progress_callback=progress_callback,
                )
            else:
                result = await service.generate_feature_blueprint(
                    repository_id,
                    feature_name=feature_name or "",
                )

            yield f"data: {json.dumps({'type': 'complete', 'metadata': result.get('metadata')})}\n\n"

            # Send document in chunks for large documents
            document = result.get("document", "")
            chunk_size = 10000
            for i in range(0, len(document), chunk_size):
                chunk = document[i:i + chunk_size]
                yield f"data: {json.dumps({'type': 'document_chunk', 'chunk': chunk, 'index': i // chunk_size})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.exception(f"Blueprint stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get(
    "/jobs/{job_id}/status",
    response_model=BlueprintStatusResponse,
    summary="Check blueprint generation status",
)
async def get_job_status(job_id: str):
    """Get the status of a blueprint generation job."""
    job = _generation_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return BlueprintStatusResponse(
        status=job.status,
        progress=job.progress,
        current_step=job.current_step,
        message=job.message,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.get(
    "/jobs/{job_id}/result",
    response_model=BlueprintResponse,
    summary="Get blueprint generation result",
)
async def get_job_result(job_id: str):
    """Get the result of a completed blueprint generation job."""
    job = _generation_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if job.status == "pending" or job.status == "running":
        raise HTTPException(status_code=202, detail="Job still in progress")

    if job.status == "failed":
        return BlueprintResponse(success=False, error=job.error)

    result = job.result
    return BlueprintResponse(
        success=True,
        document=result.get("document"),
        metadata=BlueprintMetadata(**result.get("metadata", {})) if result.get("metadata") else None,
    )


@router.get(
    "/jobs/{job_id}/download",
    summary="Download generated blueprint",
)
async def download_blueprint(
    job_id: str,
    format: BlueprintFormat = Query(BlueprintFormat.MARKDOWN),
):
    """Download the generated blueprint in specified format."""
    job = _generation_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    document = job.result.get("document", "")

    if format == BlueprintFormat.MARKDOWN:
        # Return as markdown file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(document)
            temp_path = f.name

        return FileResponse(
            temp_path,
            media_type="text/markdown",
            filename=f"business_logic_blueprint_{job.repository_id}.md",
        )

    elif format == BlueprintFormat.HTML:
        # Convert to HTML (simple conversion)
        import markdown
        html_content = markdown.markdown(document, extensions=['tables', 'fenced_code'])
        html_doc = f"""<!DOCTYPE html>
<html>
<head>
    <title>Business Logic Blueprint</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        code {{ background-color: #f4f4f4; padding: 2px 6px; border-radius: 4px; }}
        pre {{ background-color: #f4f4f4; padding: 10px; border-radius: 4px; overflow-x: auto; }}
        h1, h2, h3 {{ color: #333; }}
        h2 {{ border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html_doc)
            temp_path = f.name

        return FileResponse(
            temp_path,
            media_type="text/html",
            filename=f"business_logic_blueprint_{job.repository_id}.html",
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Format {format.value} not yet supported. Use markdown or html."
        )


@router.get(
    "/repositories/{repository_id}/search",
    summary="Search within blueprint",
)
async def search_blueprint(
    repository_id: str,
    q: str = Query(..., min_length=2, description="Search query"),
    scope: str = Query("all", description="Search scope: all, fields, rules, actions"),
    limit: int = Query(20, ge=1, le=100),
):
    """Search for specific content within the blueprint context."""
    try:
        service = get_blueprint_service()

        # Build search query based on scope
        if scope == "fields":
            query = """
            CALL db.index.fulltext.queryNodes('jsp_spring_fulltext_search', $searchTerm)
            YIELD node, score
            WHERE (node:JSPForm OR node:JSPPage)
            RETURN node.name as name, node.kind as type, score
            ORDER BY score DESC
            LIMIT $limit
            """
        elif scope == "rules":
            query = """
            CALL db.index.fulltext.queryNodes('businessrule_fulltext_search', $searchTerm)
            YIELD node, score
            RETURN node.ruleText as name, node.kind as type, score
            ORDER BY score DESC
            LIMIT $limit
            """
        elif scope == "actions":
            query = """
            MATCH (a:FlowAction)
            WHERE a.properties.actionName CONTAINS $searchTerm
               OR a.properties.expression CONTAINS $searchTerm
            RETURN a.properties.actionName as name, 'FlowAction' as type, 1.0 as score
            LIMIT $limit
            """
        else:
            # Search across all
            query = """
            CALL db.index.fulltext.queryNodes('menu_fulltext_search', $searchTerm)
            YIELD node, score
            RETURN node.label as name, labels(node)[0] as type, score
            ORDER BY score DESC
            LIMIT $limit
            """

        result = await service.neo4j_client.execute_query(
            query,
            {"searchTerm": q, "limit": limit}
        )

        return {
            "query": q,
            "scope": scope,
            "results": result or [],
            "total": len(result) if result else 0,
        }

    except Exception as e:
        logger.exception(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Background Task Helper
# =============================================================================

async def _run_full_blueprint_generation(
    job: GenerationJob,
    service: BlueprintService,
    repository_id: str,
):
    """Run full blueprint generation in background."""
    try:
        job.status = "running"

        result = await service.generate_full_blueprint(
            repository_id,
            progress_callback=job.update_progress,
        )

        job.complete(result)
        logger.info(f"Blueprint generation completed for job {job.job_id}")

    except Exception as e:
        logger.exception(f"Blueprint generation failed for job {job.job_id}: {e}")
        job.fail(str(e))
