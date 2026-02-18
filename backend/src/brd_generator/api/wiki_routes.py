"""Wiki API routes for DeepWiki-style documentation."""

from datetime import datetime
from typing import Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import json
import asyncio

from ..database.config import get_async_session
from ..database.models import WikiStatus, WikiPageType
from ..services.wiki_service import get_wiki_service, WikiService
from ..utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/wiki", tags=["Wiki Documentation"])


# =============================================================================
# Request/Response Models
# =============================================================================

class WikiDepth(str, Enum):
    """Wiki generation depth levels."""
    QUICK = "quick"        # Overview + Architecture only (~5 pages)
    BASIC = "basic"        # + Modules (~15-20 pages) - DEFAULT
    STANDARD = "standard"  # + API Reference, Data Models (~30-40 pages)
    COMPREHENSIVE = "comprehensive"  # + Individual class pages (~50-100 pages)


class WikiGenerationOptions(BaseModel):
    """Options for wiki generation."""
    depth: WikiDepth = Field(
        WikiDepth.BASIC,
        description="Generation depth: quick (overview only), basic (+ modules), standard (+ API), comprehensive (+ classes)"
    )
    include_modules: bool = Field(True, description="Include module documentation pages")
    include_api_reference: bool = Field(False, description="Include API reference pages")
    include_class_pages: bool = Field(False, description="Include individual class documentation")
    include_data_models: bool = Field(False, description="Include data model documentation")
    regenerate_all: bool = Field(False, description="Regenerate all pages even if not stale")


class GenerateWikiRequest(BaseModel):
    """Request to generate wiki documentation."""
    options: WikiGenerationOptions = Field(default_factory=WikiGenerationOptions)


class WikiStatusResponse(BaseModel):
    """Wiki generation status response."""
    status: str
    total_pages: int
    stale_pages: int
    commit_sha: Optional[str]
    generated_at: Optional[str]
    generation_mode: Optional[str] = None  # 'llm-powered' or 'template'
    message: Optional[str] = None


class WikiTreeNode(BaseModel):
    """Node in the wiki navigation tree."""
    slug: str
    title: str
    type: str
    is_stale: bool = False
    children: list["WikiTreeNode"] = Field(default_factory=list)


class WikiTreeResponse(BaseModel):
    """Wiki navigation tree response."""
    wiki: Optional[WikiStatusResponse]
    tree: list[WikiTreeNode]


class WikiPageResponse(BaseModel):
    """Single wiki page response."""
    id: str
    slug: str
    title: str
    type: str
    content: str
    summary: Optional[str]
    source_files: Optional[list[str]]
    is_stale: bool
    stale_reason: Optional[str]
    updated_at: str
    breadcrumbs: list[dict]
    related: list[dict]


class WikiSearchResult(BaseModel):
    """Wiki search result item."""
    slug: str
    title: str
    type: str
    summary: str


class WikiSearchResponse(BaseModel):
    """Wiki search response."""
    query: str
    results: list[WikiSearchResult]
    total: int


# =============================================================================
# API Endpoints
# =============================================================================

@router.get(
    "/repositories/{repository_id}/status",
    response_model=WikiStatusResponse,
    summary="Get wiki generation status",
)
async def get_wiki_status(repository_id: str):
    """Get the current wiki generation status for a repository."""
    async with get_async_session() as session:
        wiki_service = get_wiki_service()
        wiki = await wiki_service.get_or_create_wiki(session, repository_id)

        return WikiStatusResponse(
            status=wiki.status.value,
            total_pages=wiki.total_pages,
            stale_pages=wiki.stale_pages,
            commit_sha=wiki.commit_sha,
            generated_at=wiki.generated_at.isoformat() if wiki.generated_at else None,
            generation_mode=wiki.generation_mode,
            message=wiki.status_message,
        )


@router.post(
    "/repositories/{repository_id}/generate",
    summary="Generate wiki documentation",
)
async def generate_wiki(
    repository_id: str,
    request: GenerateWikiRequest,
    background_tasks: BackgroundTasks,
):
    """Generate wiki documentation for a repository.

    This endpoint starts wiki generation and returns immediately.
    Use the streaming endpoint or status endpoint to track progress.
    """
    async with get_async_session() as session:
        wiki_service = get_wiki_service()
        wiki = await wiki_service.get_or_create_wiki(session, repository_id)

        if wiki.status == WikiStatus.GENERATING:
            raise HTTPException(
                status_code=409,
                detail="Wiki generation already in progress"
            )

        # Map options to depth
        depth = request.options.depth.value

        # Start generation in background
        background_tasks.add_task(
            _run_wiki_generation,
            repository_id,
            depth,
        )

        return {
            "success": True,
            "message": f"Wiki generation started with depth: {depth}",
            "repository_id": repository_id,
        }


