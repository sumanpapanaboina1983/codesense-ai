"""SQLAlchemy database models for repository management and audit history."""

from __future__ import annotations

import enum
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    Integer,
    Float,
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


# =============================================================================
# Audit History Enums
# =============================================================================

class ArtifactType(str, enum.Enum):
    """Types of artifacts that can be tracked."""
    BRD = "brd"
    EPIC = "epic"
    BACKLOG = "backlog"


class ArtifactAction(str, enum.Enum):
    """Actions that can be performed on artifacts."""
    CREATED = "created"
    REFINED = "refined"
    DELETED = "deleted"


class FeedbackScope(str, enum.Enum):
    """Scope of feedback applied."""
    GLOBAL = "global"
    SECTION = "section"
    ITEM = "item"


class SessionStatus(str, enum.Enum):
    """Status of a generation session."""
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class RepositoryPlatform(str, enum.Enum):
    """Supported repository platforms."""
    GITHUB = "github"
    GITLAB = "gitlab"
    LOCAL = "local"


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
    PAUSED = "paused"              # Analysis paused (can resume)
    CANCELLED = "cancelled"        # Analysis cancelled by user


class AnalysisJobPhase(str, enum.Enum):
    """Phases of an analysis job for checkpointing."""
    PENDING = "pending"
    CLONING = "cloning"
    INDEXING_FILES = "indexing_files"
    PARSING_CODE = "parsing_code"
    BUILDING_GRAPH = "building_graph"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class LogLevel(str, enum.Enum):
    """Log levels for analysis logs."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


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

    # Wiki generation options (stored as JSON)
    wiki_options: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Wiki generation options: enabled, depth, include_* flags"
    )

    # Wiki generation status
    wiki_generated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Whether wiki was generated after analysis"
    )

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


# =============================================================================
# Analysis Checkpointing Models
# =============================================================================

class AnalysisCheckpointDB(Base):
    """Checkpoint for resumable analysis jobs.

    Stores progress and state to enable resuming failed/paused analysis jobs.
    """
    __tablename__ = "analysis_checkpoints"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign key to analysis run
    analysis_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Current phase
    current_phase: Mapped[AnalysisJobPhase] = mapped_column(
        Enum(AnalysisJobPhase),
        default=AnalysisJobPhase.PENDING,
        nullable=False,
    )

    # Progress tracking
    phase_progress_pct: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    total_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_processed_file: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Graph statistics
    nodes_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    relationships_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Phase-specific resume data (JSON blob for flexibility)
    checkpoint_data: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Phase-specific data needed to resume: processed file list, cursor positions, etc."
    )

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

    # Relationships
    analysis_run: Mapped["AnalysisRunDB"] = relationship(
        "AnalysisRunDB",
        backref="checkpoints",
    )

    # Indexes
    __table_args__ = (
        Index("ix_analysis_checkpoints_run_phase", "analysis_run_id", "current_phase"),
        Index("ix_analysis_checkpoints_updated", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<AnalysisCheckpoint(id={self.id}, run={self.analysis_run_id}, phase={self.current_phase})>"


class AnalysisLogDB(Base):
    """Log entries for analysis jobs.

    Stores detailed logs for monitoring and debugging analysis jobs.
    """
    __tablename__ = "analysis_logs"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign key to analysis run
    analysis_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Log content
    level: Mapped[LogLevel] = mapped_column(
        Enum(LogLevel),
        default=LogLevel.INFO,
        nullable=False,
    )
    phase: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    # Relationships
    analysis_run: Mapped["AnalysisRunDB"] = relationship(
        "AnalysisRunDB",
        backref="logs",
    )

    # Indexes
    __table_args__ = (
        Index("ix_analysis_logs_run_level", "analysis_run_id", "level"),
        Index("ix_analysis_logs_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AnalysisLog(id={self.id}, level={self.level}, phase={self.phase})>"


# =============================================================================
# Audit History Models
# =============================================================================

class GenerationSessionDB(Base):
    """Generation session that groups BRD → EPICs → Backlogs.

    Enables linked traceability across the full generation pipeline.
    """
    __tablename__ = "generation_sessions"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Repository reference
    repository_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Source tracking
    brd_id: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_description: Mapped[str] = mapped_column(Text, nullable=False)

    # Linked artifacts (JSON arrays of IDs)
    epic_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    backlog_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    # Status
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus),
        default=SessionStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    # Summary stats
    total_refinements: Mapped[int] = mapped_column(Integer, default=0)
    brd_refinements: Mapped[int] = mapped_column(Integer, default=0)
    epic_refinements: Mapped[int] = mapped_column(Integer, default=0)
    backlog_refinements: Mapped[int] = mapped_column(Integer, default=0)

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
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    repository: Mapped["RepositoryDB"] = relationship("RepositoryDB")
    history_entries: Mapped[list["ArtifactHistoryDB"]] = relationship(
        "ArtifactHistoryDB",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ArtifactHistoryDB.created_at",
    )

    # Indexes
    __table_args__ = (
        Index("ix_generation_sessions_repo_status", "repository_id", "status"),
        Index("ix_generation_sessions_brd_id", "brd_id"),
    )

    def __repr__(self) -> str:
        return f"<GenerationSession(id={self.id}, brd={self.brd_id}, status={self.status})>"

    def add_epic(self, epic_id: str) -> None:
        """Add an EPIC ID to the session."""
        if self.epic_ids is None:
            self.epic_ids = []
        if epic_id not in self.epic_ids:
            self.epic_ids = [*self.epic_ids, epic_id]

    def add_backlog(self, backlog_id: str) -> None:
        """Add a backlog ID to the session."""
        if self.backlog_ids is None:
            self.backlog_ids = []
        if backlog_id not in self.backlog_ids:
            self.backlog_ids = [*self.backlog_ids, backlog_id]

    def mark_completed(self) -> None:
        """Mark the session as completed."""
        self.status = SessionStatus.COMPLETED
        self.completed_at = datetime.utcnow()


class ArtifactHistoryDB(Base):
    """Core audit log table for tracking artifact history.

    Stores complete snapshots with section-level diffs for
    BRDs, EPICs, and Backlogs.
    """
    __tablename__ = "artifact_history"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Session reference (links to generation pipeline)
    session_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("generation_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Artifact identification
    artifact_type: Mapped[ArtifactType] = mapped_column(
        Enum(ArtifactType),
        nullable=False,
        index=True,
    )
    artifact_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Action taken
    action: Mapped[ArtifactAction] = mapped_column(
        Enum(ArtifactAction),
        default=ArtifactAction.CREATED,
        nullable=False,
    )

    # Content snapshots (full artifact state at this version)
    content_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Section-level change tracking
    sections_changed: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="List of section names that changed"
    )
    section_diffs: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Dict of {section_name: {before: str, after: str}}"
    )

    # Feedback tracking
    user_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_scope: Mapped[Optional[FeedbackScope]] = mapped_column(
        Enum(FeedbackScope),
        nullable=True,
    )
    feedback_target: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Section name or item ID if section/item-level feedback"
    )
    changes_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="LLM-generated summary of what changed"
    )

    # Repository and parent tracking
    repository_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("repositories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_artifact_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="BRD ID for EPICs, EPIC ID for Backlogs"
    )

    # Generation metadata
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    generation_mode: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="draft or verified"
    )
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Timestamps and retention
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.utcnow() + timedelta(days=30),
        nullable=False,
        index=True,
    )

    # Optional user tracking
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    session: Mapped[Optional["GenerationSessionDB"]] = relationship(
        "GenerationSessionDB",
        back_populates="history_entries",
    )
    repository: Mapped[Optional["RepositoryDB"]] = relationship("RepositoryDB")

    # Indexes
    __table_args__ = (
        Index("ix_artifact_history_artifact", "artifact_type", "artifact_id"),
        Index("ix_artifact_history_version", "artifact_type", "artifact_id", "version"),
        Index("ix_artifact_history_expires", "expires_at"),
        Index("ix_artifact_history_session", "session_id"),
    )

    def __repr__(self) -> str:
        return f"<ArtifactHistory(id={self.id}, artifact={self.artifact_type.value}:{self.artifact_id}, v{self.version})>"


class AuditConfigDB(Base):
    """Configurable audit settings including retention period.

    Stores key-value configuration for audit behavior.
    """
    __tablename__ = "audit_config"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Configuration
    config_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )
    config_value: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<AuditConfig(key={self.config_key}, value={self.config_value})>"

    @staticmethod
    def get_default_configs() -> list[dict]:
        """Return default configuration entries."""
        return [
            {
                "config_key": "retention_days",
                "config_value": "30",
                "description": "Number of days to retain audit history before cleanup"
            },
            {
                "config_key": "diff_detail_level",
                "config_value": "section",
                "description": "Diff detail level: 'section' or 'full'"
            },
        ]


# =============================================================================
# Document Storage Models (BRD, EPIC, Backlog)
# =============================================================================

class DocumentStatus(str, enum.Enum):
    """Status of a document in the BRD library."""
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    APPROVED = "approved"
    ARCHIVED = "archived"


class BacklogItemType(str, enum.Enum):
    """Types of backlog items."""
    USER_STORY = "user_story"
    TASK = "task"
    SPIKE = "spike"
    BUG = "bug"


class EpicPriority(str, enum.Enum):
    """Priority levels for EPICs and backlogs."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BRDDB(Base):
    """Stored BRD document.

    Central table for managing Business Requirements Documents with
    relationships to EPICs and tracking of generation metadata.
    """
    __tablename__ = "brds"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Document identifier (user-facing)
    brd_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )  # e.g., BRD-0001

    # Core content
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    feature_description: Mapped[str] = mapped_column(Text, nullable=False)
    markdown_content: Mapped[str] = mapped_column(Text, nullable=False)

    # Structured sections (JSON array of section objects)
    sections: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Parsed sections: [{name, content, order}]"
    )

    # Repository reference
    repository_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Generation metadata
    mode: Mapped[str] = mapped_column(
        String(50),
        default="draft",
        nullable=False,
    )  # draft or verified
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verification_report: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Status and versioning
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus),
        default=DocumentStatus.DRAFT,
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    refinement_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

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

    # Relationships
    repository: Mapped["RepositoryDB"] = relationship("RepositoryDB")
    epics: Mapped[list["EpicDB"]] = relationship(
        "EpicDB",
        back_populates="brd",
        cascade="all, delete-orphan",
        order_by="EpicDB.display_order",
    )

    # Indexes
    __table_args__ = (
        Index("ix_brds_repo_status", "repository_id", "status"),
        Index("ix_brds_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<BRDDB(id={self.id}, number={self.brd_number}, title={self.title[:30]}...)>"

    @property
    def epic_count(self) -> int:
        """Return count of EPICs."""
        return len(self.epics) if self.epics else 0

    @property
    def backlog_count(self) -> int:
        """Return total count of backlogs across all EPICs."""
        if not self.epics:
            return 0
        return sum(len(epic.backlogs) if epic.backlogs else 0 for epic in self.epics)


class EpicDB(Base):
    """Stored EPIC document.

    EPICs are derived from BRDs and contain multiple backlog items.
    """
    __tablename__ = "epics"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Document identifier
    epic_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )  # e.g., EPIC-001

    # Parent BRD reference
    brd_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("brds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Core content
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    business_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Structured data
    objectives: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    acceptance_criteria: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    affected_components: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    depends_on: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="List of EPIC IDs this depends on"
    )

    # Priority and estimation
    priority: Mapped[EpicPriority] = mapped_column(
        Enum(EpicPriority),
        default=EpicPriority.MEDIUM,
        nullable=False,
    )
    estimated_effort: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )  # xs, small, medium, large, xlarge

    # Status and ordering
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus),
        default=DocumentStatus.DRAFT,
        nullable=False,
        index=True,
    )
    refinement_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

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

    # Relationships
    brd: Mapped["BRDDB"] = relationship("BRDDB", back_populates="epics")
    backlogs: Mapped[list["BacklogDB"]] = relationship(
        "BacklogDB",
        back_populates="epic",
        cascade="all, delete-orphan",
        order_by="BacklogDB.display_order",
    )

    # Indexes
    __table_args__ = (
        Index("ix_epics_brd_status", "brd_id", "status"),
        Index("ix_epics_priority", "priority"),
    )

    def __repr__(self) -> str:
        return f"<EpicDB(id={self.id}, number={self.epic_number}, title={self.title[:30]}...)>"

    @property
    def backlog_count(self) -> int:
        """Return count of backlogs."""
        return len(self.backlogs) if self.backlogs else 0


