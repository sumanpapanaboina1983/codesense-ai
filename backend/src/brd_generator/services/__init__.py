"""Services for BRD Generator."""

from .git_client import GitClient, GitStatus
from .platform_client import GitHubClient, GitLabClient, PlatformClient, create_platform_client
from .mcp_configurator import MCPConfigurator
from .repository_service import RepositoryService
from .audit_service import AuditService
from .document_service import DocumentService

# Note: CodeAssistantService is imported directly where needed to avoid circular imports
# from .code_assistant_service import CodeAssistantService

__all__ = [
    "GitClient",
    "GitStatus",
    "GitHubClient",
    "GitLabClient",
    "PlatformClient",
    "create_platform_client",
    "MCPConfigurator",
    "RepositoryService",
    "AuditService",
    "DocumentService",
]
