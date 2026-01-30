"""Pydantic models for repository management.

These are the domain models/schemas used in the API layer.
They map to/from the SQLAlchemy database models.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


class RepositoryPlatform(str, Enum):
    """Supported repository platforms."""
    GITHUB = "github"
    GITLAB = "gitlab"
    LOCAL = "local"


class RepositoryStatus(str, Enum):
    """Repository onboarding status."""
    PENDING = "pending"
    CLONING = "cloning"
    CLONED = "cloned"
    CLONE_FAILED = "clone_failed"


class AnalysisStatus(str, Enum):
    """Analysis status."""
    NOT_ANALYZED = "not_analyzed"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# Repository Models
# =============================================================================

class RepositoryBase(BaseModel):
    """Base repository fields."""
    url: str = Field(..., description="Repository URL")
    platform: Optional[RepositoryPlatform] = Field(
        None,
        description="Platform (auto-detected if not provided)"
    )


class RepositoryCreate(RepositoryBase):
    """Request model for creating a repository."""
    token: Optional[str] = Field(
        None,
        description="Personal access token for private repositories"
    )
    branch: Optional[str] = Field(
        None,
        description="Branch to clone (default: repository default)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{
                "url": "https://github.com/owner/repo",
                "token": "ghp_xxxxxxxxxxxx",
                "branch": "main"
            }]
        }
    )


class LocalRepositoryCreate(BaseModel):
    """Request model for onboarding a local repository (no cloning needed)."""
    path: str = Field(
        ...,
        description="Absolute path to the local repository directory"
    )
    name: Optional[str] = Field(
        None,
        description="Repository name (defaults to directory name)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{
                "path": "/data/repositories/my-project",
                "name": "my-project"
            }]
        }
    )


class RepositoryUpdate(BaseModel):
    """Request model for updating a repository."""
    auto_analyze_on_sync: Optional[bool] = Field(
        None,
        description="Auto-analyze after sync"
    )


class Repository(BaseModel):
    """Full repository model returned by API."""
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Repository name")
    full_name: str = Field(..., description="Full repository name (owner/repo)")
    url: str = Field(..., description="Repository URL")
    clone_url: str = Field(..., description="Git clone URL")
    platform: RepositoryPlatform

    # Metadata
    description: Optional[str] = None
    default_branch: str = "main"
    is_private: bool = False
    language: Optional[str] = None
    size_kb: int = 0
    stars: int = 0

    # Onboarding status
    status: RepositoryStatus = RepositoryStatus.PENDING
    status_message: Optional[str] = None

    # Local clone info
    local_path: Optional[str] = None
    current_branch: Optional[str] = None
    current_commit: Optional[str] = None

    # Analysis status
    analysis_status: AnalysisStatus = AnalysisStatus.NOT_ANALYZED
    last_analyzed_at: Optional[datetime] = None
    last_analysis_id: Optional[str] = None

    # Settings
    auto_analyze_on_sync: bool = True

    # Timestamps
    created_at: datetime
    updated_at: datetime
    cloned_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RepositorySummary(BaseModel):
    """Summary repository model for list endpoints."""
    id: str
    name: str
    full_name: str
    url: str
    platform: RepositoryPlatform
    status: RepositoryStatus
    analysis_status: AnalysisStatus
    last_analyzed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Analysis Run Models
# =============================================================================

class AnalysisRunCreate(BaseModel):
    """Request model for creating an analysis run."""
    reset_graph: bool = Field(
        False,
        description="Reset Neo4j graph before analysis"
    )
    triggered_by: str = Field(
        "api",
        description="What triggered this analysis"
    )


class AnalysisRun(BaseModel):
    """Full analysis run model."""
    id: str
    repository_id: str
    status: AnalysisStatus
    status_message: Optional[str] = None

    # Configuration
    commit_sha: Optional[str] = None
    branch: Optional[str] = None
    reset_graph: bool = False

    # Codegraph integration
    codegraph_job_id: Optional[str] = None

    # Results
    stats: Optional[dict] = None

    # Timestamps
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None

    # Metadata
    triggered_by: str = "api"

    model_config = ConfigDict(from_attributes=True)


class AnalysisRunSummary(BaseModel):
    """Summary analysis run model for list endpoints."""
    id: str
    status: AnalysisStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    triggered_by: str

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Credentials Model (not persisted to DB)
# =============================================================================

class RepositoryCredentials(BaseModel):
    """Repository credentials (stored in-memory only).

    These are used for git operations and platform API access,
    but are never persisted to the database.
    """
    platform: RepositoryPlatform
    token: str
    api_url: Optional[str] = None  # For self-hosted GitLab

    def get_auth_url(self, repo_url: str) -> str:
        """Get repository URL with embedded token for git operations."""
        if "github.com" in repo_url:
            return repo_url.replace("https://", f"https://{self.token}@")
        elif "gitlab" in repo_url:
            return repo_url.replace("https://", f"https://oauth2:{self.token}@")
        return repo_url
