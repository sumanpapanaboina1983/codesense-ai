"""Task Manager with Checkpointing for Resumable Analysis Jobs.

Provides:
- CheckpointedTask: A task wrapper that saves progress to PostgreSQL
- AsyncTaskManager: Singleton managing all background tasks
- Resume capability: Resume from last checkpoint on failure
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.config import get_async_session
from ..database.models import (
    AnalysisRunDB,
    AnalysisCheckpointDB,
    AnalysisLogDB,
    AnalysisStatus as DBAnalysisStatus,
    AnalysisJobPhase,
    LogLevel,
    RepositoryDB,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Configuration from environment
CHECKPOINT_INTERVAL = int(os.getenv("ANALYSIS_CHECKPOINT_INTERVAL", "100"))
LOG_RETENTION_DAYS = int(os.getenv("ANALYSIS_LOG_RETENTION_DAYS", "7"))


class CheckpointedTask:
    """A task wrapper that saves progress to PostgreSQL for resume capability.

    Tracks analysis progress at file-level granularity and saves checkpoints
    periodically to enable resuming failed or paused jobs.
    """

    def __init__(
        self,
        analysis_run_id: str,
        repository_id: str,
        checkpoint_interval: int = CHECKPOINT_INTERVAL,
    ):
        """Initialize a checkpointed task.

        Args:
            analysis_run_id: The analysis run ID.
            repository_id: The repository ID.
            checkpoint_interval: Files processed before saving checkpoint.
        """
        self.analysis_run_id = analysis_run_id
        self.repository_id = repository_id
        self.checkpoint_interval = checkpoint_interval

        # Progress tracking
        self.current_phase = AnalysisJobPhase.PENDING
        self.total_files = 0
        self.processed_files = 0
        self.last_processed_file: Optional[str] = None
        self.nodes_created = 0
        self.relationships_created = 0
        self.checkpoint_data: Dict[str, Any] = {}

        # Task state
        self._cancelled = False
        self._paused = False
        self._files_since_checkpoint = 0

    async def start(self) -> None:
        """Mark the task as started."""
        self.current_phase = AnalysisJobPhase.PENDING
        await self._save_checkpoint()
        await self._log(LogLevel.INFO, "pending", "Analysis job started")

    async def set_phase(self, phase: AnalysisJobPhase) -> None:
        """Set the current phase and save checkpoint.

        Args:
            phase: The new phase.
        """
        self.current_phase = phase
        self._files_since_checkpoint = 0
        await self._save_checkpoint()
        await self._log(LogLevel.INFO, phase.value, f"Entered phase: {phase.value}")

    async def update_progress(
        self,
        processed_files: int,
        total_files: int,
        last_file: Optional[str] = None,
        nodes_created: int = 0,
        relationships_created: int = 0,
        checkpoint_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update progress and optionally save checkpoint.

        Args:
            processed_files: Number of files processed.
            total_files: Total files to process.
            last_file: Last processed file path.
            nodes_created: Nodes created so far.
            relationships_created: Relationships created so far.
            checkpoint_data: Phase-specific data for resume.
        """
        self.processed_files = processed_files
        self.total_files = total_files
        self.last_processed_file = last_file
        self.nodes_created = nodes_created
        self.relationships_created = relationships_created

        if checkpoint_data:
            self.checkpoint_data.update(checkpoint_data)

        self._files_since_checkpoint += 1

        # Save checkpoint at interval
        if self._files_since_checkpoint >= self.checkpoint_interval:
            await self._save_checkpoint()
            self._files_since_checkpoint = 0

    async def complete(self, stats: Optional[Dict[str, Any]] = None) -> None:
        """Mark the task as completed.

        Args:
            stats: Final statistics.
        """
        self.current_phase = AnalysisJobPhase.COMPLETED
        if stats:
            self.checkpoint_data["final_stats"] = stats
        await self._save_checkpoint()
        await self._log(LogLevel.INFO, "completed", "Analysis job completed successfully")

    async def fail(self, error: str) -> None:
        """Mark the task as failed.

        Args:
            error: Error message.
        """
        self.current_phase = AnalysisJobPhase.FAILED
        self.checkpoint_data["error"] = error
        await self._save_checkpoint()
        await self._log(LogLevel.ERROR, "failed", f"Analysis job failed: {error}")

    async def pause(self) -> None:
        """Pause the task and save checkpoint."""
        self._paused = True
        self.current_phase = AnalysisJobPhase.PAUSED
        await self._save_checkpoint()
        await self._log(LogLevel.INFO, "paused", "Analysis job paused")

    def cancel(self) -> None:
        """Request task cancellation."""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """Check if task is cancelled."""
        return self._cancelled

    @property
    def is_paused(self) -> bool:
        """Check if task is paused."""
        return self._paused

    @property
    def progress_pct(self) -> int:
        """Calculate progress percentage."""
        if self.total_files == 0:
            return 0
        return int((self.processed_files / self.total_files) * 100)

    async def _save_checkpoint(self) -> None:
        """Save current progress to database."""
        async with get_async_session() as session:
            # Get or create checkpoint
            result = await session.execute(
                select(AnalysisCheckpointDB)
                .where(AnalysisCheckpointDB.analysis_run_id == self.analysis_run_id)
                .order_by(AnalysisCheckpointDB.updated_at.desc())
                .limit(1)
            )
            checkpoint = result.scalar_one_or_none()

            if checkpoint:
                # Update existing
                checkpoint.current_phase = self.current_phase
                checkpoint.phase_progress_pct = self.progress_pct
                checkpoint.total_files = self.total_files
                checkpoint.processed_files = self.processed_files
                checkpoint.last_processed_file = self.last_processed_file
                checkpoint.nodes_created = self.nodes_created
                checkpoint.relationships_created = self.relationships_created
                checkpoint.checkpoint_data = self.checkpoint_data
                checkpoint.updated_at = datetime.utcnow()
            else:
                # Create new
                checkpoint = AnalysisCheckpointDB(
                    id=str(uuid4()),
                    analysis_run_id=self.analysis_run_id,
                    current_phase=self.current_phase,
                    phase_progress_pct=self.progress_pct,
                    total_files=self.total_files,
                    processed_files=self.processed_files,
                    last_processed_file=self.last_processed_file,
                    nodes_created=self.nodes_created,
                    relationships_created=self.relationships_created,
                    checkpoint_data=self.checkpoint_data,
                )
                session.add(checkpoint)

            await session.commit()

    async def _log(
        self,
        level: LogLevel,
        phase: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write log entry to database.

        Args:
            level: Log level.
            phase: Current phase.
            message: Log message.
            details: Additional details.
        """
        async with get_async_session() as session:
            log_entry = AnalysisLogDB(
                id=str(uuid4()),
                analysis_run_id=self.analysis_run_id,
                level=level,
                phase=phase,
                message=message,
                details=details,
            )
            session.add(log_entry)
            await session.commit()

    @classmethod
    async def from_checkpoint(
        cls,
        analysis_run_id: str,
        repository_id: str,
    ) -> Optional["CheckpointedTask"]:
        """Load task from last checkpoint.

        Args:
            analysis_run_id: The analysis run ID.
            repository_id: The repository ID.

        Returns:
            CheckpointedTask if checkpoint exists, None otherwise.
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(AnalysisCheckpointDB)
                .where(AnalysisCheckpointDB.analysis_run_id == analysis_run_id)
                .order_by(AnalysisCheckpointDB.updated_at.desc())
                .limit(1)
            )
            checkpoint = result.scalar_one_or_none()

            if not checkpoint:
                return None

            task = cls(
                analysis_run_id=analysis_run_id,
                repository_id=repository_id,
            )
            task.current_phase = checkpoint.current_phase
            task.total_files = checkpoint.total_files
            task.processed_files = checkpoint.processed_files
            task.last_processed_file = checkpoint.last_processed_file
            task.nodes_created = checkpoint.nodes_created
            task.relationships_created = checkpoint.relationships_created
            task.checkpoint_data = checkpoint.checkpoint_data or {}

            return task


