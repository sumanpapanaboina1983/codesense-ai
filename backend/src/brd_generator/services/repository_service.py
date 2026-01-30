"""Repository service with PostgreSQL persistence.

Handles repository onboarding and analysis as separate operations.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import (
    RepositoryDB,
    AnalysisRunDB,
    RepositoryStatus as DBRepositoryStatus,
    AnalysisStatus as DBAnalysisStatus,
)
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
    RepositoryCredentials,
    LocalRepositoryCreate,
)
from .git_client import GitClient
from .platform_client import PlatformClient, create_platform_client
from ..utils.logger import get_logger

logger = get_logger(__name__)


class RepositoryService:
    """Service for repository onboarding and analysis.

    Separates onboarding (clone) from analysis (codegraph).
    Uses PostgreSQL for persistence.
    """

    def __init__(
        self,
        storage_root: Optional[Path] = None,
        codegraph_url: Optional[str] = None,
    ):
        """Initialize repository service.

        Args:
            storage_root: Root directory for cloned repositories.
            codegraph_url: URL of the codegraph API service.
        """
        self.storage_root = storage_root or Path(
            os.getenv("REPO_STORAGE_ROOT", "/data/repositories")
        )
        self.storage_root.mkdir(parents=True, exist_ok=True)

        self.codegraph_url = codegraph_url or os.getenv(
            "CODEGRAPH_URL", "http://localhost:8001"
        )

        # Git client for clone/pull operations
        self.git_client = GitClient()

        # HTTP client for codegraph API
        self._http_client: Optional[httpx.AsyncClient] = None

        # In-memory credential store (not persisted)
        self._credentials: dict[str, RepositoryCredentials] = {}

        # Background tasks
        self._background_tasks: dict[str, asyncio.Task] = {}

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                follow_redirects=True,
            )
        return self._http_client

    async def close(self) -> None:
        """Cleanup resources."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

        for task_id, task in self._background_tasks.items():
            if not task.done():
                task.cancel()
                logger.warning(f"Cancelled background task: {task_id}")

    # =========================================================================
    # Repository CRUD
    # =========================================================================

    async def create_repository(
        self,
        data: RepositoryCreate,
        session: AsyncSession,
    ) -> Repository:
        """Onboard a new repository (fetch metadata and start clone).

        Args:
            data: Repository creation data.
            session: Database session.

        Returns:
            Created repository.

        Raises:
            ValueError: If repository already exists or URL is invalid.
        """
        # Check for existing repository
        existing = await self._get_by_url(data.url, session)
        if existing:
            raise ValueError(f"Repository already exists: {existing.full_name}")

        # Parse URL to get platform
        owner, repo_name, platform = PlatformClient.parse_repo_url(data.url)
        platform = data.platform or platform

        # Fetch metadata from platform API
        platform_client = create_platform_client(platform, data.token)
        try:
            repo_info = await platform_client.get_repository(owner, repo_name)
        finally:
            await platform_client.close()

        # Create repository record
        repo_id = str(uuid4())
        local_path = str(self.storage_root / repo_id)

        db_repo = RepositoryDB(
            id=repo_id,
            name=repo_info.name,
            full_name=repo_info.full_name,
            url=data.url,
            clone_url=repo_info.clone_url,
            platform=DBRepositoryStatus(platform.value) if hasattr(DBRepositoryStatus, platform.value) else platform.value,
            description=repo_info.description,
            default_branch=data.branch or repo_info.default_branch,
            is_private=repo_info.is_private,
            language=repo_info.language,
            size_kb=repo_info.size_kb,
            stars=repo_info.stars,
            status=DBRepositoryStatus.PENDING,
            local_path=local_path,
            analysis_status=DBAnalysisStatus.NOT_ANALYZED,
        )
        # Fix: platform should use RepositoryPlatform enum from database models
        from ..database.models import RepositoryPlatform as DBRepositoryPlatform
        db_repo.platform = DBRepositoryPlatform(platform.value)

        session.add(db_repo)
        await session.flush()

        # Store credentials in memory
        if data.token:
            self._credentials[repo_id] = RepositoryCredentials(
                platform=platform,
                token=data.token,
            )

        logger.info(f"Created repository: {repo_info.full_name} ({repo_id})")

        # Start background clone
        task = asyncio.create_task(
            self._clone_repository(repo_id, data.token)
        )
        self._background_tasks[f"clone-{repo_id}"] = task

        return Repository.model_validate(db_repo)

    async def create_local_repository(
        self,
        data: LocalRepositoryCreate,
        session: AsyncSession,
    ) -> Repository:
        """Onboard a local repository (no cloning needed).

        Args:
            data: Local repository data with path.
            session: Database session.

        Returns:
            Created repository.

        Raises:
            ValueError: If repository already exists or path is invalid.
        """
        local_path = Path(data.path)

        # Validate path exists
        if not local_path.exists():
            raise ValueError(f"Path does not exist: {data.path}")

        if not local_path.is_dir():
            raise ValueError(f"Path is not a directory: {data.path}")

        # Check for existing repository with same path
        existing = await self._get_by_local_path(str(local_path), session)
        if existing:
            raise ValueError(f"Repository already exists at path: {data.path}")

        # Determine repository name
        repo_name = data.name or local_path.name

        # Try to get git info if it's a git repository
        current_branch = None
        current_commit = None
        try:
            git_status = await self.git_client.get_status(local_path)
            current_branch = git_status.branch
            current_commit = git_status.commit_sha
        except Exception:
            # Not a git repo or git not available - that's okay for local repos
            pass

        # Create repository record
        repo_id = str(uuid4())

        from ..database.models import RepositoryPlatform as DBRepositoryPlatform

        db_repo = RepositoryDB(
            id=repo_id,
            name=repo_name,
            full_name=f"local/{repo_name}",
            url=f"file://{local_path}",
            clone_url=f"file://{local_path}",
            platform=DBRepositoryPlatform.LOCAL,
            description=f"Local repository at {local_path}",
            default_branch=current_branch or "main",
            is_private=True,  # Local repos are always private
            local_path=str(local_path),
            current_branch=current_branch,
            current_commit=current_commit,
            status=DBRepositoryStatus.CLONED,  # Already "cloned" - files are present
            cloned_at=datetime.utcnow(),
            analysis_status=DBAnalysisStatus.NOT_ANALYZED,
        )

        session.add(db_repo)
        await session.flush()

        logger.info(f"Created local repository: {repo_name} ({repo_id}) at {local_path}")

        return Repository.model_validate(db_repo)

    async def _get_by_local_path(
        self,
        local_path: str,
        session: AsyncSession,
    ) -> Optional[RepositoryDB]:
        """Get repository by local path."""
        result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.local_path == local_path)
        )
        return result.scalar_one_or_none()

    async def get_repository(
        self,
        repository_id: str,
        session: AsyncSession,
    ) -> Optional[Repository]:
        """Get a repository by ID.

        Args:
            repository_id: Repository ID.
            session: Database session.

        Returns:
            Repository or None if not found.
        """
        result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.id == repository_id)
        )
        db_repo = result.scalar_one_or_none()

        if db_repo:
            return Repository.model_validate(db_repo)
        return None

    async def list_repositories(
        self,
        session: AsyncSession,
        status: Optional[RepositoryStatus] = None,
        analysis_status: Optional[AnalysisStatus] = None,
        platform: Optional[RepositoryPlatform] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RepositorySummary], int]:
        """List repositories with filtering.

        Args:
            session: Database session.
            status: Filter by onboarding status.
            analysis_status: Filter by analysis status.
            platform: Filter by platform.
            limit: Max results.
            offset: Results offset.

        Returns:
            Tuple of (repositories, total_count).
        """
        from sqlalchemy import func

        # Build query
        query = select(RepositoryDB)
        count_query = select(func.count(RepositoryDB.id))

        if status:
            query = query.where(RepositoryDB.status == DBRepositoryStatus(status.value))
            count_query = count_query.where(RepositoryDB.status == DBRepositoryStatus(status.value))

        if analysis_status:
            query = query.where(RepositoryDB.analysis_status == DBAnalysisStatus(analysis_status.value))
            count_query = count_query.where(RepositoryDB.analysis_status == DBAnalysisStatus(analysis_status.value))

        if platform:
            from ..database.models import RepositoryPlatform as DBRepositoryPlatform
            query = query.where(RepositoryDB.platform == DBRepositoryPlatform(platform.value))
            count_query = count_query.where(RepositoryDB.platform == DBRepositoryPlatform(platform.value))

        # Get total count
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        # Get paginated results
        query = query.order_by(RepositoryDB.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await session.execute(query)
        db_repos = result.scalars().all()

        repos = [RepositorySummary.model_validate(r) for r in db_repos]
        return repos, total

    async def update_repository(
        self,
        repository_id: str,
        data: RepositoryUpdate,
        session: AsyncSession,
    ) -> Optional[Repository]:
        """Update repository settings.

        Args:
            repository_id: Repository ID.
            data: Update data.
            session: Database session.

        Returns:
            Updated repository or None if not found.
        """
        result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.id == repository_id)
        )
        db_repo = result.scalar_one_or_none()

        if not db_repo:
            return None

        # Update fields
        if data.auto_analyze_on_sync is not None:
            db_repo.auto_analyze_on_sync = data.auto_analyze_on_sync

        db_repo.updated_at = datetime.utcnow()
        await session.flush()

        logger.info(f"Updated repository: {db_repo.full_name}")
        return Repository.model_validate(db_repo)

    async def delete_repository(
        self,
        repository_id: str,
        session: AsyncSession,
        delete_files: bool = True,
    ) -> bool:
        """Delete a repository.

        Args:
            repository_id: Repository ID.
            session: Database session.
            delete_files: Whether to delete local files.

        Returns:
            True if deleted.
        """
        result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.id == repository_id)
        )
        db_repo = result.scalar_one_or_none()

        if not db_repo:
            return False

        # Cancel any background tasks
        for task_key in [f"clone-{repository_id}", f"analysis-{repository_id}"]:
            if task_key in self._background_tasks:
                task = self._background_tasks.pop(task_key)
                if not task.done():
                    task.cancel()

        # Delete local files
        if delete_files and db_repo.local_path:
            await self.git_client.cleanup(Path(db_repo.local_path))

        # Remove credentials
        self._credentials.pop(repository_id, None)

        # Delete from database (cascades to analysis_runs)
        await session.delete(db_repo)

        logger.info(f"Deleted repository: {db_repo.full_name}")
        return True

    # =========================================================================
    # Clone Operations
    # =========================================================================

    async def _clone_repository(
        self,
        repository_id: str,
        token: Optional[str] = None,
    ) -> None:
        """Background task to clone a repository.

        Args:
            repository_id: Repository ID.
            token: Access token.
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(RepositoryDB).where(RepositoryDB.id == repository_id)
            )
            db_repo = result.scalar_one_or_none()

            if not db_repo:
                logger.error(f"Repository not found for clone: {repository_id}")
                return

            try:
                # Update status to cloning
                db_repo.status = DBRepositoryStatus.CLONING
                await session.commit()

                # Build clone URL with token
                clone_url = db_repo.clone_url
                if token:
                    credentials = RepositoryCredentials(
                        platform=RepositoryPlatform(db_repo.platform.value),
                        token=token,
                    )
                    clone_url = credentials.get_auth_url(db_repo.clone_url)

                # Clone
                await self.git_client.clone(
                    url=clone_url,
                    destination=Path(db_repo.local_path),
                    branch=db_repo.default_branch,
                )

                # Update status
                git_status = await self.git_client.get_status(Path(db_repo.local_path))
                db_repo.status = DBRepositoryStatus.CLONED
                db_repo.current_branch = git_status.branch
                db_repo.current_commit = git_status.commit_sha
                db_repo.cloned_at = datetime.utcnow()
                db_repo.last_synced_at = datetime.utcnow()
                await session.commit()

                logger.info(f"Cloned repository: {db_repo.full_name} at {git_status.commit_sha}")

            except Exception as e:
                logger.exception(f"Failed to clone repository: {db_repo.full_name}")
                db_repo.status = DBRepositoryStatus.CLONE_FAILED
                db_repo.status_message = str(e)
                await session.commit()

    async def sync_repository(
        self,
        repository_id: str,
        session: AsyncSession,
        force: bool = False,
    ) -> Repository:
        """Sync (pull) a repository.

        Args:
            repository_id: Repository ID.
            session: Database session.
            force: Force sync (discard local changes).

        Returns:
            Updated repository.

        Raises:
            ValueError: If repository not found or not cloned.
        """
        result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.id == repository_id)
        )
        db_repo = result.scalar_one_or_none()

        if not db_repo:
            raise ValueError(f"Repository not found: {repository_id}")

        if db_repo.status != DBRepositoryStatus.CLONED:
            raise ValueError(f"Repository not cloned. Status: {db_repo.status}")

        if not db_repo.local_path or not Path(db_repo.local_path).exists():
            raise ValueError("Repository local path does not exist")

        # Pull changes
        changes, commits = await self.git_client.pull(
            repo_path=Path(db_repo.local_path),
            force=force,
        )

        # Update status
        git_status = await self.git_client.get_status(Path(db_repo.local_path))
        db_repo.current_branch = git_status.branch
        db_repo.current_commit = git_status.commit_sha
        db_repo.last_synced_at = datetime.utcnow()
        await session.flush()

        logger.info(f"Synced repository: {db_repo.full_name} (changes={changes}, commits={commits})")

        return Repository.model_validate(db_repo)

    # =========================================================================
    # Analysis Operations
    # =========================================================================

    async def trigger_analysis(
        self,
        repository_id: str,
        data: AnalysisRunCreate,
        session: AsyncSession,
    ) -> AnalysisRun:
        """Trigger code analysis for a repository.

        Args:
            repository_id: Repository ID.
            data: Analysis configuration.
            session: Database session.

        Returns:
            Created analysis run.

        Raises:
            ValueError: If repository not found or not cloned.
        """
        result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.id == repository_id)
        )
        db_repo = result.scalar_one_or_none()

        if not db_repo:
            raise ValueError(f"Repository not found: {repository_id}")

        if db_repo.status != DBRepositoryStatus.CLONED:
            raise ValueError(f"Repository not cloned. Status: {db_repo.status}")

        # Create analysis run
        analysis_run = AnalysisRunDB(
            id=str(uuid4()),
            repository_id=repository_id,
            status=DBAnalysisStatus.PENDING,
            commit_sha=db_repo.current_commit,
            branch=db_repo.current_branch,
            reset_graph=data.reset_graph,
            triggered_by=data.triggered_by,
        )
        session.add(analysis_run)

        # Update repository analysis status
        db_repo.analysis_status = DBAnalysisStatus.PENDING
        db_repo.last_analysis_id = analysis_run.id

        await session.flush()

        logger.info(f"Created analysis run: {analysis_run.id} for {db_repo.full_name}")

        # Start background analysis
        task = asyncio.create_task(
            self._run_analysis(analysis_run.id)
        )
        self._background_tasks[f"analysis-{analysis_run.id}"] = task

        return AnalysisRun.model_validate(analysis_run)

    async def _run_analysis(self, analysis_id: str) -> None:
        """Background task to run analysis.

        Args:
            analysis_id: Analysis run ID.
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(AnalysisRunDB).where(AnalysisRunDB.id == analysis_id)
            )
            analysis = result.scalar_one_or_none()

            if not analysis:
                logger.error(f"Analysis run not found: {analysis_id}")
                return

            # Get repository
            repo_result = await session.execute(
                select(RepositoryDB).where(RepositoryDB.id == analysis.repository_id)
            )
            db_repo = repo_result.scalar_one_or_none()

            if not db_repo:
                logger.error(f"Repository not found for analysis: {analysis.repository_id}")
                return

            try:
                # Call codegraph API with repository metadata for multi-repository support
                client = await self._get_http_client()
                response = await client.post(
                    f"{self.codegraph_url}/analyze",
                    json={
                        "directory": db_repo.local_path,
                        "repositoryId": str(db_repo.id),  # UUID for multi-repository support
                        "repositoryName": db_repo.name,    # Display name
                        "repositoryUrl": db_repo.url,      # Original repository URL
                        "resetDb": analysis.reset_graph,
                        "updateSchema": True,
                    },
                )
                response.raise_for_status()
                result_data = response.json()

                codegraph_job_id = result_data.get("jobId")

                # Update to running
                analysis.mark_running(codegraph_job_id)
                db_repo.analysis_status = DBAnalysisStatus.RUNNING
                await session.commit()

                logger.info(f"Started codegraph analysis: {codegraph_job_id}")

                # Poll for completion
                await self._poll_analysis(analysis_id, codegraph_job_id)

            except Exception as e:
                logger.exception(f"Failed to start analysis: {analysis_id}")
                analysis.mark_failed(str(e))
                db_repo.analysis_status = DBAnalysisStatus.FAILED
                await session.commit()

    async def _poll_analysis(
        self,
        analysis_id: str,
        codegraph_job_id: str,
        poll_interval: int = 5,
        max_polls: int = 360,
    ) -> None:
        """Poll codegraph API for analysis completion.

        Args:
            analysis_id: Analysis run ID.
            codegraph_job_id: Codegraph job ID.
            poll_interval: Seconds between polls.
            max_polls: Maximum polls (30 min default).
        """
        client = await self._get_http_client()

        for _ in range(max_polls):
            try:
                response = await client.get(
                    f"{self.codegraph_url}/jobs/{codegraph_job_id}"
                )
                response.raise_for_status()
                result = response.json()

                status = result.get("status")

                async with get_async_session() as session:
                    # Get analysis and repository
                    analysis_result = await session.execute(
                        select(AnalysisRunDB).where(AnalysisRunDB.id == analysis_id)
                    )
                    analysis = analysis_result.scalar_one_or_none()

                    if not analysis:
                        return

                    repo_result = await session.execute(
                        select(RepositoryDB).where(RepositoryDB.id == analysis.repository_id)
                    )
                    db_repo = repo_result.scalar_one_or_none()

                    if status == "completed":
                        stats = result.get("stats", {})
                        analysis.mark_completed(stats)
                        if db_repo:
                            db_repo.analysis_status = DBAnalysisStatus.COMPLETED
                            db_repo.last_analyzed_at = datetime.utcnow()
                        await session.commit()

                        logger.info(
                            f"Analysis completed: {analysis_id} - "
                            f"{stats.get('nodesCreated', 0)} nodes, "
                            f"{stats.get('relationshipsCreated', 0)} relationships"
                        )
                        return

                    elif status == "failed":
                        error = result.get("error", "Unknown error")
                        analysis.mark_failed(error)
                        if db_repo:
                            db_repo.analysis_status = DBAnalysisStatus.FAILED
                        await session.commit()

                        logger.error(f"Analysis failed: {analysis_id} - {error}")
                        return

                await asyncio.sleep(poll_interval)

            except asyncio.CancelledError:
                logger.warning(f"Analysis polling cancelled: {analysis_id}")
                return
            except Exception as e:
                logger.error(f"Error polling analysis: {e}")
                await asyncio.sleep(poll_interval)

        # Timeout
        async with get_async_session() as session:
            analysis_result = await session.execute(
                select(AnalysisRunDB).where(AnalysisRunDB.id == analysis_id)
            )
            analysis = analysis_result.scalar_one_or_none()
            if analysis:
                analysis.mark_failed("Analysis timed out")

            repo_result = await session.execute(
                select(RepositoryDB).where(RepositoryDB.id == analysis.repository_id)
            )
            db_repo = repo_result.scalar_one_or_none()
            if db_repo:
                db_repo.analysis_status = DBAnalysisStatus.FAILED

            await session.commit()

        logger.error(f"Analysis timed out: {analysis_id}")

    async def get_analysis_run(
        self,
        analysis_id: str,
        session: AsyncSession,
    ) -> Optional[AnalysisRun]:
        """Get an analysis run by ID.

        Args:
            analysis_id: Analysis run ID.
            session: Database session.

        Returns:
            Analysis run or None.
        """
        result = await session.execute(
            select(AnalysisRunDB).where(AnalysisRunDB.id == analysis_id)
        )
        analysis = result.scalar_one_or_none()

        if analysis:
            return AnalysisRun.model_validate(analysis)
        return None

    async def list_analysis_runs(
        self,
        repository_id: str,
        session: AsyncSession,
        limit: int = 20,
    ) -> list[AnalysisRunSummary]:
        """List analysis runs for a repository.

        Args:
            repository_id: Repository ID.
            session: Database session.
            limit: Max results.

        Returns:
            List of analysis run summaries.
        """
        result = await session.execute(
            select(AnalysisRunDB)
            .where(AnalysisRunDB.repository_id == repository_id)
            .order_by(AnalysisRunDB.created_at.desc())
            .limit(limit)
        )
        runs = result.scalars().all()

        return [AnalysisRunSummary.model_validate(r) for r in runs]

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_by_url(
        self,
        url: str,
        session: AsyncSession,
    ) -> Optional[RepositoryDB]:
        """Get repository by URL."""
        result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.url == url)
        )
        return result.scalar_one_or_none()

    def store_credentials(
        self,
        repository_id: str,
        credentials: RepositoryCredentials,
    ) -> None:
        """Store credentials in memory."""
        self._credentials[repository_id] = credentials

    def get_credentials(
        self,
        repository_id: str,
    ) -> Optional[RepositoryCredentials]:
        """Get credentials from memory."""
        return self._credentials.get(repository_id)
