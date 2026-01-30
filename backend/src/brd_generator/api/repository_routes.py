"""API Routes for Repository Management.

Provides endpoints for:
- Repository onboarding (metadata capture + clone)
- Repository listing and details
- Analysis triggering (separate from onboarding)
- Analysis status and history
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.config import get_async_session
from ..models.repository import (
    Repository,
    RepositoryCreate,
    RepositoryUpdate,
    RepositorySummary,
    RepositoryPlatform,
    RepositoryStatus,
    AnalysisStatus,
    AnalysisRun,
    AnalysisRunCreate,
    AnalysisRunSummary,
)
from ..services.repository_service import RepositoryService
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/repositories", tags=["Repositories"])

# Global service instance
_repository_service: Optional[RepositoryService] = None


def get_repository_service() -> RepositoryService:
    """Get repository service instance."""
    global _repository_service
    if _repository_service is None:
        _repository_service = RepositoryService()
    return _repository_service


async def get_db_session():
    """Database session dependency."""
    async with get_async_session() as session:
        yield session


# =============================================================================
# Response Models
# =============================================================================

class RepositoryResponse(BaseModel):
    """Single repository response."""
    success: bool = True
    data: Repository


class RepositoryListResponse(BaseModel):
    """Repository list response."""
    success: bool = True
    data: list[RepositorySummary]
    total: int
    limit: int
    offset: int


class AnalysisRunResponse(BaseModel):
    """Single analysis run response."""
    success: bool = True
    data: AnalysisRun


class AnalysisRunListResponse(BaseModel):
    """Analysis run list response."""
    success: bool = True
    data: list[AnalysisRunSummary]


class SyncResponse(BaseModel):
    """Sync response."""
    success: bool = True
    data: Repository
    changes_detected: bool = False
    commits_pulled: int = 0


class DeleteResponse(BaseModel):
    """Delete response."""
    success: bool = True
    message: str


class ErrorResponse(BaseModel):
    """Error response."""
    success: bool = False
    error: str
    detail: Optional[str] = None


# =============================================================================
# Repository Endpoints
# =============================================================================

@router.post(
    "",
    response_model=RepositoryResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="Onboard a new repository",
    description="""
    Onboard a new repository by providing its URL.

    This will:
    1. Validate the URL and detect the platform (GitHub/GitLab)
    2. Fetch repository metadata from the platform API
    3. Store the repository in the database
    4. Start cloning in the background

    The repository will be in `pending` status initially, then `cloning`,
    and finally `cloned` when ready.

    **Note:** This does NOT trigger analysis. Call POST /repositories/{id}/analyze separately.
    """,
)
async def create_repository(
    request: RepositoryCreate,
    service: RepositoryService = Depends(get_repository_service),
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryResponse:
    """Onboard a new repository."""
    try:
        repository = await service.create_repository(request, session)
        return RepositoryResponse(data=repository)

    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create repository")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "",
    response_model=RepositoryListResponse,
    summary="List repositories",
    description="""
    List all onboarded repositories with optional filtering.

    Supports filtering by:
    - `status`: Onboarding status (pending, cloning, cloned, clone_failed)
    - `analysis_status`: Analysis status (not_analyzed, pending, running, completed, failed)
    - `platform`: Platform (github, gitlab)

    Results are paginated with `limit` and `offset`.
    """,
)
async def list_repositories(
    status: Optional[RepositoryStatus] = Query(None, description="Filter by onboarding status"),
    analysis_status: Optional[AnalysisStatus] = Query(None, description="Filter by analysis status"),
    platform: Optional[RepositoryPlatform] = Query(None, description="Filter by platform"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    service: RepositoryService = Depends(get_repository_service),
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryListResponse:
    """List repositories."""
    repos, total = await service.list_repositories(
        session,
        status=status,
        analysis_status=analysis_status,
        platform=platform,
        limit=limit,
        offset=offset,
    )

    return RepositoryListResponse(
        data=repos,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{repository_id}",
    response_model=RepositoryResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get repository details",
    description="Get full details for a specific repository including onboarding and analysis status.",
)
async def get_repository(
    repository_id: str,
    service: RepositoryService = Depends(get_repository_service),
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryResponse:
    """Get repository details."""
    repository = await service.get_repository(repository_id, session)

    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    return RepositoryResponse(data=repository)


@router.patch(
    "/{repository_id}",
    response_model=RepositoryResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Update repository settings",
    description="Update repository settings like auto-analyze on sync.",
)
async def update_repository(
    repository_id: str,
    request: RepositoryUpdate,
    service: RepositoryService = Depends(get_repository_service),
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryResponse:
    """Update repository settings."""
    repository = await service.update_repository(repository_id, request, session)

    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    return RepositoryResponse(data=repository)


@router.delete(
    "/{repository_id}",
    response_model=DeleteResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Delete a repository",
    description="Delete a repository and optionally its local files.",
)
async def delete_repository(
    repository_id: str,
    delete_files: bool = Query(True, description="Delete local clone files"),
    service: RepositoryService = Depends(get_repository_service),
    session: AsyncSession = Depends(get_db_session),
) -> DeleteResponse:
    """Delete a repository."""
    success = await service.delete_repository(repository_id, session, delete_files)

    if not success:
        raise HTTPException(status_code=404, detail="Repository not found")

    return DeleteResponse(message=f"Repository {repository_id} deleted")


# =============================================================================
# Sync Endpoint
# =============================================================================

@router.post(
    "/{repository_id}/sync",
    response_model=SyncResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    summary="Sync repository",
    description="""
    Pull latest changes from the remote repository.

    The repository must be in `cloned` status to sync.
    Use `force=true` to discard local changes.
    """,
)
async def sync_repository(
    repository_id: str,
    force: bool = Query(False, description="Force sync (discard local changes)"),
    service: RepositoryService = Depends(get_repository_service),
    session: AsyncSession = Depends(get_db_session),
) -> SyncResponse:
    """Sync repository."""
    try:
        repository = await service.sync_repository(repository_id, session, force)
        return SyncResponse(
            data=repository,
            changes_detected=True,  # TODO: Get actual value from service
            commits_pulled=0,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to sync repository")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Analysis Endpoints
# =============================================================================

@router.post(
    "/{repository_id}/analyze",
    response_model=AnalysisRunResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    summary="Trigger analysis",
    description="""
    Trigger code analysis for a repository.

    The repository must be in `cloned` status to analyze.

    Analysis is performed asynchronously. Poll the returned analysis run
    or use GET /repositories/{id}/analyses/{analysis_id} to check status.

    Options:
    - `reset_graph`: Reset Neo4j graph before analysis (default: false)
    """,
)
async def trigger_analysis(
    repository_id: str,
    request: AnalysisRunCreate = None,
    service: RepositoryService = Depends(get_repository_service),
    session: AsyncSession = Depends(get_db_session),
) -> AnalysisRunResponse:
    """Trigger analysis for a repository."""
    request = request or AnalysisRunCreate()

    try:
        analysis = await service.trigger_analysis(repository_id, request, session)
        return AnalysisRunResponse(data=analysis)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to trigger analysis")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{repository_id}/analyses",
    response_model=AnalysisRunListResponse,
    responses={404: {"model": ErrorResponse}},
    summary="List analysis runs",
    description="List analysis runs for a repository, ordered by most recent first.",
)
async def list_analysis_runs(
    repository_id: str,
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    service: RepositoryService = Depends(get_repository_service),
    session: AsyncSession = Depends(get_db_session),
) -> AnalysisRunListResponse:
    """List analysis runs for a repository."""
    # Verify repository exists
    repository = await service.get_repository(repository_id, session)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    runs = await service.list_analysis_runs(repository_id, session, limit)
    return AnalysisRunListResponse(data=runs)


@router.get(
    "/{repository_id}/analyses/{analysis_id}",
    response_model=AnalysisRunResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get analysis run details",
    description="Get details of a specific analysis run.",
)
async def get_analysis_run(
    repository_id: str,
    analysis_id: str,
    service: RepositoryService = Depends(get_repository_service),
    session: AsyncSession = Depends(get_db_session),
) -> AnalysisRunResponse:
    """Get analysis run details."""
    analysis = await service.get_analysis_run(analysis_id, session)

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    if analysis.repository_id != repository_id:
        raise HTTPException(status_code=404, detail="Analysis run not found for this repository")

    return AnalysisRunResponse(data=analysis)
