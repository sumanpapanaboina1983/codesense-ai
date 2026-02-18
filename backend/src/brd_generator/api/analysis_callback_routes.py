"""Callback Routes for Codegraph Analysis Progress.

These endpoints are called by the Codegraph service to report
analysis progress, logs, and completion status back to the backend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..database.config import get_async_session
from ..database.models import (
    AnalysisRunDB,
    AnalysisCheckpointDB,
    AnalysisLogDB,
    AnalysisStatus,
    AnalysisJobPhase,
    LogLevel,
    RepositoryDB,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/analysis/callback", tags=["Analysis Callbacks"])


# =============================================================================
# Request Models
# =============================================================================

class ProgressUpdate(BaseModel):
    """Progress update from codegraph."""
    phase: str = Field(..., description="Current analysis phase")
    progress_pct: int = Field(0, ge=0, le=100, description="Progress percentage")
    total_files: int = Field(0, ge=0, description="Total files to process")
    processed_files: int = Field(0, ge=0, description="Files processed so far")
    last_processed_file: Optional[str] = Field(None, description="Last processed file path")
    nodes_created: int = Field(0, ge=0, description="Nodes created in Neo4j")
    relationships_created: int = Field(0, ge=0, description="Relationships created in Neo4j")
    message: Optional[str] = Field(None, description="Optional status message")


class LogEntry(BaseModel):
    """Log entry from codegraph."""
    level: str = Field("info", description="Log level: info, warning, error")
    phase: str = Field(..., description="Analysis phase")
    message: str = Field(..., description="Log message")
    details: Optional[dict] = Field(None, description="Additional details")
    timestamp: Optional[str] = Field(None, description="ISO timestamp")


class LogBatch(BaseModel):
    """Batch of log entries for efficient storage."""
    logs: List[LogEntry] = Field(..., description="List of log entries")


class CompletionUpdate(BaseModel):
    """Analysis completion notification."""
    success: bool = Field(..., description="Whether analysis succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")
    stats: Optional[dict] = Field(None, description="Final statistics")


class StartNotification(BaseModel):
    """Notification that analysis has started."""
    codegraph_job_id: str = Field(..., description="Job ID from codegraph")


# =============================================================================
# Response Models
# =============================================================================

class CallbackResponse(BaseModel):
    """Standard callback response."""
    success: bool = True
    message: str = "OK"


# =============================================================================
# Callback Endpoints
# =============================================================================

@router.post("/{analysis_run_id}/start", response_model=CallbackResponse)
async def notify_start(
    analysis_run_id: str,
    request: StartNotification,
) -> CallbackResponse:
    """Notify that analysis has started.

    Called by codegraph when it begins processing.
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(AnalysisRunDB).where(AnalysisRunDB.id == analysis_run_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            raise HTTPException(status_code=404, detail="Analysis run not found")

        run.status = AnalysisStatus.RUNNING
        run.started_at = datetime.utcnow()
        run.codegraph_job_id = request.codegraph_job_id

        # Update repository status
        repo_result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.id == run.repository_id)
        )
        repo = repo_result.scalar_one_or_none()
        if repo:
            repo.analysis_status = AnalysisStatus.RUNNING

        # Create initial checkpoint
        checkpoint = AnalysisCheckpointDB(
            analysis_run_id=analysis_run_id,
            current_phase=AnalysisJobPhase.PENDING,
        )
        session.add(checkpoint)

        await session.commit()

        logger.info(f"Analysis started: {analysis_run_id}, codegraph job: {request.codegraph_job_id}")

    return CallbackResponse(message="Start notification recorded")


@router.post("/{analysis_run_id}/progress", response_model=CallbackResponse)
async def update_progress(
    analysis_run_id: str,
    request: ProgressUpdate,
) -> CallbackResponse:
    """Update analysis progress.

    Called periodically by codegraph during analysis.
    """
    async with get_async_session() as session:
        # Update or create checkpoint
        result = await session.execute(
            select(AnalysisCheckpointDB)
            .where(AnalysisCheckpointDB.analysis_run_id == analysis_run_id)
            .order_by(AnalysisCheckpointDB.created_at.desc())
            .limit(1)
        )
        checkpoint = result.scalar_one_or_none()

        if not checkpoint:
            checkpoint = AnalysisCheckpointDB(analysis_run_id=analysis_run_id)
            session.add(checkpoint)

        # Map phase string to enum
        phase_map = {
            "pending": AnalysisJobPhase.PENDING,
            "cloning": AnalysisJobPhase.CLONING,
            "indexing": AnalysisJobPhase.INDEXING_FILES,
            "indexing_files": AnalysisJobPhase.INDEXING_FILES,
            "parsing": AnalysisJobPhase.PARSING_CODE,
            "parsing_code": AnalysisJobPhase.PARSING_CODE,
            "building_graph": AnalysisJobPhase.BUILDING_GRAPH,
            "storing": AnalysisJobPhase.BUILDING_GRAPH,
            "completed": AnalysisJobPhase.COMPLETED,
            "failed": AnalysisJobPhase.FAILED,
        }

        checkpoint.current_phase = phase_map.get(
            request.phase.lower(),
            AnalysisJobPhase.PARSING_CODE
        )
        checkpoint.phase_progress_pct = request.progress_pct
        checkpoint.total_files = request.total_files
        checkpoint.processed_files = request.processed_files
        checkpoint.last_processed_file = request.last_processed_file
        checkpoint.nodes_created = request.nodes_created
        checkpoint.relationships_created = request.relationships_created
        checkpoint.updated_at = datetime.utcnow()

        # Also update the analysis run stats
        run_result = await session.execute(
            select(AnalysisRunDB).where(AnalysisRunDB.id == analysis_run_id)
        )
        run = run_result.scalar_one_or_none()
        if run:
            run.stats = {
                "files_scanned": request.processed_files,
                "total_files": request.total_files,
                "nodes_created": request.nodes_created,
                "relationships_created": request.relationships_created,
                "current_phase": request.phase,
                "progress_pct": request.progress_pct,
            }

        await session.commit()

    return CallbackResponse(message="Progress updated")


