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
]
