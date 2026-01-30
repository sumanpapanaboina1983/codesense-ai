"""Dynamic MCP server configuration for repositories."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..models.repository import Repository, RepositoryPlatform, RepositoryCredentials
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MCPServerDefinition:
    """MCP server definition for session configuration."""

    name: str
    type: str = "stdio"
    command: str = "npx"
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    tools: list[str] = field(default_factory=lambda: ["*"])
    timeout: int = 30000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for MCP config."""
        return {
            "type": self.type,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "tools": self.tools,
            "timeout": self.timeout,
        }


class MCPConfigurator:
    """Manages MCP server configuration for repositories.

    Builds MCP configurations that can be used with Copilot SDK sessions
    to provide LLM access to repository files via various MCP servers.
    """

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
        neo4j_database: Optional[str] = None,
    ):
        """Initialize MCP configurator.

        Args:
            config_dir: Directory for MCP config files.
            neo4j_uri: Neo4j connection URI.
            neo4j_user: Neo4j username.
            neo4j_password: Neo4j password.
            neo4j_database: Neo4j database name.
        """
        self.config_dir = config_dir or Path(
            os.getenv("MCP_CONFIG_DIR", str(Path.home() / ".copilot"))
        )
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Neo4j configuration
        self.neo4j_uri = neo4j_uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user = neo4j_user or os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = neo4j_password or os.getenv("NEO4J_PASSWORD", "password")
        self.neo4j_database = neo4j_database or os.getenv("NEO4J_DATABASE", "codegraph")

    def build_github_server(
        self,
        token: str,
        name: str = "github",
    ) -> MCPServerDefinition:
        """Build GitHub MCP server configuration.

        Args:
            token: GitHub personal access token.
            name: Server name.

        Returns:
            MCPServerDefinition for GitHub MCP server.
        """
        return MCPServerDefinition(
            name=name,
            type="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": token},
            timeout=60000,
        )

    def build_gitlab_server(
        self,
        token: str,
        gitlab_url: str = "https://gitlab.com",
        name: str = "gitlab",
    ) -> MCPServerDefinition:
        """Build GitLab MCP server configuration using official GitLab MCP.

        Uses mcp-remote to connect to GitLab's native MCP server endpoint.
        See: https://docs.gitlab.com/user/gitlab_duo/model_context_protocol/mcp_server/

        Args:
            token: GitLab personal access token.
            gitlab_url: GitLab instance URL (default: https://gitlab.com).
            name: Server name.

        Returns:
            MCPServerDefinition for GitLab MCP server.
        """
        mcp_endpoint = f"{gitlab_url.rstrip('/')}/api/v4/mcp"
        return MCPServerDefinition(
            name=name,
            type="stdio",
            command="npx",
            args=["-y", "mcp-remote", mcp_endpoint],
            env={
                "GITLAB_TOKEN": token,
            },
            timeout=60000,
        )

    def build_filesystem_server(
        self,
        path: Path,
        name: str = "filesystem",
    ) -> MCPServerDefinition:
        """Build filesystem MCP server configuration.

        Args:
            path: Path to expose via filesystem server.
            name: Server name.

        Returns:
            MCPServerDefinition for filesystem MCP server.
        """
        return MCPServerDefinition(
            name=name,
            type="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", str(path)],
            timeout=30000,
        )

    def build_neo4j_server(
        self,
        name: str = "neo4j-code-graph",
        read_only: bool = True,
    ) -> MCPServerDefinition:
        """Build Neo4j MCP server configuration.

        Args:
            name: Server name.
            read_only: Whether to enable read-only mode.

        Returns:
            MCPServerDefinition for Neo4j MCP server.
        """
        return MCPServerDefinition(
            name=name,
            type="stdio",
            command="npx",
            args=["-y", "@neobarrientos/neo4j_mcpserver"],
            env={
                "NEO4J_URI": self.neo4j_uri,
                "NEO4J_USERNAME": self.neo4j_user,
                "NEO4J_PASSWORD": self.neo4j_password,
                "NEO4J_DATABASE": self.neo4j_database,
                "NEO4J_READ_ONLY": str(read_only).lower(),
            },
            timeout=30000,
        )

    def configure_platform_server(
        self,
        repository: Repository,
        credentials: RepositoryCredentials,
    ) -> MCPServerDefinition:
        """Configure platform-specific MCP server for a repository.

        Args:
            repository: The repository to configure for.
            credentials: Repository credentials.

        Returns:
            MCPServerDefinition for the platform MCP server.
        """
        name = f"{repository.platform.value}-{repository.id[:8]}"

        if repository.platform == RepositoryPlatform.GITHUB:
            return self.build_github_server(
                token=credentials.token,
                name=name,
            )
        elif repository.platform == RepositoryPlatform.GITLAB:
            # Extract base GitLab URL from api_url if provided
            gitlab_url = "https://gitlab.com"
            if credentials.api_url:
                # api_url is like "https://gitlab.example.com/api/v4"
                gitlab_url = credentials.api_url.replace("/api/v4", "").rstrip("/")
            return self.build_gitlab_server(
                token=credentials.token,
                gitlab_url=gitlab_url,
                name=name,
            )
        else:
            raise ValueError(f"Unsupported platform: {repository.platform}")

    def configure_filesystem_server(
        self,
        repository: Repository,
    ) -> MCPServerDefinition:
        """Configure filesystem MCP server for a repository's local clone.

        Args:
            repository: The repository with local_path set.

        Returns:
            MCPServerDefinition for filesystem MCP server.

        Raises:
            ValueError: If repository has no local_path.
        """
        if not repository.local_path:
            raise ValueError(f"Repository {repository.id} has no local path")

        name = f"filesystem-{repository.id[:8]}"
        return self.build_filesystem_server(
            path=Path(repository.local_path),
            name=name,
        )

    def build_session_mcp_config(
        self,
        repository: Repository,
        credentials: Optional[RepositoryCredentials] = None,
        include_filesystem: bool = True,
        include_platform: bool = True,
        include_neo4j: bool = True,
    ) -> dict[str, Any]:
        """Build complete MCP server configuration for a Copilot session.

        This builds the mcp_servers dict that can be passed to
        CopilotClient.create_session() for repository-scoped BRD generation.

        Args:
            repository: The repository to build config for.
            credentials: Optional credentials for platform MCP.
            include_filesystem: Include filesystem server for local clone.
            include_platform: Include platform server (GitHub/GitLab).
            include_neo4j: Include Neo4j code graph server.

        Returns:
            Dictionary of MCP server configurations.
        """
        mcp_servers: dict[str, Any] = {}

        # Filesystem MCP for local clone
        if include_filesystem and repository.local_path:
            server = self.configure_filesystem_server(repository)
            mcp_servers[server.name] = server.to_dict()
            logger.debug(f"Added filesystem MCP: {server.name}")

        # Platform MCP (GitHub/GitLab)
        if include_platform and credentials:
            server = self.configure_platform_server(repository, credentials)
            mcp_servers[server.name] = server.to_dict()
            logger.debug(f"Added platform MCP: {server.name}")

        # Neo4j code graph MCP
        if include_neo4j:
            server = self.build_neo4j_server()
            mcp_servers[server.name] = server.to_dict()
            logger.debug(f"Added Neo4j MCP: {server.name}")

        logger.info(
            f"Built MCP config for repository {repository.name} "
            f"with servers: {list(mcp_servers.keys())}"
        )

        return mcp_servers

    def get_mcp_servers_list(
        self,
        repository: Repository,
        credentials: Optional[RepositoryCredentials] = None,
        include_filesystem: bool = True,
        include_platform: bool = True,
        include_neo4j: bool = True,
    ) -> list[MCPServerDefinition]:
        """Get list of MCP server definitions for a repository.

        Args:
            repository: The repository to build config for.
            credentials: Optional credentials for platform MCP.
            include_filesystem: Include filesystem server.
            include_platform: Include platform server.
            include_neo4j: Include Neo4j server.

        Returns:
            List of MCPServerDefinition objects.
        """
        servers: list[MCPServerDefinition] = []

        if include_filesystem and repository.local_path:
            servers.append(self.configure_filesystem_server(repository))

        if include_platform and credentials:
            servers.append(self.configure_platform_server(repository, credentials))

        if include_neo4j:
            servers.append(self.build_neo4j_server())

        return servers

    def save_mcp_config(
        self,
        servers: dict[str, Any],
        filename: str = "mcp-config.json",
    ) -> Path:
        """Save MCP configuration to file.

        Args:
            servers: MCP servers configuration.
            filename: Config filename.

        Returns:
            Path to the saved config file.
        """
        config = {"mcp_servers": servers}
        config_path = self.config_dir / filename

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Saved MCP config to {config_path}")
        return config_path

    def load_mcp_config(
        self,
        filename: str = "mcp-config.json",
    ) -> dict[str, Any]:
        """Load MCP configuration from file.

        Args:
            filename: Config filename.

        Returns:
            MCP servers configuration.
        """
        config_path = self.config_dir / filename

        if not config_path.exists():
            return {}

        with open(config_path, "r") as f:
            config = json.load(f)

        return config.get("mcp_servers", {})

    def merge_mcp_configs(
        self,
        *configs: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge multiple MCP configurations.

        Later configs override earlier ones for same server names.

        Args:
            *configs: MCP server configurations to merge.

        Returns:
            Merged configuration.
        """
        merged: dict[str, Any] = {}
        for config in configs:
            merged.update(config)
        return merged

    def remove_repository_servers(
        self,
        repository_id: str,
        current_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Remove all MCP servers associated with a repository.

        Args:
            repository_id: Repository ID prefix to match.
            current_config: Current MCP configuration.

        Returns:
            Updated configuration with repository servers removed.
        """
        prefix = repository_id[:8]
        return {
            name: config
            for name, config in current_config.items()
            if prefix not in name
        }
