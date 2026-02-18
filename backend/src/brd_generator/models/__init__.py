"""Data models for BRD Generator."""

from .request import BRDRequest
from .context import (
    AggregatedContext,
    ArchitectureContext,
    ImplementationContext,
    ComponentInfo,
    APIContract,
    DataModel,
    FileContext,
)
from .output import (
    BRDOutput,
    BRDDocument,
    Epic,
    UserStory,
    Requirement,
    AcceptanceCriteria,
    EpicsOutput,
    BacklogsOutput,
    JiraCreationResult,
)
from .repository import (
    Repository,
    RepositoryBase,
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
# Enhanced EPIC and Backlog models with traceability
from .epic import (
    # Enums
    EpicStatus,
    BacklogItemType,
    Priority,
    EffortSize,
    # Template configuration models
    EpicFieldConfig,
    EpicTemplateConfig,
    BacklogFieldConfig,
    BacklogTemplateConfig,
    # Core models
    ProjectContext,
    Epic as TrackedEpic,
    BacklogItem,
    # Request models
    GenerateEpicsRequest,
    RefineEpicRequest,
    RefineAllEpicsRequest,
    GenerateBacklogsRequest,
    RefineBacklogItemRequest,
    RegenerateBacklogsForEpicRequest,
    # Response models
    CoverageMatrixEntry,
    GenerateEpicsResponse,
    GenerateBacklogsResponse,
    TraceabilityMatrixResponse,
    # Streaming events
    EpicStreamEvent,
    BacklogStreamEvent,
)
# BRD refinement and audit history models
from .brd import (
    # Enums
    BRDStatus,
    FeedbackType,
    # Core models
    BRDSection,
    RefinementEntry,
    RefinedBRD,
    # Request models
    RefineBRDSectionRequest,
    RefineEntireBRDRequest,
    # Response models
    RefineBRDSectionResponse,
    RefineEntireBRDResponse,
    # Audit history models
    ArtifactHistoryEntry,
    ArtifactHistoryResponse,
    SessionHistoryResponse,
    VersionDiffResponse,
)

__all__ = [
    "BRDRequest",
    "AggregatedContext",
    "ArchitectureContext",
    "ImplementationContext",
    "ComponentInfo",
    "APIContract",
    "DataModel",
    "FileContext",
    "BRDOutput",
    "BRDDocument",
    "Epic",
    "UserStory",
    "Requirement",
    "AcceptanceCriteria",
    "EpicsOutput",
    "BacklogsOutput",
    "JiraCreationResult",
    # Repository models
    "Repository",
    "RepositoryBase",
    "RepositoryCreate",
    "RepositoryUpdate",
    "RepositorySummary",
    "RepositoryPlatform",
    "RepositoryStatus",
    "AnalysisStatus",
    "AnalysisRun",
    "AnalysisRunCreate",
    "AnalysisRunSummary",
    "RepositoryCredentials",
    "LocalRepositoryCreate",
    # Enhanced EPIC/Backlog models with traceability
    "EpicStatus",
    "BacklogItemType",
    "Priority",
    "EffortSize",
    # Template configuration models
    "EpicFieldConfig",
    "EpicTemplateConfig",
    "BacklogFieldConfig",
    "BacklogTemplateConfig",
    "ProjectContext",
    "TrackedEpic",
    "BacklogItem",
    "GenerateEpicsRequest",
    "RefineEpicRequest",
    "RefineAllEpicsRequest",
    "GenerateBacklogsRequest",
    "RefineBacklogItemRequest",
    "RegenerateBacklogsForEpicRequest",
    "CoverageMatrixEntry",
    "GenerateEpicsResponse",
    "GenerateBacklogsResponse",
    "TraceabilityMatrixResponse",
    "EpicStreamEvent",
    "BacklogStreamEvent",
    # BRD refinement models
    "BRDStatus",
    "FeedbackType",
    "BRDSection",
    "RefinementEntry",
    "RefinedBRD",
    "RefineBRDSectionRequest",
    "RefineEntireBRDRequest",
    "RefineBRDSectionResponse",
    "RefineEntireBRDResponse",
    # Audit history models
    "ArtifactHistoryEntry",
    "ArtifactHistoryResponse",
    "SessionHistoryResponse",
    "VersionDiffResponse",
]
