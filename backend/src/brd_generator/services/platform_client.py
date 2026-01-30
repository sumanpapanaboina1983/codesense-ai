"""GitHub and GitLab API clients for repository metadata."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

from ..models.repository import RepositoryPlatform
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RepositoryInfo:
    """Repository metadata from platform API."""

    name: str  # owner/repo format
    full_name: str
    description: Optional[str]
    default_branch: str
    is_private: bool
    clone_url: str
    html_url: str
    language: Optional[str] = None
    size_kb: int = 0
    stars: int = 0


@dataclass
class BranchInfo:
    """Branch information."""

    name: str
    commit_sha: str
    is_protected: bool = False


class PlatformClient(ABC):
    """Abstract base class for platform API clients."""

    def __init__(self, token: Optional[str] = None, timeout: int = 30):
        """Initialize platform client.

        Args:
            token: Personal access token for authentication.
            timeout: HTTP request timeout in seconds.
        """
        self.token = token
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @abstractmethod
    async def get_repository(self, owner: str, repo: str) -> RepositoryInfo:
        """Get repository metadata."""
        pass

    @abstractmethod
    async def list_branches(self, owner: str, repo: str) -> list[BranchInfo]:
        """List repository branches."""
        pass

    @abstractmethod
    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: Optional[str] = None,
    ) -> str:
        """Get file content from repository."""
        pass

    @abstractmethod
    async def validate_token(self) -> bool:
        """Validate the access token."""
        pass

    @classmethod
    def parse_repo_url(cls, url: str) -> tuple[str, str, RepositoryPlatform]:
        """Parse repository URL into owner, repo, and platform.

        Args:
            url: Repository URL.

        Returns:
            Tuple of (owner, repo, platform).

        Raises:
            ValueError: If URL is invalid or platform is unsupported.
        """
        # Clean URL
        url = url.strip().rstrip("/")

        # Remove .git suffix
        if url.endswith(".git"):
            url = url[:-4]

        # Handle SSH URLs
        if url.startswith("git@"):
            # git@github.com:owner/repo -> github.com/owner/repo
            url = url.replace(":", "/").replace("git@", "https://")

        parsed = urlparse(url)
        host = parsed.netloc.lower()

        # Determine platform
        if "github.com" in host:
            platform = RepositoryPlatform.GITHUB
        elif "gitlab.com" in host or "gitlab." in host:
            platform = RepositoryPlatform.GITLAB
        else:
            raise ValueError(f"Unsupported platform: {host}")

        # Extract owner and repo from path
        path_parts = [p for p in parsed.path.split("/") if p]

        if len(path_parts) < 2:
            raise ValueError(f"Invalid repository URL: {url}")

        owner = path_parts[0]
        repo = path_parts[1]

        return owner, repo, platform


class GitHubClient(PlatformClient):
    """GitHub API client using REST API v3."""

    API_BASE = "https://api.github.com"

    def __init__(self, token: Optional[str] = None, timeout: int = 30):
        super().__init__(token, timeout)

    def _headers(self) -> dict[str, str]:
        """Get request headers."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def get_repository(self, owner: str, repo: str) -> RepositoryInfo:
        """Get repository metadata from GitHub."""
        client = await self._get_client()
        url = f"{self.API_BASE}/repos/{owner}/{repo}"

        logger.debug(f"Fetching GitHub repository: {owner}/{repo}")

        response = await client.get(url, headers=self._headers())

        if response.status_code == 404:
            raise ValueError(f"Repository not found: {owner}/{repo}")
        elif response.status_code == 401:
            raise PermissionError("Invalid GitHub token")
        elif response.status_code == 403:
            raise PermissionError("Access denied to repository")

        response.raise_for_status()
        data = response.json()

        return RepositoryInfo(
            name=data["name"],
            full_name=data["full_name"],
            description=data.get("description"),
            default_branch=data["default_branch"],
            is_private=data["private"],
            clone_url=data["clone_url"],
            html_url=data["html_url"],
            language=data.get("language"),
            size_kb=data.get("size", 0),
            stars=data.get("stargazers_count", 0),
        )

    async def list_branches(self, owner: str, repo: str) -> list[BranchInfo]:
        """List repository branches."""
        client = await self._get_client()
        url = f"{self.API_BASE}/repos/{owner}/{repo}/branches"

        response = await client.get(url, headers=self._headers())
        response.raise_for_status()

        branches = []
        for branch_data in response.json():
            branches.append(BranchInfo(
                name=branch_data["name"],
                commit_sha=branch_data["commit"]["sha"],
                is_protected=branch_data.get("protected", False),
            ))

        return branches

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: Optional[str] = None,
    ) -> str:
        """Get file content from repository."""
        client = await self._get_client()
        url = f"{self.API_BASE}/repos/{owner}/{repo}/contents/{path}"

        params = {}
        if ref:
            params["ref"] = ref

        response = await client.get(url, headers=self._headers(), params=params)
        response.raise_for_status()

        data = response.json()

        if data.get("encoding") == "base64":
            import base64
            return base64.b64decode(data["content"]).decode("utf-8")

        return data.get("content", "")

    async def validate_token(self) -> bool:
        """Validate the GitHub token."""
        if not self.token:
            return False

        client = await self._get_client()
        url = f"{self.API_BASE}/user"

        try:
            response = await client.get(url, headers=self._headers())
            return response.status_code == 200
        except Exception:
            return False


