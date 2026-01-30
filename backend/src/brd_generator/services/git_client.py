"""Git operations client for repository management."""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GitStatus:
    """Git repository status."""

    branch: str
    commit_sha: str
    is_dirty: bool = False
    ahead: int = 0
    behind: int = 0


class GitClient:
    """Git operations client using subprocess."""

    def __init__(self, timeout: int = 300):
        """Initialize Git client.

        Args:
            timeout: Default timeout for git operations in seconds.
        """
        self.timeout = timeout

    async def _run_git(
        self,
        *args: str,
        cwd: Optional[Path] = None,
        env: Optional[dict] = None,
        timeout: Optional[int] = None,
    ) -> tuple[int, str, str]:
        """Run a git command asynchronously.

        Args:
            *args: Git command arguments.
            cwd: Working directory for the command.
            env: Environment variables.
            timeout: Command timeout in seconds.

        Returns:
            Tuple of (return_code, stdout, stderr).
        """
        cmd = ["git", *args]
        cmd_str = " ".join(cmd)

        # Merge environment
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        # Disable interactive prompts
        run_env["GIT_TERMINAL_PROMPT"] = "0"

        logger.debug(f"Running: {cmd_str}" + (f" in {cwd}" if cwd else ""))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                env=run_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout or self.timeout,
            )

            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            if process.returncode != 0:
                logger.warning(
                    f"Git command failed: {cmd_str}\n"
                    f"Return code: {process.returncode}\n"
                    f"Stderr: {stderr_str}"
                )

            return process.returncode, stdout_str, stderr_str

        except asyncio.TimeoutError:
            logger.error(f"Git command timed out: {cmd_str}")
            raise TimeoutError(f"Git command timed out after {timeout or self.timeout}s: {cmd_str}")

    async def clone(
        self,
        url: str,
        destination: Path,
        branch: Optional[str] = None,
        depth: Optional[int] = None,
        single_branch: bool = True,
    ) -> Path:
        """Clone a repository.

        Args:
            url: Repository URL (may include embedded token).
            destination: Local destination path.
            branch: Specific branch to clone.
            depth: Shallow clone depth.
            single_branch: Only clone the single branch.

        Returns:
            Path to the cloned repository.

        Raises:
            RuntimeError: If clone fails.
        """
        # Ensure parent directory exists
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Build clone command
        args = ["clone"]

        if branch:
            args.extend(["--branch", branch])

        if depth:
            args.extend(["--depth", str(depth)])

        if single_branch:
            args.append("--single-branch")

        # Add progress flag for logging
        args.append("--progress")

        args.extend([url, str(destination)])

        # Mask token in logs
        safe_url = self._mask_token(url)
        logger.info(f"Cloning repository: {safe_url} -> {destination}")

        returncode, stdout, stderr = await self._run_git(*args)

        if returncode != 0:
            # Clean up failed clone
            if destination.exists():
                shutil.rmtree(destination)
            raise RuntimeError(f"Failed to clone repository: {stderr}")

        logger.info(f"Successfully cloned repository to {destination}")
        return destination

    async def pull(
        self,
        repo_path: Path,
        force: bool = False,
        remote: str = "origin",
        branch: Optional[str] = None,
    ) -> tuple[bool, int]:
        """Pull changes from remote.

        Args:
            repo_path: Path to the repository.
            force: Force pull (reset local changes).
            remote: Remote name.
            branch: Branch to pull.

        Returns:
            Tuple of (changes_detected, commits_pulled).
        """
        logger.info(f"Pulling changes for {repo_path}")

        # Get current commit before pull
        _, old_commit, _ = await self._run_git(
            "rev-parse", "HEAD",
            cwd=repo_path
        )

        if force:
            # Fetch first
            await self._run_git("fetch", remote, cwd=repo_path)

            # Get the branch to reset to
            target_branch = branch or await self._get_current_branch(repo_path)

            # Hard reset to remote
            returncode, _, stderr = await self._run_git(
                "reset", "--hard", f"{remote}/{target_branch}",
                cwd=repo_path
            )
            if returncode != 0:
                raise RuntimeError(f"Failed to reset repository: {stderr}")
        else:
            # Normal pull
            args = ["pull", remote]
            if branch:
                args.append(branch)

            returncode, stdout, stderr = await self._run_git(*args, cwd=repo_path)

            if returncode != 0:
                raise RuntimeError(f"Failed to pull: {stderr}")

        # Get new commit after pull
        _, new_commit, _ = await self._run_git(
            "rev-parse", "HEAD",
            cwd=repo_path
        )

        # Count commits pulled
        if old_commit != new_commit:
            _, count_output, _ = await self._run_git(
                "rev-list", "--count", f"{old_commit}..{new_commit}",
                cwd=repo_path
            )
            commits_pulled = int(count_output) if count_output.isdigit() else 0
            logger.info(f"Pulled {commits_pulled} commits")
            return True, commits_pulled
        else:
            logger.info("Already up to date")
            return False, 0

    async def get_status(self, repo_path: Path) -> GitStatus:
        """Get repository status.

        Args:
            repo_path: Path to the repository.

        Returns:
            GitStatus with current branch, commit, etc.
        """
        # Get current branch
        branch = await self._get_current_branch(repo_path)

        # Get current commit SHA
        _, commit_sha, _ = await self._run_git(
            "rev-parse", "HEAD",
            cwd=repo_path
        )

        # Check for uncommitted changes
        returncode, _, _ = await self._run_git(
            "diff", "--quiet",
            cwd=repo_path
        )
        is_dirty = returncode != 0

        # Get ahead/behind counts (if tracking branch exists)
        ahead, behind = 0, 0
        returncode, output, _ = await self._run_git(
            "rev-list", "--left-right", "--count", f"HEAD...@{{upstream}}",
            cwd=repo_path
        )
        if returncode == 0 and output:
            parts = output.split()
            if len(parts) == 2:
                ahead = int(parts[0])
                behind = int(parts[1])

        return GitStatus(
            branch=branch,
            commit_sha=commit_sha[:12] if commit_sha else "",
            is_dirty=is_dirty,
            ahead=ahead,
            behind=behind,
        )

    async def get_default_branch(self, repo_path: Path) -> str:
        """Get the default branch name from remote.

        Args:
            repo_path: Path to the repository.

        Returns:
            Default branch name (e.g., 'main' or 'master').
        """
        # Try to get from remote HEAD
        returncode, output, _ = await self._run_git(
            "symbolic-ref", "refs/remotes/origin/HEAD",
            cwd=repo_path
        )

        if returncode == 0 and output:
            # refs/remotes/origin/main -> main
            return output.split("/")[-1]

        # Fallback: check for common branches
        for branch in ["main", "master"]:
            returncode, _, _ = await self._run_git(
                "rev-parse", "--verify", f"refs/remotes/origin/{branch}",
                cwd=repo_path
            )
            if returncode == 0:
                return branch

        # Last resort: return current branch
        return await self._get_current_branch(repo_path)

    async def checkout(
        self,
        repo_path: Path,
        branch: str,
        create: bool = False,
    ) -> None:
        """Checkout a branch.

        Args:
            repo_path: Path to the repository.
            branch: Branch name to checkout.
            create: Create the branch if it doesn't exist.
        """
        args = ["checkout"]
        if create:
            args.append("-b")
        args.append(branch)

        returncode, _, stderr = await self._run_git(*args, cwd=repo_path)

        if returncode != 0:
            raise RuntimeError(f"Failed to checkout branch {branch}: {stderr}")

        logger.info(f"Checked out branch: {branch}")

    async def _get_current_branch(self, repo_path: Path) -> str:
        """Get the current branch name."""
        returncode, output, _ = await self._run_git(
            "rev-parse", "--abbrev-ref", "HEAD",
            cwd=repo_path
        )

        if returncode == 0 and output:
            return output

        # Fallback for detached HEAD
        return "HEAD"

    def _mask_token(self, url: str) -> str:
        """Mask any token in the URL for safe logging."""
        if "@" in url and "://" in url:
            # https://token@github.com -> https://***@github.com
            protocol, rest = url.split("://", 1)
            if "@" in rest:
                token_part, host_part = rest.split("@", 1)
                # Handle oauth2:token format
                if ":" in token_part:
                    prefix, _ = token_part.split(":", 1)
                    return f"{protocol}://{prefix}:***@{host_part}"
                return f"{protocol}://***@{host_part}"
        return url

    async def cleanup(self, repo_path: Path) -> bool:
        """Remove a cloned repository.

        Args:
            repo_path: Path to the repository.

        Returns:
            True if cleanup was successful.
        """
        if repo_path.exists():
            try:
                shutil.rmtree(repo_path)
                logger.info(f"Cleaned up repository at {repo_path}")
                return True
            except Exception as e:
                logger.error(f"Failed to cleanup repository: {e}")
                return False
        return True
