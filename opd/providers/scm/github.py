"""GitHub SCM provider using PyGithub and GitPython."""

from __future__ import annotations

import asyncio
import logging
import os
from functools import partial
from typing import Any

from opd.providers.scm.base import SCMProvider

logger = logging.getLogger(__name__)

try:
    import git as gitpython  # GitPython

    _HAS_GITPYTHON = True
except ImportError:  # pragma: no cover
    _HAS_GITPYTHON = False

try:
    from github import Github
    from github import GithubException

    _HAS_PYGITHUB = True
except ImportError:  # pragma: no cover
    _HAS_PYGITHUB = False


def _require_gitpython() -> None:
    if not _HAS_GITPYTHON:
        raise RuntimeError(
            "GitPython is required for GitHubSCMProvider. "
            "Install it with: pip install gitpython"
        )


def _require_pygithub() -> None:
    if not _HAS_PYGITHUB:
        raise RuntimeError(
            "PyGithub is required for GitHubSCMProvider. "
            "Install it with: pip install pygithub"
        )


class GitHubSCMProvider(SCMProvider):
    """GitHub implementation of :class:`SCMProvider`.

    Config keys:

    - ``token`` -- GitHub personal access token (required for API calls).
      Can also be set via GITHUB_TOKEN environment variable.
      Required scopes: repo, workflow (optional for GitHub Actions).
    - ``base_url`` -- GitHub API base URL (optional, for GitHub Enterprise).
    - ``webhook_secret`` -- Secret for verifying GitHub webhook signatures (optional).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        # Expose config for webhook signature verification
        # Support webhook_secret from config or environment variable
        webhook_secret = config.get("webhook_secret", "") or os.environ.get("GITHUB_WEBHOOK_SECRET", "")
        self.config = {**config, "webhook_secret": webhook_secret}
        self._token: str = config.get("token", "") or os.environ.get("GITHUB_TOKEN", "")
        self._base_url: str | None = config.get("base_url")
        self._gh: Any = None  # lazy Github client

    async def initialize(self) -> None:
        _require_gitpython()
        _require_pygithub()

        # Validate token is present
        if not self._token:
            raise ValueError(
                "GitHub token is required. Set GITHUB_TOKEN environment variable "
                "or provide 'token' in provider config. "
                "Token needs 'repo' scope at minimum."
            )

        kwargs: dict[str, Any] = {}
        if self._token:
            kwargs["login_or_token"] = self._token
        if self._base_url:
            kwargs["base_url"] = self._base_url

        self._gh = Github(**kwargs)

        # Validate token by attempting to get authenticated user
        try:
            user = self._gh.get_user()
            user.login  # Force API call
            logger.info("GitHub authentication successful for user: %s", user.login)
        except GithubException as e:
            raise ValueError(
                f"GitHub token validation failed: {e.data.get('message', str(e))}. "
                "Please check your token and ensure it has 'repo' scope."
            ) from e

    async def cleanup(self) -> None:
        if self._gh is not None:
            self._gh.close()
            self._gh = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_sync(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a blocking function in the default executor."""
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(None, partial(func, *args, **kwargs))

    def _authed_url(self, url: str) -> str:
        """Inject token into an HTTPS git URL for authentication."""
        if not self._token:
            return url
        # https://github.com/owner/repo.git -> https://{token}@github.com/owner/repo.git
        for prefix in ("https://", "http://"):
            if url.startswith(prefix):
                return f"{prefix}{self._token}@{url[len(prefix):]}"
        # SSH URLs or other formats — return as-is
        return url

    # ------------------------------------------------------------------
    # Local git operations
    # ------------------------------------------------------------------

    async def clone_repo(self, repo_url: str, target_dir: str) -> None:
        _require_gitpython()
        logger.info("Cloning %s -> %s", repo_url, target_dir)
        authed = self._authed_url(repo_url)
        await self._run_sync(gitpython.Repo.clone_from, authed, target_dir)

    async def create_branch(self, repo_dir: str, branch_name: str) -> None:
        _require_gitpython()

        def _create(rd: str, bn: str) -> None:
            repo = gitpython.Repo(rd)
            repo.git.checkout("-b", bn)

        await self._run_sync(_create, repo_dir, branch_name)
        logger.info("Created branch %s in %s", branch_name, repo_dir)

    async def commit_changes(self, repo_dir: str, message: str) -> None:
        _require_gitpython()

        def _commit(rd: str, msg: str) -> None:
            repo = gitpython.Repo(rd)
            repo.git.add("-A")
            repo.index.commit(msg)

        await self._run_sync(_commit, repo_dir, message)
        logger.info("Committed changes in %s", repo_dir)

    async def push_branch(self, repo_dir: str, branch_name: str) -> None:
        _require_gitpython()
        token = self._token

        def _push(rd: str, bn: str) -> None:
            repo = gitpython.Repo(rd)
            # Ensure remote URL has token for auth
            if token:
                origin = repo.remote("origin")
                current_url = origin.url
                for prefix in ("https://", "http://"):
                    if current_url.startswith(prefix):
                        authed = f"{prefix}{token}@{current_url[len(prefix):]}"
                        origin.set_url(authed)
                        break
            repo.git.push("origin", bn)

        await self._run_sync(_push, repo_dir, branch_name)
        logger.info("Pushed branch %s from %s", branch_name, repo_dir)

    # ------------------------------------------------------------------
    # Remote platform operations
    # ------------------------------------------------------------------

    async def create_pull_request(
        self, repo: str, branch: str, title: str, body: str
    ) -> dict[str, Any]:
        _require_pygithub()

        def _create_pr() -> dict[str, Any]:
            gh_repo = self._gh.get_repo(repo)
            default_branch = gh_repo.default_branch
            pr = gh_repo.create_pull(
                title=title,
                body=body,
                head=branch,
                base=default_branch,
            )
            return {
                "id": pr.number,
                "url": pr.html_url,
                "state": pr.state,
                "title": pr.title,
            }

        result = await self._run_sync(_create_pr)
        logger.info("Created PR #%s in %s", result["id"], repo)
        return result

    async def get_review_comments(self, repo: str, pr_id: int) -> list[dict[str, Any]]:
        _require_pygithub()

        def _get_comments() -> list[dict[str, Any]]:
            gh_repo = self._gh.get_repo(repo)
            pr = gh_repo.get_pull(pr_id)
            comments: list[dict[str, Any]] = []
            for review in pr.get_reviews():
                comments.append({
                    "id": review.id,
                    "user": review.user.login if review.user else "unknown",
                    "body": review.body or "",
                    "state": review.state,
                })
            for comment in pr.get_review_comments():
                comments.append({
                    "id": comment.id,
                    "user": comment.user.login if comment.user else "unknown",
                    "body": comment.body or "",
                    "path": comment.path,
                    "line": comment.line,
                })
            return comments

        return await self._run_sync(_get_comments)

    async def update_pull_request(self, repo: str, pr_id: int, **kwargs: Any) -> None:
        _require_pygithub()

        def _update() -> None:
            gh_repo = self._gh.get_repo(repo)
            pr = gh_repo.get_pull(pr_id)
            pr.edit(**kwargs)

        await self._run_sync(_update)
        logger.info("Updated PR #%s in %s", pr_id, repo)

    async def merge_pull_request(self, repo: str, pr_id: int) -> None:
        _require_pygithub()

        def _merge() -> None:
            gh_repo = self._gh.get_repo(repo)
            pr = gh_repo.get_pull(pr_id)
            pr.merge()

        await self._run_sync(_merge)
        logger.info("Merged PR #%s in %s", pr_id, repo)

    async def get_pr_status(self, repo: str, pr_id: int) -> str:
        _require_pygithub()

        def _status() -> str:
            gh_repo = self._gh.get_repo(repo)
            pr = gh_repo.get_pull(pr_id)
            if pr.merged:
                return "merged"
            return pr.state  # "open" or "closed"

        return await self._run_sync(_status)
