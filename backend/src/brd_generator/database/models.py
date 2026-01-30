"""SQLAlchemy database models for repository management."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    Integer,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class RepositoryPlatform(str, enum.Enum):
    """Supported repository platforms."""
    GITHUB = "github"
    GITLAB = "gitlab"


class RepositoryStatus(str, enum.Enum):
    """Repository onboarding status."""
    PENDING = "pending"          # Just created, not yet cloned
    CLONING = "cloning"          # Clone in progress
    CLONED = "cloned"            # Successfully cloned
    CLONE_FAILED = "clone_failed"  # Clone failed


class AnalysisStatus(str, enum.Enum):
    """Analysis run status."""
    NOT_ANALYZED = "not_analyzed"  # Never analyzed
    PENDING = "pending"            # Analysis queued
    RUNNING = "running"            # Analysis in progress
    COMPLETED = "completed"        # Analysis completed successfully
    FAILED = "failed"              # Analysis failed


class RepositoryDB(Base):
    """Repository database model.

    Stores metadata about onboarded repositories.
    """
    __tablename__ = "repositories"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    clone_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    platform: Mapped[RepositoryPlatform] = mapped_column(
        Enum(RepositoryPlatform),
        nullable=False,
        index=True,
    )

    # Repository metadata from platform API
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    size_kb: Mapped[int] = mapped_column(Integer, default=0)
    stars: Mapped[int] = mapped_column(Integer, default=0)

    # Onboarding status
    status: Mapped[RepositoryStatus] = mapped_column(
        Enum(RepositoryStatus),
        default=RepositoryStatus.PENDING,
        nullable=False,
        index=True,
    )
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Local clone info
    local_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    current_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    current_commit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Analysis status (denormalized for quick access)
    analysis_status: Mapped[AnalysisStatus] = mapped_column(
        Enum(AnalysisStatus),
        default=AnalysisStatus.NOT_ANALYZED,
        nullable=False,
        index=True,
    )
    last_analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_analysis_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
    )

    # Settings
    auto_analyze_on_sync: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    cloned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    analysis_runs: Mapped[list["AnalysisRunDB"]] = relationship(
        "AnalysisRunDB",
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="desc(AnalysisRunDB.created_at)",
    )

    # Indexes
    __table_args__ = (
        Index("ix_repositories_status_analysis", "status", "analysis_status"),
        Index("ix_repositories_platform_status", "platform", "status"),
    )

    def __repr__(self) -> str:
        return f"<Repository(id={self.id}, name={self.full_name}, status={self.status})>"


class AnalysisRunDB(Base):
    """Analysis run database model.

    Tracks individual analysis runs for a repository.
    """
    __tablename__ = "analysis_runs"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign key to repository
    repository_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Status
    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(AnalysisStatus),
        default=AnalysisStatus.PENDING,
        nullable=False,
        index=True,
    )
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Analysis configuration
    commit_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reset_graph: Mapped[bool] = mapped_column(Boolean, default=False)

    # Codegraph integration
    codegraph_job_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Results
    stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Example stats: {"files_scanned": 100, "nodes_created": 500, "relationships_created": 1000}

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Duration in seconds (computed on completion)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Triggered by
    triggered_by: Mapped[str] = mapped_column(
        String(100),
        default="api",
        nullable=False,
    )  # "api", "sync", "schedule"

    # Relationships
    repository: Mapped["RepositoryDB"] = relationship(
        "RepositoryDB",
        back_populates="analysis_runs",
    )

    def __repr__(self) -> str:
        return f"<AnalysisRun(id={self.id}, repo={self.repository_id}, status={self.status})>"

    def mark_running(self, codegraph_job_id: Optional[str] = None) -> None:
        """Mark analysis as running."""
        self.status = AnalysisStatus.RUNNING
        self.started_at = datetime.utcnow()
        if codegraph_job_id:
            self.codegraph_job_id = codegraph_job_id

    def mark_completed(self, stats: Optional[dict] = None) -> None:
        """Mark analysis as completed."""
        self.status = AnalysisStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        if self.started_at:
            self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        if stats:
            self.stats = stats

    def mark_failed(self, message: str) -> None:
        """Mark analysis as failed."""
        self.status = AnalysisStatus.FAILED
        self.status_message = message
        self.completed_at = datetime.utcnow()
        if self.started_at:
            self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