class AsyncTaskManager:
    """Singleton manager for all background analysis tasks.

    Provides:
    - Task registration and tracking
    - Resume capability for failed jobs
    - Graceful shutdown
    - Log cleanup
    """

    _instance: Optional["AsyncTaskManager"] = None
    _lock = asyncio.Lock()

    def __new__(cls) -> "AsyncTaskManager":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the task manager."""
        if self._initialized:
            return

        self._tasks: Dict[str, asyncio.Task] = {}
        self._checkpointed_tasks: Dict[str, CheckpointedTask] = {}
        self._initialized = True

    async def start_analysis_task(
        self,
        analysis_run_id: str,
        repository_id: str,
        task_func: Callable[[CheckpointedTask], Coroutine[Any, Any, None]],
    ) -> CheckpointedTask:
        """Start a new analysis task with checkpointing.

        Args:
            analysis_run_id: The analysis run ID.
            repository_id: The repository ID.
            task_func: Async function that performs the analysis.

        Returns:
            The checkpointed task instance.
        """
        # Create checkpointed task
        checkpointed_task = CheckpointedTask(
            analysis_run_id=analysis_run_id,
            repository_id=repository_id,
        )
        self._checkpointed_tasks[analysis_run_id] = checkpointed_task

        # Start background task
        async def wrapped_task():
            try:
                await checkpointed_task.start()
                await task_func(checkpointed_task)
            except asyncio.CancelledError:
                await checkpointed_task.pause()
                logger.info(f"Analysis task cancelled: {analysis_run_id}")
            except Exception as e:
                await checkpointed_task.fail(str(e))
                logger.exception(f"Analysis task failed: {analysis_run_id}")
            finally:
                self._tasks.pop(analysis_run_id, None)

        task = asyncio.create_task(wrapped_task())
        self._tasks[analysis_run_id] = task

        return checkpointed_task

    async def resume_analysis_task(
        self,
        analysis_run_id: str,
        repository_id: str,
        task_func: Callable[[CheckpointedTask], Coroutine[Any, Any, None]],
    ) -> Optional[CheckpointedTask]:
        """Resume a failed or paused analysis task from checkpoint.

        Args:
            analysis_run_id: The analysis run ID.
            repository_id: The repository ID.
            task_func: Async function that performs the analysis.

        Returns:
            The checkpointed task if resumable, None otherwise.
        """
        # Load from checkpoint
        checkpointed_task = await CheckpointedTask.from_checkpoint(
            analysis_run_id=analysis_run_id,
            repository_id=repository_id,
        )

        if not checkpointed_task:
            logger.warning(f"No checkpoint found for analysis: {analysis_run_id}")
            return None

        # Check if task is resumable
        if checkpointed_task.current_phase not in [
            AnalysisJobPhase.FAILED,
            AnalysisJobPhase.PAUSED,
        ]:
            logger.warning(f"Task not resumable, phase: {checkpointed_task.current_phase}")
            return None

        self._checkpointed_tasks[analysis_run_id] = checkpointed_task

        # Start resumed task
        async def wrapped_task():
            try:
                await checkpointed_task._log(
                    LogLevel.INFO,
                    "resumed",
                    f"Resuming from phase {checkpointed_task.current_phase.value}, "
                    f"processed {checkpointed_task.processed_files}/{checkpointed_task.total_files} files",
                )
                await task_func(checkpointed_task)
            except asyncio.CancelledError:
                await checkpointed_task.pause()
            except Exception as e:
                await checkpointed_task.fail(str(e))
            finally:
                self._tasks.pop(analysis_run_id, None)

        task = asyncio.create_task(wrapped_task())
        self._tasks[analysis_run_id] = task

        return checkpointed_task

    def cancel_task(self, analysis_run_id: str) -> bool:
        """Cancel a running task.

        Args:
            analysis_run_id: The analysis run ID.

        Returns:
            True if task was cancelled.
        """
        task = self._tasks.get(analysis_run_id)
        if task and not task.done():
            checkpointed_task = self._checkpointed_tasks.get(analysis_run_id)
            if checkpointed_task:
                checkpointed_task.cancel()
            task.cancel()
            return True
        return False

    def get_task(self, analysis_run_id: str) -> Optional[CheckpointedTask]:
        """Get a checkpointed task by ID.

        Args:
            analysis_run_id: The analysis run ID.

        Returns:
            The checkpointed task or None.
        """
        return self._checkpointed_tasks.get(analysis_run_id)

    def get_running_tasks(self) -> List[str]:
        """Get list of running task IDs.

        Returns:
            List of analysis run IDs.
        """
        return [
            run_id
            for run_id, task in self._tasks.items()
            if not task.done()
        ]

    async def shutdown(self) -> None:
        """Gracefully shutdown all tasks."""
        logger.info("Shutting down task manager...")

        # Cancel all running tasks
        for run_id in list(self._tasks.keys()):
            self.cancel_task(run_id)

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(
                *self._tasks.values(),
                return_exceptions=True,
            )

        self._tasks.clear()
        self._checkpointed_tasks.clear()
        logger.info("Task manager shutdown complete")

    @staticmethod
    async def cleanup_old_logs(retention_days: int = LOG_RETENTION_DAYS) -> int:
        """Delete analysis logs older than retention period.

        Args:
            retention_days: Days to retain logs.

        Returns:
            Number of logs deleted.
        """
        cutoff = datetime.utcnow() - timedelta(days=retention_days)

        async with get_async_session() as session:
            result = await session.execute(
                delete(AnalysisLogDB).where(AnalysisLogDB.created_at < cutoff)
            )
            await session.commit()

            deleted = result.rowcount
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old analysis logs")
            return deleted

    @staticmethod
    async def get_incomplete_jobs() -> List[Dict[str, Any]]:
        """Get list of incomplete jobs that can be resumed.

        Returns:
            List of job info dicts.
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(AnalysisRunDB, AnalysisCheckpointDB)
                .join(
                    AnalysisCheckpointDB,
                    AnalysisRunDB.id == AnalysisCheckpointDB.analysis_run_id,
                )
                .where(
                    AnalysisCheckpointDB.current_phase.in_([
                        AnalysisJobPhase.FAILED,
                        AnalysisJobPhase.PAUSED,
                    ])
                )
                .order_by(AnalysisRunDB.created_at.desc())
            )

            jobs = []
            for run, checkpoint in result:
                jobs.append({
                    "analysis_run_id": run.id,
                    "repository_id": run.repository_id,
                    "status": run.status.value,
                    "phase": checkpoint.current_phase.value,
                    "progress_pct": checkpoint.phase_progress_pct,
                    "processed_files": checkpoint.processed_files,
                    "total_files": checkpoint.total_files,
                    "created_at": run.created_at.isoformat(),
                    "updated_at": checkpoint.updated_at.isoformat(),
                })

            return jobs


# Singleton instance
task_manager = AsyncTaskManager()