class BacklogDB(Base):
    """Stored Backlog item.

    Backlog items are derived from EPICs and represent work items
    like user stories, tasks, spikes, or bugs.
    """
    __tablename__ = "backlogs"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Document identifier
    backlog_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )  # e.g., STORY-001

    # Parent EPIC reference
    epic_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("epics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Core content
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    item_type: Mapped[BacklogItemType] = mapped_column(
        Enum(BacklogItemType),
        default=BacklogItemType.USER_STORY,
        nullable=False,
    )

    # User story format
    as_a: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    i_want: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    so_that: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Structured data
    acceptance_criteria: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    technical_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    files_to_modify: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    files_to_create: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Priority and estimation
    priority: Mapped[EpicPriority] = mapped_column(
        Enum(EpicPriority),
        default=EpicPriority.MEDIUM,
        nullable=False,
    )
    story_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Status and ordering
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus),
        default=DocumentStatus.DRAFT,
        nullable=False,
        index=True,
    )
    refinement_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

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

    # Relationships
    epic: Mapped["EpicDB"] = relationship("EpicDB", back_populates="backlogs")

    # Indexes
    __table_args__ = (
        Index("ix_backlogs_epic_status", "epic_id", "status"),
        Index("ix_backlogs_type", "item_type"),
        Index("ix_backlogs_priority", "priority"),
    )

    def __repr__(self) -> str:
        return f"<BacklogDB(id={self.id}, number={self.backlog_number}, type={self.item_type.value})>"

    @property
    def user_story_format(self) -> str:
        """Return the user story in standard format."""
        if self.item_type == BacklogItemType.USER_STORY and self.as_a:
            return f"As a {self.as_a}, I want {self.i_want}, so that {self.so_that}"
        return ""