class GitLabClient(PlatformClient):
    """GitLab API client using REST API v4."""

    def __init__(
        self,
        token: Optional[str] = None,
        api_url: str = "https://gitlab.com/api/v4",
        timeout: int = 30,
    ):
        super().__init__(token, timeout)
        self.api_url = api_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        """Get request headers."""
        headers = {"Accept": "application/json"}
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token
        return headers

    def _encode_project_path(self, owner: str, repo: str) -> str:
        """URL encode the project path."""
        from urllib.parse import quote
        return quote(f"{owner}/{repo}", safe="")

    async def get_repository(self, owner: str, repo: str) -> RepositoryInfo:
        """Get repository metadata from GitLab."""
        client = await self._get_client()
        project_path = self._encode_project_path(owner, repo)
        url = f"{self.api_url}/projects/{project_path}"

        logger.debug(f"Fetching GitLab repository: {owner}/{repo}")

        response = await client.get(url, headers=self._headers())

        if response.status_code == 404:
            raise ValueError(f"Repository not found: {owner}/{repo}")
        elif response.status_code == 401:
            raise PermissionError("Invalid GitLab token")
        elif response.status_code == 403:
            raise PermissionError("Access denied to repository")

        response.raise_for_status()
        data = response.json()

        return RepositoryInfo(
            name=data["path"],
            full_name=data["path_with_namespace"],
            description=data.get("description"),
            default_branch=data.get("default_branch", "main"),
            is_private=data.get("visibility", "private") == "private",
            clone_url=data["http_url_to_repo"],
            html_url=data["web_url"],
            language=None,  # GitLab doesn't include this in basic response
            size_kb=data.get("statistics", {}).get("repository_size", 0) // 1024,
            stars=data.get("star_count", 0),
        )

    async def list_branches(self, owner: str, repo: str) -> list[BranchInfo]:
        """List repository branches."""
        client = await self._get_client()
        project_path = self._encode_project_path(owner, repo)
        url = f"{self.api_url}/projects/{project_path}/repository/branches"

        response = await client.get(url, headers=self._headers())
        response.raise_for_status()

        branches = []
        for branch_data in response.json():
            branches.append(BranchInfo(
                name=branch_data["name"],
                commit_sha=branch_data["commit"]["id"],
                is_protected=branch_data.get("protected", False),
            ))

        return branches

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: Optional[str] = None,
    ) -> str:
        """Get file content from repository."""
        from urllib.parse import quote

        client = await self._get_client()
        project_path = self._encode_project_path(owner, repo)
        encoded_path = quote(path, safe="")
        url = f"{self.api_url}/projects/{project_path}/repository/files/{encoded_path}"

        params = {"ref": ref or "HEAD"}

        response = await client.get(url, headers=self._headers(), params=params)
        response.raise_for_status()

        data = response.json()

        if data.get("encoding") == "base64":
            import base64
            return base64.b64decode(data["content"]).decode("utf-8")

        return data.get("content", "")

    async def validate_token(self) -> bool:
        """Validate the GitLab token."""
        if not self.token:
            return False

        client = await self._get_client()
        url = f"{self.api_url}/user"

        try:
            response = await client.get(url, headers=self._headers())
            return response.status_code == 200
        except Exception:
            return False


def create_platform_client(
    platform: RepositoryPlatform,
    token: Optional[str] = None,
    api_url: Optional[str] = None,
) -> PlatformClient:
    """Factory function to create a platform client.

    Args:
        platform: The repository platform.
        token: Access token.
        api_url: API URL (for self-hosted GitLab).

    Returns:
        Platform client instance.
    """
    if platform == RepositoryPlatform.GITHUB:
        return GitHubClient(token=token)
    elif platform == RepositoryPlatform.GITLAB:
        return GitLabClient(
            token=token,
            api_url=api_url or "https://gitlab.com/api/v4",
        )
    else:
        raise ValueError(f"Unsupported platform: {platform}")
