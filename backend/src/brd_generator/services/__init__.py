"""Services for BRD Generator."""

from .git_client import GitClient, GitStatus
from .platform_client import GitHubClient, GitLabClient, PlatformClient, create_platform_client
from .mcp_configurator import MCPConfigurator
from .repository_service import RepositoryService

__all__ = [
    "GitClient",
    "GitStatus",
    "GitHubClient",
    "GitLabClient",
    "PlatformClient",
    "create_platform_client",
    "MCPConfigurator",
    "RepositoryService",
]
