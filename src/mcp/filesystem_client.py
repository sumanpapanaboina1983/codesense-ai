"""
Filesystem MCP client for source code access.
Provides methods to read and search source files.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from src.core.config import settings
from src.core.exceptions import MCPError
from src.core.logging import get_logger
from src.mcp.base_client import BaseMCPClient

logger = get_logger(__name__)


@dataclass
class FileInfo:
    """Information about a file or directory."""

    path: str
    name: str
    type: str  # 'file' or 'directory'
    size_bytes: int
    modified_time: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileInfo":
        """Create FileInfo from dictionary."""
        modified = data.get("modified_time")
        if modified and isinstance(modified, str):
            modified = datetime.fromisoformat(modified.replace("Z", "+00:00"))

        return cls(
            path=data["path"],
            name=data["name"],
            type=data["type"],
            size_bytes=data.get("size_bytes", 0),
            modified_time=modified,
        )


@dataclass
class FileMetadata:
    """Detailed metadata about a file."""

    path: str
    size_bytes: int
    language: str
    loc: int  # Lines of code
    encoding: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileMetadata":
        """Create FileMetadata from dictionary."""
        return cls(
            path=data["path"],
            size_bytes=data.get("size_bytes", 0),
            language=data.get("language", "unknown"),
            loc=data.get("loc", 0),
            encoding=data.get("encoding", "utf-8"),
        )


@dataclass
class FileContent:
    """Content read from a file."""

    path: str
    content: str
    start_line: int = 1
    end_line: Optional[int] = None
    total_lines: int = 0
    truncated: bool = False


class FilesystemMCPClient(BaseMCPClient):
    """
    MCP client for filesystem access.
    Provides methods to read source files and navigate directories.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        codebase_root: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        """
        Initialize the Filesystem MCP client.

        Args:
            server_url: MCP server URL (defaults to settings)
            codebase_root: Root path for codebase (defaults to settings)
            timeout: Request timeout in seconds
        """
        url = server_url or settings.filesystem.mcp_url
        super().__init__(server_url=url, timeout=timeout)
        self.codebase_root = codebase_root or settings.filesystem.codebase_root
        self.max_file_size = settings.filesystem.max_file_size_mb * 1024 * 1024

    @property
    def mcp_type(self) -> str:
        return "Filesystem"

    async def health_check(self) -> bool:
        """Check if Filesystem MCP server is healthy."""
        try:
            result = await self._get("/health")
            return result.get("status") == "healthy"
        except Exception as e:
            logger.warning("Filesystem health check failed", error=str(e))
            return False

    def _resolve_path(self, path: str) -> str:
        """
        Resolve a path relative to codebase root.

        Args:
            path: Relative or absolute path

        Returns:
            Absolute path within codebase
        """
        if path.startswith(self.codebase_root):
            return path

        # Remove leading slash for joining
        if path.startswith("/"):
            path = path[1:]

        return f"{self.codebase_root}/{path}"

    async def read_file(self, path: str) -> FileContent:
        """
        Read an entire file.

        Args:
            path: Path to the file

        Returns:
            FileContent with the file's contents

        Raises:
            MCPError: If file cannot be read
        """
        resolved_path = self._resolve_path(path)

        logger.debug("Reading file", path=resolved_path)

        response = await self._post(
            "/read",
            data={"path": resolved_path},
        )

        content = response.get("content", "")
        lines = content.split("\n")

        return FileContent(
            path=resolved_path,
            content=content,
            start_line=1,
            end_line=len(lines),
            total_lines=len(lines),
            truncated=response.get("truncated", False),
        )

    async def read_file_range(
        self,
        path: str,
        start_line: int,
        end_line: int,
    ) -> FileContent:
        """
        Read specific lines from a file.

        Args:
            path: Path to the file
            start_line: Starting line number (1-based)
            end_line: Ending line number (inclusive)

        Returns:
            FileContent with the specified lines
        """
        resolved_path = self._resolve_path(path)

        logger.debug(
            "Reading file range",
            path=resolved_path,
            start=start_line,
            end=end_line,
        )

        response = await self._post(
            "/read",
            data={
                "path": resolved_path,
                "start_line": start_line,
                "end_line": end_line,
            },
        )

        return FileContent(
            path=resolved_path,
            content=response.get("content", ""),
            start_line=start_line,
            end_line=end_line,
            total_lines=response.get("total_lines", 0),
            truncated=response.get("truncated", False),
        )

    async def list_directory(self, path: str = "") -> list[FileInfo]:
        """
        List contents of a directory.

        Args:
            path: Path to the directory (relative to codebase root)

        Returns:
            List of FileInfo objects
        """
        resolved_path = self._resolve_path(path) if path else self.codebase_root

        logger.debug("Listing directory", path=resolved_path)

        response = await self._post(
            "/list",
            data={"path": resolved_path},
        )

        entries = response.get("entries", [])
        return [FileInfo.from_dict(entry) for entry in entries]

    async def find_files(
        self,
        pattern: str,
        root: str = "",
        max_results: int = 100,
    ) -> list[str]:
        """
        Find files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., "**/*.java", "*Service.py")
            root: Starting directory (relative to codebase root)
            max_results: Maximum number of results

        Returns:
            List of matching file paths
        """
        resolved_root = self._resolve_path(root) if root else self.codebase_root

        logger.debug("Finding files", pattern=pattern, root=resolved_root)

        response = await self._post(
            "/find",
            data={
                "pattern": pattern,
                "root": resolved_root,
                "max_results": max_results,
            },
        )

        return response.get("files", [])

    async def get_file_metadata(self, path: str) -> FileMetadata:
        """
        Get metadata about a file.

        Args:
            path: Path to the file

        Returns:
            FileMetadata with file information
        """
        resolved_path = self._resolve_path(path)

        response = await self._post(
            "/metadata",
            data={"path": resolved_path},
        )

        return FileMetadata.from_dict(response)

    async def file_exists(self, path: str) -> bool:
        """
        Check if a file exists.

        Args:
            path: Path to check

        Returns:
            True if file exists, False otherwise
        """
        try:
            resolved_path = self._resolve_path(path)
            response = await self._post(
                "/exists",
                data={"path": resolved_path},
            )
            return response.get("exists", False)
        except MCPError:
            return False

    async def search_in_file(
        self,
        path: str,
        pattern: str,
        case_sensitive: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Search for a pattern within a file.

        Args:
            path: Path to the file
            pattern: Search pattern (regex supported)
            case_sensitive: Whether search is case-sensitive

        Returns:
            List of matches with line numbers and content
        """
        resolved_path = self._resolve_path(path)

        response = await self._post(
            "/search",
            data={
                "path": resolved_path,
                "pattern": pattern,
                "case_sensitive": case_sensitive,
            },
        )

        return response.get("matches", [])

    async def search_in_directory(
        self,
        pattern: str,
        root: str = "",
        file_pattern: str = "*",
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Search for a pattern across files in a directory.

        Args:
            pattern: Search pattern (regex supported)
            root: Starting directory
            file_pattern: Glob pattern for files to search
            max_results: Maximum number of results

        Returns:
            List of matches with file paths, line numbers, and content
        """
        resolved_root = self._resolve_path(root) if root else self.codebase_root

        response = await self._post(
            "/search_directory",
            data={
                "pattern": pattern,
                "root": resolved_root,
                "file_pattern": file_pattern,
                "max_results": max_results,
            },
        )

        return response.get("matches", [])

    async def verify_content_exists(
        self,
        path: str,
        content: str,
        case_sensitive: bool = False,
    ) -> bool:
        """
        Verify if specific content exists in a file.

        Args:
            path: Path to the file
            content: Content to search for
            case_sensitive: Whether search is case-sensitive

        Returns:
            True if content exists, False otherwise
        """
        try:
            file_content = await self.read_file(path)
            source = file_content.content

            if not case_sensitive:
                source = source.lower()
                content = content.lower()

            return content in source
        except MCPError:
            return False

    async def get_class_from_file(
        self,
        path: str,
        class_name: str,
    ) -> Optional[str]:
        """
        Extract a class definition from a file.

        Args:
            path: Path to the file
            class_name: Name of the class to extract

        Returns:
            Class definition as string, or None if not found
        """
        try:
            file_content = await self.read_file(path)
            source = file_content.content

            # Simple extraction - look for class definition
            # This is a simplified implementation; real extraction would need
            # language-aware parsing
            import re

            # Pattern for common class definitions
            patterns = [
                rf"(class\s+{class_name}\s*[^{{]*\{{[^}}]*\}})",  # Java/TypeScript
                rf"(class\s+{class_name}[^\n]*:[\s\S]*?)(?=\nclass\s|\n[^\s]|\Z)",  # Python
            ]

            for pattern in patterns:
                match = re.search(pattern, source, re.MULTILINE)
                if match:
                    return match.group(1)

            return None
        except MCPError:
            return None

    async def get_method_from_file(
        self,
        path: str,
        method_name: str,
        class_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Extract a method definition from a file.

        Args:
            path: Path to the file
            method_name: Name of the method
            class_name: Optional class name to scope the search

        Returns:
            Method definition as string, or None if not found
        """
        try:
            file_content = await self.read_file(path)
            source = file_content.content

            import re

            # Patterns for method definitions
            patterns = [
                rf"((?:public|private|protected)?\s*(?:static\s+)?(?:\w+\s+)?{method_name}\s*\([^)]*\)\s*\{{[^}}]*\}})",  # Java
                rf"(def\s+{method_name}\s*\([^)]*\)[^:]*:[\s\S]*?)(?=\n\s*def\s|\n[^\s]|\Z)",  # Python
                rf"((?:async\s+)?function\s+{method_name}\s*\([^)]*\)\s*\{{[^}}]*\}})",  # JavaScript
            ]

            for pattern in patterns:
                match = re.search(pattern, source, re.MULTILINE)
                if match:
                    return match.group(1)

            return None
        except MCPError:
            return None
