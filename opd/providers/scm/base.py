"""Abstract base class for source-control management providers."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from opd.providers.base import Provider


class SCMProvider(Provider):
    """Interface for interacting with source-control systems.

    Covers both local git operations (clone, branch, commit, push) and
    remote platform operations (pull requests, reviews).
    """

    # ------------------------------------------------------------------
    # Local git operations
    # ------------------------------------------------------------------

    @abstractmethod
    async def clone_repo(self, repo_url: str, target_dir: str) -> None:
        """Clone *repo_url* into *target_dir*."""

    @abstractmethod
    async def create_branch(self, repo_dir: str, branch_name: str) -> None:
        """Create and check out a new branch in *repo_dir*."""

    @abstractmethod
    async def commit_changes(self, repo_dir: str, message: str) -> None:
        """Stage all changes and create a commit in *repo_dir*."""

    @abstractmethod
    async def push_branch(self, repo_dir: str, branch_name: str) -> None:
        """Push *branch_name* to the remote origin."""

    # ------------------------------------------------------------------
    # Remote platform operations
    # ------------------------------------------------------------------

    @abstractmethod
    async def create_pull_request(
        self, repo: str, branch: str, title: str, body: str
    ) -> dict[str, Any]:
        """Create a pull request and return its metadata.

        *repo* is in ``owner/name`` format.  The returned dict must
        contain at least ``id`` and ``url`` keys.
        """

    @abstractmethod
    async def get_review_comments(self, repo: str, pr_id: int) -> list[dict[str, Any]]:
        """Return review comments for a pull request."""

    @abstractmethod
    async def update_pull_request(self, repo: str, pr_id: int, **kwargs: Any) -> None:
        """Update pull request fields (title, body, labels, etc.)."""

    @abstractmethod
    async def merge_pull_request(self, repo: str, pr_id: int) -> None:
        """Merge a pull request."""

    @abstractmethod
    async def get_pr_status(self, repo: str, pr_id: int) -> str:
        """Return the current status/state of a pull request.

        Typical values: ``open``, ``closed``, ``merged``.
        """