@router.post("/{analysis_run_id}/log", response_model=CallbackResponse)
async def add_log(
    analysis_run_id: str,
    request: LogEntry,
) -> CallbackResponse:
    """Add a single log entry.

    Called by codegraph for individual log messages.
    """
    async with get_async_session() as session:
        # Map level string to enum
        level_map = {
            "info": LogLevel.INFO,
            "warning": LogLevel.WARNING,
            "warn": LogLevel.WARNING,
            "error": LogLevel.ERROR,
        }

        log_entry = AnalysisLogDB(
            analysis_run_id=analysis_run_id,
            level=level_map.get(request.level.lower(), LogLevel.INFO),
            phase=request.phase,
            message=request.message,
            details=request.details,
        )
        session.add(log_entry)
        await session.commit()

    return CallbackResponse(message="Log added")


@router.post("/{analysis_run_id}/logs", response_model=CallbackResponse)
async def add_logs_batch(
    analysis_run_id: str,
    request: LogBatch,
) -> CallbackResponse:
    """Add multiple log entries in a batch.

    More efficient for high-volume logging.
    """
    async with get_async_session() as session:
        level_map = {
            "info": LogLevel.INFO,
            "warning": LogLevel.WARNING,
            "warn": LogLevel.WARNING,
            "error": LogLevel.ERROR,
        }

        for log in request.logs:
            log_entry = AnalysisLogDB(
                analysis_run_id=analysis_run_id,
                level=level_map.get(log.level.lower(), LogLevel.INFO),
                phase=log.phase,
                message=log.message,
                details=log.details,
            )
            session.add(log_entry)

        await session.commit()

    return CallbackResponse(message=f"Added {len(request.logs)} logs")


def normalize_stats_to_snake_case(stats: dict) -> dict:
    """Convert camelCase stats keys to snake_case.

    Codegraph sends camelCase keys (nodesCreated, relationshipsCreated)
    but the frontend expects snake_case (nodes_created, relationships_created).
    """
    if not stats:
        return {}

    # Map of camelCase to snake_case
    key_map = {
        "nodesCreated": "nodes_created",
        "relationshipsCreated": "relationships_created",
        "filesScanned": "files_scanned",
        "totalFiles": "total_files",
        "classesFound": "classes_found",
        "methodsFound": "methods_found",
        "functionsFound": "functions_found",
        "currentPhase": "current_phase",
        "progressPct": "progress_pct",
    }

    normalized = {}
    for key, value in stats.items():
        # Use the mapped key if exists, otherwise keep original
        normalized_key = key_map.get(key, key)
        normalized[normalized_key] = value

    return normalized


@router.post("/{analysis_run_id}/complete", response_model=CallbackResponse)
async def notify_complete(
    analysis_run_id: str,
    request: CompletionUpdate,
) -> CallbackResponse:
    """Notify that analysis has completed.

    Called by codegraph when analysis finishes (success or failure).
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(AnalysisRunDB).where(AnalysisRunDB.id == analysis_run_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            raise HTTPException(status_code=404, detail="Analysis run not found")

        if request.success:
            # Normalize stats from camelCase to snake_case
            normalized_stats = normalize_stats_to_snake_case(request.stats) if request.stats else None
            run.mark_completed(stats=normalized_stats)
            final_status = AnalysisStatus.COMPLETED

            # Update checkpoint to completed
            checkpoint_result = await session.execute(
                select(AnalysisCheckpointDB)
                .where(AnalysisCheckpointDB.analysis_run_id == analysis_run_id)
                .order_by(AnalysisCheckpointDB.created_at.desc())
                .limit(1)
            )
            checkpoint = checkpoint_result.scalar_one_or_none()
            if checkpoint:
                checkpoint.current_phase = AnalysisJobPhase.COMPLETED
                checkpoint.phase_progress_pct = 100
        else:
            run.mark_failed(message=request.error or "Analysis failed")
            final_status = AnalysisStatus.FAILED

        # Update repository status
        repo_result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.id == run.repository_id)
        )
        repo = repo_result.scalar_one_or_none()
        if repo:
            repo.analysis_status = final_status
            if request.success:
                repo.last_analyzed_at = datetime.utcnow()
                repo.last_analysis_id = analysis_run_id

        await session.commit()

        logger.info(f"Analysis completed: {analysis_run_id}, success={request.success}")

    return CallbackResponse(message="Completion recorded")
