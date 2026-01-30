"""Filesystem MCP client for source code access."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from .base import MCPClient, MCPToolError
from ..utils.logger import get_logger

logger = get_logger(__name__)


class FilesystemMCPClient(MCPClient):
    """
    Client for Filesystem MCP server.

    Provides methods to read source files and navigate directories.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        workspace_root: Optional[Path] = None,
        timeout: int = 30,
    ):
        """
        Initialize Filesystem MCP client.

        Args:
            server_url: MCP server URL (defaults to env FILESYSTEM_MCP_URL)
            workspace_root: Root path for codebase
            timeout: Request timeout in seconds
        """
        url = server_url or os.getenv("FILESYSTEM_MCP_URL", "http://localhost:3004")
        super().__init__(
            server_name="filesystem-reader",
            server_url=url,
            timeout=timeout,
        )

        codebase_root = os.getenv("CODEBASE_ROOT", str(Path.cwd()))
        self.workspace_root = workspace_root or Path(codebase_root)

    async def connect(self) -> None:
        """Initialize connection."""
        logger.info(f"Filesystem MCP client connecting to: {self.server_url}")
        logger.info(f"Workspace root: {self.workspace_root}")

        # Verify connection with health check
        if self.server_url:
            try:
                healthy = await self.health_check()
                if healthy:
                    logger.info("Filesystem MCP server connection verified")
                else:
                    logger.warning("Filesystem MCP server unhealthy, continuing anyway")
            except Exception as e:
                logger.warning(f"Filesystem MCP health check failed: {e}")

        self._connected = True

    async def disconnect(self) -> None:
        """Close connection."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._connected = False
        logger.info("Filesystem MCP client disconnected")

    async def health_check(self) -> bool:
        """Check if Filesystem MCP server is healthy."""
        try:
            result = await self._http_get("/health")
            return result.get("status") in ["healthy", "degraded"]
        except Exception as e:
            logger.warning(f"Filesystem health check failed: {e}")
            return False

    async def call_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> Any:
        """
        Call Filesystem MCP tool.

        Args:
            tool_name: Name of the tool
            parameters: Tool parameters

        Returns:
            Tool result
        """
        if not self._connected:
            raise MCPToolError("Filesystem MCP client not connected")

        # Map tool names to HTTP endpoints
        tool_handlers = {
            "read_file": self._read_file,
            "search_files": self._search_files,
            "get_file_metadata": self._get_file_metadata,
            "read_multiple_files": self._read_multiple_files,
            "list_directory": self._list_directory,
        }

        handler = tool_handlers.get(tool_name)
        if not handler:
            raise MCPToolError(f"Unknown tool: {tool_name}")

        return await handler(**parameters)

    def _resolve_path(self, path: str) -> str:
        """Resolve path relative to workspace root."""
        if path.startswith(str(self.workspace_root)):
            return path

        # Remove leading slash for joining
        if path.startswith("/"):
            path = path[1:]

        return str(self.workspace_root / path)

    async def _read_file(self, path: str) -> str:
        """Read file content via MCP server."""
        resolved_path = self._resolve_path(path)
        result = await self._http_post("/read", {"path": resolved_path})
        return result.get("content", "")

    async def _search_files(
        self,
        pattern: str,
        include_content: bool = False,
    ) -> list[dict[str, Any]]:
        """Search files by glob pattern."""
        result = await self._http_post("/find", {
            "pattern": pattern,
            "root": str(self.workspace_root),
            "max_results": 100,
        })
        files = result.get("files", [])

        if include_content:
            # Fetch content for each file
            for i, file_path in enumerate(files):
                try:
                    content = await self._read_file(file_path)
                    files[i] = {"path": file_path, "content": content}
                except Exception as e:
                    files[i] = {"path": file_path, "error": str(e)}

        return files

    async def _get_file_metadata(self, path: str) -> dict[str, Any]:
        """Get file metadata."""
        resolved_path = self._resolve_path(path)
        return await self._http_post("/metadata", {"path": resolved_path})

    async def _read_multiple_files(self, paths: list[str]) -> dict[str, str]:
        """Batch read multiple files."""
        results = {}
        for path in paths:
            try:
                content = await self._read_file(path)
                results[path] = content
            except Exception as e:
                results[path] = f"Error: {str(e)}"
        return results

    async def _list_directory(self, path: str = "") -> list[dict[str, Any]]:
        """List directory contents."""
        resolved_path = self._resolve_path(path) if path else str(self.workspace_root)
        result = await self._http_post("/list", {"path": resolved_path})
        return result.get("entries", [])

    # Convenience methods

    async def read_file(self, path: str) -> str:
        """Read file content."""
        return await self.call_tool("read_file", {"path": path})

    async def search_files(
        self,
        pattern: str,
        include_content: bool = False,
    ) -> list[dict[str, Any]]:
        """Search files by glob pattern."""
        return await self.call_tool("search_files", {
            "pattern": pattern,
            "include_content": include_content,
        })

    async def get_file_metadata(self, path: str) -> dict[str, Any]:
        """Get file metadata."""
        return await self.call_tool("get_file_metadata", {"path": path})

    async def read_multiple_files(self, paths: list[str]) -> dict[str, str]:
        """Batch read multiple files."""
        return await self.call_tool("read_multiple_files", {"paths": paths})

    async def list_directory(self, path: str = "") -> list[dict[str, Any]]:
        """List directory contents."""
        return await self.call_tool("list_directory", {"path": path})
