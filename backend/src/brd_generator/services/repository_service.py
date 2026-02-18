"""Repository service with PostgreSQL persistence.

Handles repository onboarding and analysis as separate operations.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
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

    async def create_from_zip(
        self,
        zip_path: str,
        name: str,
        session: AsyncSession,
        auto_analyze: bool = True,
    ) -> Tuple[Repository, int]:
        """Create a repository from an uploaded ZIP file.

        Args:
            zip_path: Path to the uploaded ZIP file.
            name: Repository name.
            session: Database session.
            auto_analyze: Whether to auto-trigger analysis.

        Returns:
            Tuple of (Repository, files_extracted).

        Raises:
            ValueError: If repository name already exists or ZIP is invalid.
        """
        # Generate repository ID and destination path
        repo_id = str(uuid4())
        dest_path = self.storage_root / repo_id

        # Check if name already exists
        existing = await self._get_by_name(name, session)
        if existing:
            raise ValueError(f"Repository with name '{name}' already exists")

        files_extracted = 0

        try:
            # Create destination directory
            dest_path.mkdir(parents=True, exist_ok=True)

            # Extract ZIP file
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Get list of files
                file_list = zip_ref.namelist()
                files_extracted = len([f for f in file_list if not f.endswith('/')])

                # Check if there's a single root directory
                # Many ZIPs have structure like: repo-name/src/... instead of src/...
                root_dirs = set()
                for file_path in file_list:
                    parts = file_path.split('/')
                    if len(parts) > 1 and parts[0]:
                        root_dirs.add(parts[0])

                # If there's exactly one root directory, extract contents from it
                single_root = len(root_dirs) == 1
                root_prefix = list(root_dirs)[0] + '/' if single_root else ''

                # Extract files
                for member in zip_ref.infolist():
                    # Skip directories and hidden files
                    if member.is_dir():
                        continue
                    if member.filename.startswith('__MACOSX'):
                        continue

                    # Calculate target path
                    if single_root and member.filename.startswith(root_prefix):
                        target_name = member.filename[len(root_prefix):]
                    else:
                        target_name = member.filename

                    if not target_name:
                        continue

                    target_path = dest_path / target_name

                    # Create parent directories
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    # Extract file
                    with zip_ref.open(member) as source:
                        with open(target_path, 'wb') as target:
                            shutil.copyfileobj(source, target)

            # Try to get git info if it's a git repository
            current_branch = None
            current_commit = None
            try:
                git_status = await self.git_client.get_status(dest_path)
                current_branch = git_status.branch
                current_commit = git_status.commit_sha
            except Exception:
                # Not a git repo - that's okay for uploaded repos
                pass

            # Create repository record
            from ..database.models import RepositoryPlatform as DBRepositoryPlatform

            db_repo = RepositoryDB(
                id=repo_id,
                name=name,
                full_name=f"uploaded/{name}",
                url=f"upload://{name}",
                clone_url=f"upload://{name}",
                platform=DBRepositoryPlatform.LOCAL,
                description=f"Uploaded repository: {name}",
                default_branch=current_branch or "main",
                is_private=True,
                local_path=str(dest_path),
                current_branch=current_branch,
                current_commit=current_commit,
                status=DBRepositoryStatus.CLONED,
                cloned_at=datetime.utcnow(),
                analysis_status=DBAnalysisStatus.NOT_ANALYZED,
                auto_analyze_on_sync=auto_analyze,
            )

            session.add(db_repo)
            await session.flush()

            logger.info(
                f"Created repository from ZIP: {name} ({repo_id}), "
                f"extracted {files_extracted} files to {dest_path}"
            )

            repository = Repository.model_validate(db_repo)

            # Schedule auto-analysis as a background task (runs after transaction commits)
            if auto_analyze:
                logger.info(f"Scheduling auto-analysis for uploaded repository: {name}")
                task = asyncio.create_task(
                    self._delayed_auto_trigger_analysis(repo_id, name)
                )
                self._background_tasks[f"auto-analyze-{repo_id}"] = task

            return repository, files_extracted

        except Exception as e:
            # Cleanup on failure
            if dest_path.exists():
                shutil.rmtree(dest_path, ignore_errors=True)
            raise

    async def _get_by_name(
        self,
        name: str,
        session: AsyncSession,
    ) -> Optional[RepositoryDB]:
        """Get repository by name."""
        result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.name == name)
        )
        return result.scalar_one_or_none()

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
        force: bool = False,
    ) -> bool:
        """Delete a repository.

        Args:
            repository_id: Repository ID.
            session: Database session.
            delete_files: Whether to delete local files.
            force: If True, cancel running jobs and delete anyway.

        Returns:
            True if deleted.

        Raises:
            ValueError: If repository has running analysis jobs and force=False.
        """
        result = await session.execute(
            select(RepositoryDB).where(RepositoryDB.id == repository_id)
        )
        db_repo = result.scalar_one_or_none()

        if not db_repo:
            return False

        # Check for running analysis jobs
        running_jobs_result = await session.execute(
            select(AnalysisRunDB).where(
                AnalysisRunDB.repository_id == repository_id,
                AnalysisRunDB.status.in_([
                    DBAnalysisStatus.PENDING,
                    DBAnalysisStatus.RUNNING,
                ])
            )
        )
        running_jobs = running_jobs_result.scalars().all()

        if running_jobs and not force:
            job_ids = [job.id for job in running_jobs]
            raise ValueError(
                f"Cannot delete repository with running analysis jobs. "
                f"Running jobs: {job_ids}. Use force=true to cancel jobs and delete."
            )

        # Cancel any background tasks
        for task_key in [f"clone-{repository_id}", f"analysis-{repository_id}"]:
            if task_key in self._background_tasks:
                task = self._background_tasks.pop(task_key)
                if not task.done():
                    task.cancel()

        # Cancel running jobs if force=True
        if running_jobs and force:
            for job in running_jobs:
                job.status = DBAnalysisStatus.FAILED
                job.status_message = "Cancelled due to repository deletion"
                job.completed_at = datetime.utcnow()
            await session.flush()

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

                # Auto-trigger analysis if enabled
                if db_repo.auto_analyze_on_sync:
                    logger.info(f"Auto-triggering analysis for {db_repo.full_name}")
                    await self._auto_trigger_analysis(repository_id)

            except Exception as e:
                logger.exception(f"Failed to clone repository: {db_repo.full_name}")
                db_repo.status = DBRepositoryStatus.CLONE_FAILED
                db_repo.status_message = str(e)
                await session.commit()

    async def _auto_trigger_analysis(self, repository_id: str) -> None:
        """Auto-trigger analysis after successful clone.

        Args:
            repository_id: Repository ID to analyze.
        """
        try:
            async with get_async_session() as session:
                # Create analysis run
                from ..models.repository import AnalysisRunCreate

                analysis_data = AnalysisRunCreate(
                    reset_graph=False,
                    triggered_by="auto_clone",
                )

                await self.trigger_analysis(repository_id, analysis_data, session)
                await session.commit()

        except Exception as e:
            logger.warning(f"Failed to auto-trigger analysis: {e}")
            # Don't fail the clone if analysis trigger fails

    async def _delayed_auto_trigger_analysis(
        self,
        repository_id: str,
        repo_name: str,
        max_retries: int = 5,
        retry_delay: float = 1.0,
    ) -> None:
        """Auto-trigger analysis after ZIP upload with retry logic.

        This runs as a background task to ensure the transaction that created
        the repository record has committed before we try to trigger analysis.

        Args:
            repository_id: Repository ID to analyze.
            repo_name: Repository name for logging.
            max_retries: Maximum retry attempts to find the repository.
            retry_delay: Seconds to wait between retries.
        """
        for attempt in range(max_retries):
            try:
                # Wait for transaction to commit
                await asyncio.sleep(retry_delay)

                async with get_async_session() as session:
                    # Verify repository exists
                    result = await session.execute(
                        select(RepositoryDB).where(RepositoryDB.id == repository_id)
                    )
                    db_repo = result.scalar_one_or_none()

                    if not db_repo:
                        logger.warning(
                            f"Repository {repository_id} not found yet, "
                            f"attempt {attempt + 1}/{max_retries}"
                        )
                        continue

                    # Create analysis run
                    from ..models.repository import AnalysisRunCreate

                    analysis_data = AnalysisRunCreate(
                        reset_graph=False,
                        triggered_by="auto_upload",
                    )

                    await self.trigger_analysis(repository_id, analysis_data, session)
                    await session.commit()

                    logger.info(f"Auto-triggered analysis for uploaded repository: {repo_name}")
                    return

            except Exception as e:
                logger.warning(
                    f"Failed to auto-trigger analysis (attempt {attempt + 1}): {e}"
                )
                if attempt < max_retries - 1:
                    continue
                else:
                    logger.error(
                        f"Giving up auto-trigger analysis for {repo_name} after {max_retries} attempts"
                    )

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

        # Create analysis run with wiki options
        wiki_options_dict = None
        if hasattr(data, 'wiki_options') and data.wiki_options:
            wiki_options_dict = data.wiki_options.model_dump()

        analysis_run = AnalysisRunDB(
            id=str(uuid4()),
            repository_id=repository_id,
            status=DBAnalysisStatus.PENDING,
            commit_sha=db_repo.current_commit,
            branch=db_repo.current_branch,
            reset_graph=data.reset_graph,
            triggered_by=data.triggered_by,
            wiki_options=wiki_options_dict,
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
                # Build callback URL for codegraph to report progress
                # Use internal Docker network URL if running in Docker
                backend_url = os.environ.get("BACKEND_INTERNAL_URL", "http://backend:8000")

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
                        # Callback parameters for progress reporting
                        "callbackUrl": backend_url,
                        "analysisRunId": str(analysis.id),
                    },
                )
                response.raise_for_status()
                result_data = response.json()

                codegraph_job_id = result_data.get("jobId")

                # Update to running
                analysis.mark_running(codegraph_job_id)
                db_repo.analysis_status = DBAnalysisStatus.RUNNING
                await session.commit()

                logger.info(f"Started codegraph analysis: {codegraph_job_id} with callback to {backend_url}")

                # Poll for completion (as fallback, codegraph also reports via callback)
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
                        raw_stats = result.get("stats", {})
                        # Normalize camelCase stats from codegraph to snake_case
                        stats = self._normalize_stats(raw_stats)
                        analysis.mark_completed(stats)
                        if db_repo:
                            db_repo.analysis_status = DBAnalysisStatus.COMPLETED
                            db_repo.last_analyzed_at = datetime.utcnow()
                        await session.commit()

                        logger.info(
                            f"Analysis completed: {analysis_id} - "
                            f"{stats.get('nodes_created', 0)} nodes, "
                            f"{stats.get('relationships_created', 0)} relationships"
                        )

                        # Trigger wiki generation if enabled
                        wiki_options = analysis.wiki_options
                        if wiki_options and wiki_options.get("enabled", True):
                            logger.info(f"Triggering wiki generation for {analysis.repository_id}")
                            await self._trigger_wiki_generation(
                                repository_id=analysis.repository_id,
                                analysis_id=analysis_id,
                                wiki_options=wiki_options,
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

    async def resume_analysis(
        self,
        analysis_id: str,
        repository_id: str,
        local_path: str,
        resume_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Resume a paused or failed analysis from its checkpoint.

        Args:
            analysis_id: Analysis run ID.
            repository_id: Repository ID.
            local_path: Local path to the repository.
            resume_data: Checkpoint data for resuming (phase, processed_files, etc.)
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(AnalysisRunDB).where(AnalysisRunDB.id == analysis_id)
            )
            analysis = result.scalar_one_or_none()

            if not analysis:
                logger.error(f"Analysis run not found for resume: {analysis_id}")
                return

            # Get repository
            repo_result = await session.execute(
                select(RepositoryDB).where(RepositoryDB.id == repository_id)
            )
            db_repo = repo_result.scalar_one_or_none()

            if not db_repo:
                logger.error(f"Repository not found for resume: {repository_id}")
                return

            try:
                # Build callback URL for codegraph to report progress
                backend_url = os.environ.get("BACKEND_INTERNAL_URL", "http://backend:8000")

                # Build resume request with checkpoint data
                request_data = {
                    "directory": local_path,
                    "repositoryId": str(repository_id),
                    "repositoryName": db_repo.name,
                    "repositoryUrl": db_repo.url,
                    "resetDb": False,  # Don't reset on resume
                    "updateSchema": False,  # Schema already exists
                    "callbackUrl": backend_url,
                    "analysisRunId": str(analysis_id),
                }

                # Add resume checkpoint data if available
                if resume_data:
                    request_data["resumeFrom"] = {
                        "phase": resume_data.get("phase", "pending"),
                        "processedFiles": resume_data.get("processed_files", 0),
                        "totalFiles": resume_data.get("total_files", 0),
                        "lastProcessedFile": resume_data.get("last_processed_file"),
                        "nodesCreated": resume_data.get("nodes_created", 0),
                        "relationshipsCreated": resume_data.get("relationships_created", 0),
                        "checkpointData": resume_data.get("checkpoint_data", {}),
                    }

                # Call codegraph API
                client = await self._get_http_client()
                response = await client.post(
                    f"{self.codegraph_url}/analyze",
                    json=request_data,
                )
                response.raise_for_status()
                result_data = response.json()

                codegraph_job_id = result_data.get("jobId")

                # Update to running
                analysis.codegraph_job_id = codegraph_job_id
                db_repo.analysis_status = DBAnalysisStatus.RUNNING
                await session.commit()

                logger.info(
                    f"Resumed analysis: {analysis_id} -> codegraph job {codegraph_job_id}, "
                    f"resuming from phase: {resume_data.get('phase') if resume_data else 'start'}"
                )

                # Poll for completion (as fallback, codegraph also reports via callback)
                await self._poll_analysis(analysis_id, codegraph_job_id)

            except Exception as e:
                logger.exception(f"Failed to resume analysis: {analysis_id}")
                analysis.mark_failed(f"Resume failed: {str(e)}")
                db_repo.analysis_status = DBAnalysisStatus.FAILED
                await session.commit()

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _normalize_stats(self, stats: dict) -> dict:
        """Convert camelCase stats keys to snake_case.

        Codegraph sends camelCase keys (nodesCreated, relationshipsCreated)
        but the frontend expects snake_case (nodes_created, relationships_created).

        Args:
            stats: Raw stats dict from codegraph.

        Returns:
            Normalized stats with snake_case keys.
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

    async def _trigger_wiki_generation(
        self,
        repository_id: str,
        analysis_id: str,
        wiki_options: Dict[str, Any],
    ) -> None:
        """Trigger wiki generation after analysis completes.

        This is called automatically when analysis completes if wiki generation
        is enabled in the analysis options.

        Args:
            repository_id: Repository ID.
            analysis_id: Analysis run ID that triggered this.
            wiki_options: Wiki generation options from the analysis run.
        """
        try:
            from .wiki_service import get_wiki_service

            # Map wiki_options to depth
            # If include_code_structure is True, use comprehensive
            # Otherwise use the depth from options (basic, standard, etc.)
            depth = wiki_options.get("depth", "basic")

            # Adjust depth based on include options
            include_code_structure = wiki_options.get("include_code_structure", False)
            include_api_reference = wiki_options.get("include_api_reference", False)
            include_data_models = wiki_options.get("include_data_models", False)

            # If any advanced options are enabled, ensure at least standard depth
            if include_api_reference or include_data_models:
                if depth in ["quick", "basic"]:
                    depth = "standard"

            # If code structure is enabled, use comprehensive
            if include_code_structure:
                depth = "comprehensive"

            logger.info(
                f"Starting wiki generation for repository {repository_id} "
                f"(analysis: {analysis_id}, depth: {depth}, mode: {wiki_options.get('mode', 'standard')})"
            )

            async with get_async_session() as session:
                # Get repository for commit SHA
                repo_result = await session.execute(
                    select(RepositoryDB).where(RepositoryDB.id == repository_id)
                )
                db_repo = repo_result.scalar_one_or_none()

                if not db_repo:
                    logger.error(f"Repository not found for wiki generation: {repository_id}")
                    return

                # Get wiki service (should already be initialized by app.py)
                wiki_service = get_wiki_service()

                # Generate wiki with full options
                await wiki_service.generate_wiki(
                    session=session,
                    repository_id=repository_id,
                    commit_sha=db_repo.current_commit,
                    depth=depth,
                    wiki_options=wiki_options,  # Pass full options for advanced mode
                    progress_callback=None,  # Could add logging callback
                )

                # Mark analysis as having wiki generated
                analysis_result = await session.execute(
                    select(AnalysisRunDB).where(AnalysisRunDB.id == analysis_id)
                )
                analysis = analysis_result.scalar_one_or_none()
                if analysis:
                    analysis.wiki_generated = True

                await session.commit()

                logger.info(
                    f"Wiki generation completed for repository {repository_id} "
                    f"(analysis: {analysis_id})"
                )

        except Exception as e:
            logger.exception(
                f"Wiki generation failed for repository {repository_id}: {e}"
            )
            # Don't fail the analysis if wiki generation fails
            # Just log the error