# =============================================================================
# Wiki Documentation Models (DeepWiki-style)
# =============================================================================

class WikiStatus(str, enum.Enum):
    """Status of wiki generation."""
    NOT_GENERATED = "not_generated"
    GENERATING = "generating"
    GENERATED = "generated"
    STALE = "stale"  # Code changed since generation
    FAILED = "failed"


class WikiPageType(str, enum.Enum):
    """Types of wiki pages (DeepWiki-style concept-based documentation)."""
    # Overview & Architecture
    OVERVIEW = "overview"
    ARCHITECTURE = "architecture"
    TECH_STACK = "tech_stack"

    # User Guide
    GETTING_STARTED = "getting_started"
    INSTALLATION = "installation"
    CONFIGURATION = "configuration"
    DEPLOYMENT = "deployment"

    # Core Systems (dynamically discovered concepts)
    CONCEPT = "concept"              # LLM-discovered system/concept
    CORE_SYSTEM = "core_system"      # Major system component

    # Features (dynamically discovered)
    FEATURE = "feature"              # Business feature/capability

    # Technical Reference
    API = "api"
    DATA_MODEL = "data_model"
    INTEGRATION = "integration"      # External integrations

    # Code Structure (optional detailed view)
    MODULE = "module"
    CLASS = "class"
    PATTERN = "pattern"

    # Custom pages (advanced mode)
    CUSTOM = "custom"                # User-defined custom page


