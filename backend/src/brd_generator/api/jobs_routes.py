"""Jobs API routes for analysis job management with checkpointing.

Provides endpoints for:
- Listing jobs with filters
- Getting detailed job info with checkpoints and logs
- SSE streaming for live progress
- Resume and cancel operations
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import re

from ..database.config import get_async_session
from ..database.models import (
    AnalysisRunDB,
    AnalysisCheckpointDB,
    AnalysisLogDB,
    RepositoryDB,
    AnalysisStatus as DBAnalysisStatus,
    AnalysisJobPhase,
    LogLevel,
)
from ..services.task_manager import task_manager, CheckpointedTask
from ..utils.logger import get_logger

logger = get_logger(__name__)

# UUID regex pattern
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)


def is_uuid(value: str) -> bool:
    """Check if a string is a valid UUID format."""
    return bool(UUID_PATTERN.match(value))


router = APIRouter(prefix="/jobs", tags=["Jobs"])


# =============================================================================
# Response Models
# =============================================================================

class JobCheckpoint(BaseModel):
    """Checkpoint information for a job."""

    id: str
    current_phase: str
    phase_progress_pct: int
    total_files: int
    processed_files: int
    last_processed_file: Optional[str] = None
    nodes_created: int
    relationships_created: int
    checkpoint_data: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class JobLog(BaseModel):
    """Log entry for a job."""

    id: str
    level: str
    phase: str
    message: str
    details: Optional[Dict[str, Any]] = None
    created_at: datetime


class JobSummary(BaseModel):
    """Summary of an analysis job for list views."""

    id: str
    repository_id: str
    repository_name: Optional[str] = None
    status: str
    current_phase: Optional[str] = None
    progress_pct: int = 0
    commit_sha: Optional[str] = None
    branch: Optional[str] = None
    triggered_by: str
    stats: Optional[Dict[str, Any]] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    error: Optional[str] = None


class JobDetail(JobSummary):
    """Detailed job information including checkpoints and logs."""

    checkpoints: List[JobCheckpoint] = Field(default_factory=list)
    recent_logs: List[JobLog] = Field(default_factory=list)
    can_resume: bool = False
    can_cancel: bool = False
    can_pause: bool = False


class JobListResponse(BaseModel):
    """Response for job list endpoint."""

    success: bool = True
    jobs: List[JobSummary]
    total: int
    limit: int
    offset: int


class JobDetailResponse(BaseModel):
    """Response for job detail endpoint."""

    success: bool = True
    job: JobDetail


class JobProgressEvent(BaseModel):
    """Progress event for SSE streaming."""

    type: str = "progress"  # progress, phase, complete, error
    phase: Optional[str] = None
    progress_pct: int = 0
    processed_files: int = 0
    total_files: int = 0
    nodes_created: int = 0
    relationships_created: int = 0
    message: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None


class ResumeResponse(BaseModel):
    """Response for resume operation."""

    success: bool = True
    message: str
    job_id: str
    phase: str
    progress_pct: int


class CancelResponse(BaseModel):
    """Response for cancel operation."""

    success: bool = True
    message: str
    job_id: str


class PauseResponse(BaseModel):
    """Response for pause operation."""

    success: bool = True
    message: str
    job_id: str
    phase: str
    progress_pct: int


# =============================================================================
# Helper Functions
# =============================================================================

async def get_db_session() -> AsyncSession:
    """Get database session dependency."""
    async with get_async_session() as session:
        yield session


def normalize_stats_to_snake_case(stats: Optional[dict]) -> Optional[dict]:
    """Normalize stats keys from camelCase to snake_case.

    Ensures consistent snake_case format regardless of how stats were stored.
    """
    if not stats:
        return None

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


def job_to_summary(
    run: AnalysisRunDB,
    checkpoint: Optional[AnalysisCheckpointDB] = None,
    repository: Optional[RepositoryDB] = None,
) -> JobSummary:
    """Convert database models to JobSummary."""
    return JobSummary(
        id=run.id,
        repository_id=run.repository_id,
        repository_name=repository.name if repository else None,
        status=run.status.value,
        current_phase=checkpoint.current_phase.value if checkpoint else None,
        progress_pct=checkpoint.phase_progress_pct if checkpoint else 0,
        commit_sha=run.commit_sha,
        branch=run.branch,
        triggered_by=run.triggered_by,
        stats=normalize_stats_to_snake_case(run.stats),
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_seconds=run.duration_seconds,
        error=run.status_message if run.status == DBAnalysisStatus.FAILED else None,
    )


def checkpoint_to_model(checkpoint: AnalysisCheckpointDB) -> JobCheckpoint:
    """Convert database checkpoint to response model."""
    return JobCheckpoint(
        id=checkpoint.id,
        current_phase=checkpoint.current_phase.value,
        phase_progress_pct=checkpoint.phase_progress_pct,
        total_files=checkpoint.total_files,
        processed_files=checkpoint.processed_files,
        last_processed_file=checkpoint.last_processed_file,
        nodes_created=checkpoint.nodes_created,
        relationships_created=checkpoint.relationships_created,
        checkpoint_data=checkpoint.checkpoint_data,
        created_at=checkpoint.created_at,
        updated_at=checkpoint.updated_at,
    )


def log_to_model(log: AnalysisLogDB) -> JobLog:
    """Convert database log to response model."""
    return JobLog(
        id=log.id,
        level=log.level.value,
        phase=log.phase,
        message=log.message,
        details=log.details,
        created_at=log.created_at,
    )


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    repository_id: Optional[str] = Query(None, description="Filter by repository"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Result offset"),
) -> JobListResponse:
    """List analysis jobs with optional filters.

    Args:
        status: Filter by job status (pending, running, completed, failed).
        repository_id: Filter by repository ID.
        limit: Maximum number of results.
        offset: Result offset for pagination.

    Returns:
        List of job summaries.
    """
    async with get_async_session() as session:
        # Build query
        query = select(AnalysisRunDB)
        count_query = select(func.count(AnalysisRunDB.id))

        if status:
            try:
                status_enum = DBAnalysisStatus(status)
                query = query.where(AnalysisRunDB.status == status_enum)
                count_query = count_query.where(AnalysisRunDB.status == status_enum)
            except ValueError:
                pass

        if repository_id:
            query = query.where(AnalysisRunDB.repository_id == repository_id)
            count_query = count_query.where(AnalysisRunDB.repository_id == repository_id)

        # Get total count
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        # Get paginated results
        query = query.order_by(AnalysisRunDB.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await session.execute(query)
        runs = result.scalars().all()

        # Get latest checkpoints and repository info
        jobs = []
        for run in runs:
            # Get latest checkpoint
            checkpoint_result = await session.execute(
                select(AnalysisCheckpointDB)
                .where(AnalysisCheckpointDB.analysis_run_id == run.id)
                .order_by(AnalysisCheckpointDB.updated_at.desc())
                .limit(1)
            )
            checkpoint = checkpoint_result.scalar_one_or_none()

            # Get repository
            repo_result = await session.execute(
                select(RepositoryDB).where(RepositoryDB.id == run.repository_id)
            )
            repository = repo_result.scalar_one_or_none()

            jobs.append(job_to_summary(run, checkpoint, repository))

        return JobListResponse(
            jobs=jobs,
            total=total,
            limit=limit,
            offset=offset,
        )


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job_detail(job_id: str) -> JobDetailResponse:
    """Get detailed information about an analysis job.

    Args:
        job_id: The analysis run ID.

    Returns:
        Detailed job information including checkpoints and logs.
    """
    async with get_async_session() as session:
        # Get analysis run
        result = await session.execute(
            select(AnalysisRunDB).where(AnalysisRunDB.id == job_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get repository
        repo_result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.id == run.repository_id)
        )
        repository = repo_result.scalar_one_or_none()

        # Get checkpoints
        checkpoints_result = await session.execute(
            select(AnalysisCheckpointDB)
            .where(AnalysisCheckpointDB.analysis_run_id == job_id)
            .order_by(AnalysisCheckpointDB.updated_at.desc())
        )
        checkpoints = checkpoints_result.scalars().all()
        latest_checkpoint = checkpoints[0] if checkpoints else None

        # Get recent logs
        logs_result = await session.execute(
            select(AnalysisLogDB)
            .where(AnalysisLogDB.analysis_run_id == job_id)
            .order_by(AnalysisLogDB.created_at.desc())
            .limit(100)
        )
        logs = logs_result.scalars().all()

        # Determine if resumable/cancellable/pausable
        can_resume = run.status in [
            DBAnalysisStatus.FAILED,
            DBAnalysisStatus.PAUSED,
        ]
        can_cancel = run.status in [
            DBAnalysisStatus.RUNNING,
            DBAnalysisStatus.PAUSED,
        ]
        can_pause = run.status == DBAnalysisStatus.RUNNING

        # Build response
        summary = job_to_summary(run, latest_checkpoint, repository)
        job_detail = JobDetail(
            **summary.model_dump(),
            checkpoints=[checkpoint_to_model(cp) for cp in checkpoints],
            recent_logs=[log_to_model(log) for log in reversed(logs)],
            can_resume=can_resume,
            can_cancel=can_cancel,
            can_pause=can_pause,
        )

        return JobDetailResponse(job=job_detail)


@router.get("/{job_id}/progress/stream")
async def stream_job_progress(job_id: str):
    """Stream live progress updates for an analysis job via SSE.

    Args:
        job_id: The analysis run ID.

    Returns:
        SSE stream of progress events.
    """

    async def generate():
        """Generate SSE events."""
        last_progress = -1
        last_phase = None
        poll_count = 0
        max_polls = 3600  # 1 hour at 1s intervals

        while poll_count < max_polls:
            try:
                async with get_async_session() as session:
                    # Get analysis run - look up by UUID id or by codegraph_job_id
                    if is_uuid(job_id):
                        result = await session.execute(
                            select(AnalysisRunDB).where(AnalysisRunDB.id == job_id)
                        )
                    else:
                        # job_id is a codegraph job ID format
                        result = await session.execute(
                            select(AnalysisRunDB).where(AnalysisRunDB.codegraph_job_id == job_id)
                        )
                    run = result.scalar_one_or_none()

                    if not run:
                        event = JobProgressEvent(
                            type="error",
                            error="Job not found",
                        )
                        yield f"data: {event.model_dump_json()}\n\n"
                        break

                    # Get latest checkpoint (use run.id which is always the UUID)
                    checkpoint_result = await session.execute(
                        select(AnalysisCheckpointDB)
                        .where(AnalysisCheckpointDB.analysis_run_id == run.id)
                        .order_by(AnalysisCheckpointDB.updated_at.desc())
                        .limit(1)
                    )
                    checkpoint = checkpoint_result.scalar_one_or_none()

                    # Build progress event
                    current_progress = checkpoint.phase_progress_pct if checkpoint else 0
                    current_phase = checkpoint.current_phase.value if checkpoint else "pending"

                    # Check for completion
                    if run.status == DBAnalysisStatus.COMPLETED:
                        event = JobProgressEvent(
                            type="complete",
                            phase="completed",
                            progress_pct=100,
                            processed_files=checkpoint.processed_files if checkpoint else 0,
                            total_files=checkpoint.total_files if checkpoint else 0,
                            nodes_created=checkpoint.nodes_created if checkpoint else 0,
                            relationships_created=checkpoint.relationships_created if checkpoint else 0,
                            status="completed",
                            message="Analysis completed successfully",
                        )
                        yield f"data: {event.model_dump_json()}\n\n"
                        break

                    # Check for failure
                    if run.status == DBAnalysisStatus.FAILED:
                        event = JobProgressEvent(
                            type="error",
                            phase=current_phase,
                            progress_pct=current_progress,
                            status="failed",
                            error=run.status_message or "Analysis failed",
                        )
                        yield f"data: {event.model_dump_json()}\n\n"
                        break

                    # Send progress update if changed
                    if current_progress != last_progress or current_phase != last_phase:
                        event = JobProgressEvent(
                            type="phase" if current_phase != last_phase else "progress",
                            phase=current_phase,
                            progress_pct=current_progress,
                            processed_files=checkpoint.processed_files if checkpoint else 0,
                            total_files=checkpoint.total_files if checkpoint else 0,
                            nodes_created=checkpoint.nodes_created if checkpoint else 0,
                            relationships_created=checkpoint.relationships_created if checkpoint else 0,
                            status=run.status.value,
                        )
                        yield f"data: {event.model_dump_json()}\n\n"
                        last_progress = current_progress
                        last_phase = current_phase

            except Exception as e:
                logger.error(f"Error streaming progress: {e}")
                event = JobProgressEvent(
                    type="error",
                    error=str(e),
                )
                yield f"data: {event.model_dump_json()}\n\n"
                break

            await asyncio.sleep(1)
            poll_count += 1

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{job_id}/resume", response_model=ResumeResponse)
async def resume_job(job_id: str) -> ResumeResponse:
    """Resume a failed or paused analysis job from its last checkpoint.

    This will restart the analysis from where it left off, skipping
    already-processed files.

    Args:
        job_id: The analysis run ID.

    Returns:
        Resume operation result.
    """
    # Import here to avoid circular imports
    from ..services.repository_service import RepositoryService

    async with get_async_session() as session:
        # Get analysis run
        result = await session.execute(
            select(AnalysisRunDB).where(AnalysisRunDB.id == job_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get repository
        repo_result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.id == run.repository_id)
        )
        repository = repo_result.scalar_one_or_none()

        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Get latest checkpoint
        checkpoint_result = await session.execute(
            select(AnalysisCheckpointDB)
            .where(AnalysisCheckpointDB.analysis_run_id == job_id)
            .order_by(AnalysisCheckpointDB.updated_at.desc())
            .limit(1)
        )
        checkpoint = checkpoint_result.scalar_one_or_none()

        # Check if resumable
        can_resume = run.status in [
            DBAnalysisStatus.FAILED,
            DBAnalysisStatus.PAUSED,
        ]

        if not can_resume:
            raise HTTPException(
                status_code=400,
                detail=f"Job cannot be resumed. Status: {run.status.value}",
            )

        # Update status to running
        run.status = DBAnalysisStatus.RUNNING
        run.status_message = "Resuming from checkpoint"
        run.started_at = datetime.utcnow()  # Reset start time for duration tracking

        # Update checkpoint phase
        if checkpoint:
            checkpoint.current_phase = AnalysisJobPhase.PENDING  # Will be updated by codegraph

        await session.commit()

        phase = checkpoint.current_phase.value if checkpoint else "pending"
        progress = checkpoint.phase_progress_pct if checkpoint else 0

        # Prepare checkpoint data for codegraph
        resume_data = None
        if checkpoint:
            resume_data = {
                "phase": phase,
                "processed_files": checkpoint.processed_files,
                "total_files": checkpoint.total_files,
                "last_processed_file": checkpoint.last_processed_file,
                "nodes_created": checkpoint.nodes_created,
                "relationships_created": checkpoint.relationships_created,
                "checkpoint_data": checkpoint.checkpoint_data or {},
            }

        logger.info(f"Job {job_id} resuming from phase {phase} at {progress}%")

        # Trigger resume analysis in background
        repo_service = RepositoryService()
        import asyncio
        asyncio.create_task(
            repo_service.resume_analysis(
                analysis_id=job_id,
                repository_id=str(repository.id),
                local_path=repository.local_path,
                resume_data=resume_data,
            )
        )

        return ResumeResponse(
            message=f"Resuming analysis from {phase} phase",
            job_id=job_id,
            phase=phase,
            progress_pct=progress,
        )


@router.post("/{job_id}/pause", response_model=PauseResponse)
async def pause_job(job_id: str) -> PauseResponse:
    """Pause a running analysis job.

    The job can be resumed later from its last checkpoint.

    Args:
        job_id: The analysis run ID.

    Returns:
        Pause operation result.
    """
    async with get_async_session() as session:
        # Get analysis run
        result = await session.execute(
            select(AnalysisRunDB).where(AnalysisRunDB.id == job_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            raise HTTPException(status_code=404, detail="Job not found")

        if run.status != DBAnalysisStatus.RUNNING:
            raise HTTPException(
                status_code=400,
                detail=f"Job is not running. Status: {run.status.value}",
            )

        # Get latest checkpoint for progress info
        checkpoint_result = await session.execute(
            select(AnalysisCheckpointDB)
            .where(AnalysisCheckpointDB.analysis_run_id == job_id)
            .order_by(AnalysisCheckpointDB.updated_at.desc())
            .limit(1)
        )
        checkpoint = checkpoint_result.scalar_one_or_none()

        # Try to pause via task manager (this will trigger checkpoint save)
        task_manager.cancel_task(job_id)

        # Update checkpoint phase to PAUSED
        if checkpoint:
            checkpoint.current_phase = AnalysisJobPhase.PAUSED
            # Store processed files list in checkpoint_data for resume
            if not checkpoint.checkpoint_data:
                checkpoint.checkpoint_data = {}

        # Update status to PAUSED
        run.status = DBAnalysisStatus.PAUSED
        run.status_message = "Paused by user"
        await session.commit()

        phase = checkpoint.current_phase.value if checkpoint else "pending"
        progress = checkpoint.phase_progress_pct if checkpoint else 0

        logger.info(f"Job {job_id} paused at phase {phase}, {progress}%")

        return PauseResponse(
            message=f"Job paused at {phase} phase",
            job_id=job_id,
            phase=phase,
            progress_pct=progress,
        )


@router.post("/{job_id}/cancel", response_model=CancelResponse)
async def cancel_job(job_id: str) -> CancelResponse:
    """Cancel a running analysis job.

    Unlike pause, cancelled jobs cannot be resumed.

    Args:
        job_id: The analysis run ID.

    Returns:
        Cancel operation result.
    """
    async with get_async_session() as session:
        # Get analysis run
        result = await session.execute(
            select(AnalysisRunDB).where(AnalysisRunDB.id == job_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            raise HTTPException(status_code=404, detail="Job not found")

        if run.status not in [DBAnalysisStatus.RUNNING, DBAnalysisStatus.PAUSED]:
            raise HTTPException(
                status_code=400,
                detail=f"Job is not running or paused. Status: {run.status.value}",
            )

        # Try to cancel via task manager
        task_manager.cancel_task(job_id)

        # Update status to CANCELLED
        run.status = DBAnalysisStatus.CANCELLED
        run.status_message = "Cancelled by user"
        run.completed_at = datetime.utcnow()
        if run.started_at:
            run.duration_seconds = int(
                (run.completed_at - run.started_at).total_seconds()
            )
        await session.commit()

        logger.info(f"Job {job_id} cancelled")

        return CancelResponse(
            message="Job cancelled successfully",
            job_id=job_id,
        )


@router.get("/{job_id}/logs", response_model=List[JobLog])
async def get_job_logs(
    job_id: str,
    level: Optional[str] = Query(None, description="Filter by log level"),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Result offset"),
) -> List[JobLog]:
    """Get logs for an analysis job.

    Args:
        job_id: The analysis run ID.
        level: Filter by log level (info, warning, error).
        limit: Maximum number of results.
        offset: Result offset for pagination.

    Returns:
        List of log entries.
    """
    async with get_async_session() as session:
        # Build query
        query = select(AnalysisLogDB).where(AnalysisLogDB.analysis_run_id == job_id)

        if level:
            try:
                level_enum = LogLevel(level)
                query = query.where(AnalysisLogDB.level == level_enum)
            except ValueError:
                pass

        query = query.order_by(AnalysisLogDB.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await session.execute(query)
        logs = result.scalars().all()

        return [log_to_model(log) for log in logs]


@router.get("/{job_id}/logs/download")
async def download_job_logs(job_id: str):
    """Download all logs for an analysis job as a text file.

    Args:
        job_id: The analysis run ID.

    Returns:
        Text file with all log entries.
    """
    from fastapi.responses import Response

    async with get_async_session() as session:
        # Get job info
        run_result = await session.execute(
            select(AnalysisRunDB).where(AnalysisRunDB.id == job_id)
        )
        run = run_result.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get repository name for filename
        repo_result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.id == run.repository_id)
        )
        repo = repo_result.scalar_one_or_none()
        repo_name = repo.name if repo else "unknown"

        # Get all logs
        query = select(AnalysisLogDB).where(
            AnalysisLogDB.analysis_run_id == job_id
        ).order_by(AnalysisLogDB.created_at.asc())

        result = await session.execute(query)
        logs = result.scalars().all()

        # Build log content
        lines = [
            f"Analysis Job Logs",
            f"================",
            f"Job ID: {job_id}",
            f"Repository: {repo_name}",
            f"Status: {run.status.value}",
            f"Started: {run.started_at}",
            f"Completed: {run.completed_at}",
            f"",
            f"Logs ({len(logs)} entries):",
            f"----------------------------",
            "",
        ]

        for log in logs:
            timestamp = log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else ""
            lines.append(f"[{timestamp}] [{log.level.value.upper()}] [{log.phase}] {log.message}")
            if log.details:
                import json
                lines.append(f"    Details: {json.dumps(log.details)}")

        content = "\n".join(lines)

        # Return as downloadable file
        filename = f"analysis-logs-{repo_name}-{job_id[:8]}.txt"
        return Response(
            content=content,
            media_type="text/plain",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )


class DeleteJobResponse(BaseModel):
    """Response for deleting a job."""

    success: bool
    message: str
    job_id: str


@router.delete("/{job_id}", response_model=DeleteJobResponse)
async def delete_job(job_id: str) -> DeleteJobResponse:
    """Delete an analysis job.

    This will cancel the job if running and remove all related data
    (checkpoints, logs).

    Args:
        job_id: The analysis run ID.

    Returns:
        Delete operation result.
    """
    async with get_async_session() as session:
        # Get analysis run
        result = await session.execute(
            select(AnalysisRunDB).where(AnalysisRunDB.id == job_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            raise HTTPException(status_code=404, detail="Job not found")

        # Cancel if running
        if run.status == DBAnalysisStatus.RUNNING:
            task_manager.cancel_task(job_id)

        # Delete checkpoints
        await session.execute(
            delete(AnalysisCheckpointDB).where(
                AnalysisCheckpointDB.analysis_run_id == job_id
            )
        )

        # Delete logs
        await session.execute(
            delete(AnalysisLogDB).where(AnalysisLogDB.analysis_run_id == job_id)
        )

        # Delete the analysis run
        await session.delete(run)
        await session.commit()

        logger.info(f"Deleted job {job_id}")

        return DeleteJobResponse(
            success=True,
            message="Job deleted successfully",
            job_id=job_id,
        )
