"""API Routes for Repository Management.

Provides endpoints for:
- Repository onboarding (metadata capture + clone)
- Repository listing and details
- Analysis triggering (separate from onboarding)
- Analysis status and history
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ModuleDependenciesResponse, ModuleInfo, ModuleDependencyEdge

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
    LocalRepositoryCreate,
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


@router.post(
    "/local",
    response_model=RepositoryResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="Onboard a local repository",
    description="""
    Onboard a local repository by providing its path.

    This is used for repositories that are already present on the filesystem
    (e.g., mounted volumes in Docker). No cloning is performed.

    This will:
    1. Validate the path exists and is a directory
    2. Extract git info if available (branch, commit)
    3. Store the repository in the database with status `cloned`

    The repository will be immediately ready for analysis.

    **Note:** Call POST /repositories/{id}/analyze to trigger code analysis.
    """,
)
async def create_local_repository(
    request: LocalRepositoryCreate,
    service: RepositoryService = Depends(get_repository_service),
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryResponse:
    """Onboard a local repository."""
    try:
        repository = await service.create_local_repository(request, session)
        return RepositoryResponse(data=repository)

    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create local repository")
        raise HTTPException(status_code=500, detail=str(e))


class UploadRepositoryResponse(BaseModel):
    """Response for repository upload."""
    success: bool = True
    data: Repository
    files_extracted: int = 0
    message: str = ""


@router.post(
    "/upload",
    response_model=UploadRepositoryResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="Upload a repository as ZIP file",
    description="""
    Upload a repository as a ZIP file from your local machine.

    This will:
    1. Accept the ZIP file upload
    2. Extract it to the repository storage location
    3. Create a repository record with platform = "local"
    4. Optionally trigger auto-analysis

    Supported formats: .zip

    The repository will be immediately ready for analysis after extraction.

    **Note:** Maximum file size is 500MB.
    """,
)
async def upload_repository(
    file: UploadFile = File(..., description="ZIP file containing the repository"),
    name: str = Form(None, description="Repository name (defaults to filename)"),
    auto_analyze: bool = Form(True, description="Auto-trigger analysis after upload"),
    service: RepositoryService = Depends(get_repository_service),
    session: AsyncSession = Depends(get_db_session),
) -> UploadRepositoryResponse:
    """Upload a repository as a ZIP file."""
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(
            status_code=400,
            detail="Only ZIP files are supported. Please upload a .zip file."
        )

    # Check file size (500MB limit)
    MAX_SIZE = 500 * 1024 * 1024  # 500MB
    file_size = 0
    temp_file_path = None

    try:
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
            temp_file_path = temp_file.name
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                file_size += len(chunk)
                if file_size > MAX_SIZE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"File too large. Maximum size is 500MB."
                    )
                temp_file.write(chunk)

        # Validate it's a valid ZIP file
        if not zipfile.is_zipfile(temp_file_path):
            raise HTTPException(
                status_code=400,
                detail="Invalid ZIP file. The file appears to be corrupted."
            )

        # Create repository via service
        repo_name = name or Path(file.filename).stem
        repository, files_extracted = await service.create_from_zip(
            zip_path=temp_file_path,
            name=repo_name,
            auto_analyze=auto_analyze,
            session=session,
        )

        return UploadRepositoryResponse(
            data=repository,
            files_extracted=files_extracted,
            message=f"Successfully uploaded and extracted {files_extracted} files"
        )

    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to upload repository")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup temp file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass


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
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Delete a repository",
    description="""
    Delete a repository and optionally its local files.

    If the repository has running analysis jobs, deletion will fail unless
    `force=true` is set, which will cancel running jobs before deleting.
    """,
)
async def delete_repository(
    repository_id: str,
    delete_files: bool = Query(True, description="Delete local clone files"),
    force: bool = Query(False, description="Force delete even if jobs are running"),
    service: RepositoryService = Depends(get_repository_service),
    session: AsyncSession = Depends(get_db_session),
) -> DeleteResponse:
    """Delete a repository."""
    try:
        success = await service.delete_repository(
            repository_id, session, delete_files, force
        )

        if not success:
            raise HTTPException(status_code=404, detail="Repository not found")

        return DeleteResponse(message=f"Repository {repository_id} deleted")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    - `wiki_options`: Wiki generation options (optional)
      - `enabled`: Generate wiki documentation after analysis (default: true)
      - `depth`: Generation depth - quick, basic, standard, comprehensive (default: basic)
      - `include_core_systems`: Generate Core Systems documentation (default: true)
      - `include_features`: Generate Features documentation (default: true)
      - `include_api_reference`: Generate API Reference documentation (default: false)
      - `include_data_models`: Generate Data Models documentation (default: false)
      - `include_code_structure`: Generate detailed Code Structure documentation (default: false)
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


# =============================================================================
# Module Dependencies Endpoints
# =============================================================================

@router.get(
    "/{repository_id}/modules",
    response_model=ModuleDependenciesResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get module dependencies",
    description="""
    Get module information and dependency graph for a repository.

    Returns:
    - List of modules with their statistics (file count, LOC, complexity)
    - Dependency graph showing which modules depend on each other
    - Summary statistics (total modules, average dependencies)

    This endpoint requires the repository to have been analyzed.
    Module data is available for Java repositories with multi-module structure.
    """,
)
async def get_module_dependencies(
    repository_id: str,
    service: RepositoryService = Depends(get_repository_service),
    session: AsyncSession = Depends(get_db_session),
) -> ModuleDependenciesResponse:
    """Get module dependencies for a repository."""
    # Verify repository exists
    repository = await service.get_repository(repository_id, session)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Check if repository has been analyzed
    if repository.analysis_status.value.lower() not in ["completed", "running"]:
        return ModuleDependenciesResponse(
            repository_id=repository_id,
            repository_name=repository.name,
            modules=[],
            dependencyGraph=[],
            totalModules=0,
            avgDependencies=0.0,
        )

    try:
        # Fetch module data from codegraph service
        codegraph_url = os.getenv("CODEGRAPH_URL", "http://localhost:8001")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{codegraph_url}/repositories/{repository_id}/modules"
            )

            if response.status_code == 404:
                # No modules found - return empty response
                return ModuleDependenciesResponse(
                    repository_id=repository_id,
                    repository_name=repository.name,
                    modules=[],
                    dependencyGraph=[],
                    totalModules=0,
                    avgDependencies=0.0,
                )

            response.raise_for_status()
            data = response.json()

            # Transform response
            modules = [
                ModuleInfo(
                    name=m.get("name", ""),
                    path=m.get("path", ""),
                    fileCount=m.get("fileCount", 0),
                    classCount=m.get("classCount", 0),
                    functionCount=m.get("functionCount", 0),
                    totalLoc=m.get("totalLoc", 0),
                    avgComplexity=m.get("avgComplexity"),
                    maxComplexity=m.get("maxComplexity"),
                    dependencies=m.get("dependencies", []),
                    dependents=m.get("dependents", []),
                )
                for m in data.get("modules", [])
            ]

            dependency_graph = [
                ModuleDependencyEdge(
                    source=e.get("source", ""),
                    target=e.get("target", ""),
                    weight=e.get("weight", 1),
                )
                for e in data.get("dependencyGraph", [])
            ]

            # Calculate summary statistics
            total_modules = len(modules)
            total_deps = sum(len(m.dependencies) for m in modules)
            avg_deps = total_deps / total_modules if total_modules > 0 else 0.0

            return ModuleDependenciesResponse(
                repository_id=repository_id,
                repository_name=repository.name,
                modules=modules,
                dependencyGraph=dependency_graph,
                totalModules=total_modules,
                avgDependencies=round(avg_deps, 2),
            )

    except httpx.HTTPStatusError as e:
        logger.error(f"Codegraph API error: {e.response.status_code}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch module data from analysis service"
        )
    except httpx.RequestError as e:
        logger.error(f"Failed to connect to codegraph: {e}")
        raise HTTPException(
            status_code=503,
            detail="Analysis service unavailable"
        )
    except Exception as e:
        logger.exception("Failed to get module dependencies")
        raise HTTPException(status_code=500, detail=str(e))