class WikiDB(Base):
    """Wiki metadata for a repository.

    Tracks overall wiki generation status and configuration.
    """
    __tablename__ = "wikis"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Repository reference
    repository_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Generation status
    status: Mapped[WikiStatus] = mapped_column(
        Enum(WikiStatus),
        default=WikiStatus.NOT_GENERATED,
        nullable=False,
        index=True,
    )
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Source tracking
    commit_sha: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Git commit SHA when wiki was generated"
    )

    # Statistics
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    stale_pages: Mapped[int] = mapped_column(Integer, default=0)

    # Generation mode tracking
    generation_mode: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        default="template",
        comment="Generation mode: 'llm-powered' or 'template'"
    )

    # Configuration (user preferences)
    config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Wiki generation config: depth, included sections, etc."
    )

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
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    repository: Mapped["RepositoryDB"] = relationship("RepositoryDB")
    pages: Mapped[list["WikiPageDB"]] = relationship(
        "WikiPageDB",
        back_populates="wiki",
        cascade="all, delete-orphan",
        order_by="WikiPageDB.display_order",
    )

    def __repr__(self) -> str:
        return f"<WikiDB(id={self.id}, repo={self.repository_id}, status={self.status})>"


class WikiPageDB(Base):
    """Individual wiki page.

    Stores generated documentation content with source references.
    """
    __tablename__ = "wiki_pages"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Parent wiki reference
    wiki_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("wikis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Page identity
    slug: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        comment="URL-friendly path: e.g., 'modules/legal-entity'"
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    page_type: Mapped[WikiPageType] = mapped_column(
        Enum(WikiPageType),
        nullable=False,
        index=True,
    )

    # Content
    markdown_content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Brief summary for search results and previews"
    )

    # Source references (what this page documents)
    source_files: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="List of source file paths this page documents"
    )
    source_entities: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="Neo4j entity IDs (classes, functions) this page covers"
    )

    # Hierarchy
    parent_slug: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        index=True,
        comment="Parent page slug for navigation tree"
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    # Related pages (cross-references)
    related_pages: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="List of related page slugs"
    )

    # Staleness tracking
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    stale_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Generation metadata
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    generation_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

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

    # Relationships
    wiki: Mapped["WikiDB"] = relationship("WikiDB", back_populates="pages")

    # Indexes
    __table_args__ = (
        Index("ix_wiki_pages_wiki_slug", "wiki_id", "slug", unique=True),
        Index("ix_wiki_pages_type", "page_type"),
        Index("ix_wiki_pages_parent", "parent_slug"),
    )

    def __repr__(self) -> str:
        return f"<WikiPageDB(id={self.id}, slug={self.slug}, type={self.page_type})>"
