"""SCM Provider base class."""

from __future__ import annotations

from abc import abstractmethod

from opd.capabilities.base import Provider


class SCMProvider(Provider):
    """Abstract base for source code management."""

    @abstractmethod
    async def clone_repo(self, repo_url: str, target_dir: str) -> None:
        """Clone a repository to target_dir."""

    @abstractmethod
    async def create_branch(self, repo_dir: str, branch_name: str) -> None:
        """Create and checkout a new branch."""

    @abstractmethod
    async def commit_and_push(self, repo_dir: str, branch_name: str, message: str) -> None:
        """Stage all changes, commit, and push."""

    @abstractmethod
    async def create_pull_request(self, repo_url: str, branch: str,
                                  title: str, body: str) -> dict:
        """Create a PR. Returns dict with pr_number, pr_url."""

    @abstractmethod
    async def get_review_comments(self, repo_url: str, pr_number: int) -> list[dict]:
        """Get review comments for a PR."""

    @abstractmethod
    async def merge_pull_request(self, repo_url: str, pr_number: int) -> None:
        """Merge a PR."""

    @abstractmethod
    async def close_pull_request(self, repo_url: str, pr_number: int) -> None:
        """Close a PR without merging."""

    @abstractmethod
    async def get_repo_structure(self, repo_dir: str) -> str:
        """Get a summary of the repo file structure."""
