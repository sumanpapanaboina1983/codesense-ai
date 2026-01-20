"""
API dependencies for dependency injection.
"""

from functools import lru_cache
from typing import Optional

from src.agentic.reasoning_engine import ReasoningEngine
from src.agentic.verification_engine import VerificationEngine
from src.copilot.sdk_client import CopilotSDKClient
from src.core.config import settings
from src.mcp.neo4j_client import Neo4jMCPClient
from src.mcp.filesystem_client import FilesystemMCPClient
from src.mcp.tool_registry import MCPToolRegistry
from src.orchestration.workflow_engine import WorkflowEngine
from src.repositories.cache_repo import InMemoryCacheRepository
from src.repositories.document_repo import InMemoryDocumentRepository
from src.repositories.session_repo import InMemorySessionRepository
from src.services.analysis_service import AnalysisService
from src.services.document_service import DocumentService
from src.services.session_manager import SessionManager
from src.skills.registry import SkillRegistry


class ServiceContainer:
    """
    Container for all application services.
    Provides singleton instances of services.
    """

    _instance: Optional["ServiceContainer"] = None

    def __init__(self) -> None:
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "ServiceContainer":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self) -> None:
        """Initialize all services."""
        if self._initialized:
            return

        # Initialize MCP clients
        self._neo4j_client = Neo4jMCPClient()  # Uses settings.neo4j.mcp_url by default
        self._filesystem_client = FilesystemMCPClient()  # Uses settings.filesystem.mcp_url by default

        # Initialize tool registry with MCP clients
        self._tool_registry = MCPToolRegistry(
            neo4j_client=self._neo4j_client,
            filesystem_client=self._filesystem_client,
        )

        # Initialize Copilot client
        self._copilot_client = CopilotSDKClient(
            api_key=settings.copilot.api_key,
            model=settings.copilot.model,
        )

        # Initialize skill registry
        self._skill_registry = SkillRegistry()

        # Initialize engines
        self._reasoning_engine = ReasoningEngine(
            self._copilot_client,
            self._tool_registry,
        )

        self._verification_engine = VerificationEngine(
            self._tool_registry,
        )

        # Initialize repositories
        self._session_repository = InMemorySessionRepository()
        self._document_repository = InMemoryDocumentRepository()
        self._cache_repository = InMemoryCacheRepository()

        # Initialize workflow engine
        self._workflow_engine = WorkflowEngine(
            copilot_client=self._copilot_client,
            tool_registry=self._tool_registry,
            skill_registry=self._skill_registry,
            reasoning_engine=self._reasoning_engine,
            verification_engine=self._verification_engine,
        )

        # Initialize services
        self._document_service = DocumentService(
            workflow_engine=self._workflow_engine,
            document_repository=self._document_repository,
        )

        self._analysis_service = AnalysisService(
            tool_registry=self._tool_registry,
            reasoning_engine=self._reasoning_engine,
        )

        self._session_manager = SessionManager(
            copilot_client=self._copilot_client,
            tool_registry=self._tool_registry,
            session_repository=self._session_repository,
        )

        self._initialized = True

    @property
    def session_manager(self) -> SessionManager:
        """Get the session manager."""
        self.initialize()
        return self._session_manager

    @property
    def document_service(self) -> DocumentService:
        """Get the document service."""
        self.initialize()
        return self._document_service

    @property
    def analysis_service(self) -> AnalysisService:
        """Get the analysis service."""
        self.initialize()
        return self._analysis_service

    @property
    def tool_registry(self) -> MCPToolRegistry:
        """Get the tool registry."""
        self.initialize()
        return self._tool_registry

    @property
    def copilot_client(self) -> CopilotSDKClient:
        """Get the Copilot client."""
        self.initialize()
        return self._copilot_client

    @property
    def cache(self) -> InMemoryCacheRepository:
        """Get the cache repository."""
        self.initialize()
        return self._cache_repository


# Singleton container instance
container = ServiceContainer.get_instance()


# Dependency functions for FastAPI
def get_session_manager() -> SessionManager:
    """Get the session manager instance."""
    return container.session_manager


def get_document_service() -> DocumentService:
    """Get the document service instance."""
    return container.document_service


def get_analysis_service() -> AnalysisService:
    """Get the analysis service instance."""
    return container.analysis_service


def get_tool_registry() -> MCPToolRegistry:
    """Get the tool registry instance."""
    return container.tool_registry


def get_cache() -> InMemoryCacheRepository:
    """Get the cache repository instance."""
    return container.cache


def get_copilot_client() -> CopilotSDKClient:
    """Get the Copilot SDK client instance."""
    return container.copilot_client