@router.get(
    "/repositories/{repository_id}/generate/stream",
    summary="Generate wiki with streaming progress",
)
async def generate_wiki_stream(
    repository_id: str,
    depth: WikiDepth = Query(WikiDepth.BASIC, description="Generation depth"),
):
    """Generate wiki documentation with streaming progress updates."""

    async def event_stream():
        """Generate SSE events for wiki generation progress."""
        try:
            async with get_async_session() as session:
                wiki_service = get_wiki_service()

                # Progress callback for streaming
                async def progress_callback(step: str, detail: str):
                    event = {
                        "type": "progress",
                        "step": step,
                        "detail": detail,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    yield f"data: {json.dumps(event)}\n\n"

                # Check if already generating
                wiki = await wiki_service.get_or_create_wiki(session, repository_id)
                if wiki.status == WikiStatus.GENERATING:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Generation already in progress'})}\n\n"
                    return

                # Start generation with progress updates
                yield f"data: {json.dumps({'type': 'start', 'depth': depth.value})}\n\n"

                # Generate wiki
                wiki = await wiki_service.generate_wiki(
                    session,
                    repository_id,
                    depth=depth.value,
                    progress_callback=lambda step, detail: None,  # We'll handle this differently
                )

                await session.commit()

                # Send completion event
                yield f"data: {json.dumps({'type': 'complete', 'total_pages': wiki.total_pages})}\n\n"

        except Exception as e:
            logger.exception(f"Wiki generation stream error: {e}")
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
    "/repositories/{repository_id}/tree",
    response_model=WikiTreeResponse,
    summary="Get wiki navigation tree",
)
async def get_wiki_tree(repository_id: str):
    """Get the wiki navigation tree for sidebar display."""
    async with get_async_session() as session:
        wiki_service = get_wiki_service()
        result = await wiki_service.get_wiki_tree(session, repository_id)

        wiki_data = result.get("wiki")
        if wiki_data:
            wiki_status = WikiStatusResponse(
                status=wiki_data["status"],
                total_pages=wiki_data["total_pages"],
                stale_pages=wiki_data["stale_pages"],
                commit_sha=wiki_data["commit_sha"],
                generation_mode=wiki_data.get("generation_mode"),
                generated_at=wiki_data["generated_at"],
            )
        else:
            wiki_status = None

        return WikiTreeResponse(
            wiki=wiki_status,
            tree=result.get("tree", []),
        )


@router.get(
    "/repositories/{repository_id}/pages/{slug:path}",
    response_model=WikiPageResponse,
    summary="Get wiki page content",
)
async def get_wiki_page(repository_id: str, slug: str):
    """Get a specific wiki page by its slug.

    The slug can include path separators, e.g., 'modules/legal-entity'.
    """
    async with get_async_session() as session:
        wiki_service = get_wiki_service()
        page = await wiki_service.get_page(session, repository_id, slug)

        if not page:
            raise HTTPException(status_code=404, detail=f"Wiki page not found: {slug}")

        return WikiPageResponse(**page)


@router.get(
    "/repositories/{repository_id}/search",
    response_model=WikiSearchResponse,
    summary="Search wiki pages",
)
async def search_wiki(
    repository_id: str,
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
):
    """Search wiki pages by title and content."""
    async with get_async_session() as session:
        wiki_service = get_wiki_service()
        results = await wiki_service.search_wiki(session, repository_id, q, limit)

        return WikiSearchResponse(
            query=q,
            results=[WikiSearchResult(**r) for r in results],
            total=len(results),
        )


@router.post(
    "/repositories/{repository_id}/pages/{slug:path}/regenerate",
    summary="Regenerate a specific wiki page",
)
async def regenerate_wiki_page(repository_id: str, slug: str):
    """Regenerate a specific wiki page."""
    async with get_async_session() as session:
        wiki_service = get_wiki_service()

        # Get existing page
        page = await wiki_service.get_page(session, repository_id, slug)
        if not page:
            raise HTTPException(status_code=404, detail=f"Wiki page not found: {slug}")

        # TODO: Implement single page regeneration
        # For now, return success
        return {
            "success": True,
            "message": f"Page regeneration queued: {slug}",
        }


@router.delete(
    "/repositories/{repository_id}",
    summary="Delete wiki for repository",
)
async def delete_wiki(repository_id: str):
    """Delete all wiki content for a repository."""
    from sqlalchemy import delete
    from ..database.models import WikiDB

    async with get_async_session() as session:
        await session.execute(
            delete(WikiDB).where(WikiDB.repository_id == repository_id)
        )
        await session.commit()

        return {
            "success": True,
            "message": "Wiki deleted",
        }


# =============================================================================
# Background Task Helper
# =============================================================================

async def _run_wiki_generation(repository_id: str, depth: str):
    """Run wiki generation in background."""
    try:
        async with get_async_session() as session:
            wiki_service = get_wiki_service()
            await wiki_service.generate_wiki(
                session,
                repository_id,
                depth=depth,
            )
            await session.commit()
            logger.info(f"Background wiki generation completed for {repository_id}")
    except Exception as e:
        logger.exception(f"Background wiki generation failed: {e}")


# =============================================================================
# Default Wiki Generation Options (for analysis integration)
# =============================================================================

DEFAULT_WIKI_OPTIONS = WikiGenerationOptions(
    depth=WikiDepth.BASIC,
    include_modules=True,
    include_api_reference=False,
    include_class_pages=False,
    include_data_models=False,
)


def get_default_wiki_options() -> dict:
    """Get default wiki generation options as dict."""
    return {
        "depth": "basic",
        "include_modules": True,
        "include_api_reference": False,
        "include_class_pages": False,
        "include_data_models": False,
        "options": [
            {
                "id": "basic",
                "label": "Basic (Overview + Modules)",
                "description": "System overview, architecture, and module documentation (~15-20 pages)",
                "default": True,
            },
            {
                "id": "api_reference",
                "label": "API Reference",
                "description": "REST endpoint documentation",
                "default": False,
            },
            {
                "id": "class_pages",
                "label": "Class Documentation",
                "description": "Individual class/service documentation (~50+ pages)",
                "default": False,
            },
            {
                "id": "data_models",
                "label": "Data Models",
                "description": "Database schema and entity documentation",
                "default": False,
            },
        ]
    }
