"""GitHub SCM Provider."""

from __future__ import annotations

import logging
import os
import subprocess

from opd.capabilities.base import HealthStatus
from opd.providers.scm.base import SCMProvider

logger = logging.getLogger(__name__)


class GitHubProvider(SCMProvider):
    """SCM provider using GitHub (PyGithub + GitPython)."""

    CONFIG_SCHEMA = [
        {"name": "token", "label": "GitHub Token", "type": "password", "required": True},
    ]

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._token = self.config.get("token") or os.environ.get("GITHUB_TOKEN", "")
        self._github = None

    async def initialize(self):
        try:
            from github import Github
            self._github = Github(self._token)
        except ImportError:
            logger.warning("PyGithub not installed")

    async def health_check(self) -> HealthStatus:
        if not self._token:
            return HealthStatus(healthy=False, message="GITHUB_TOKEN not set")
        if not self._github:
            return HealthStatus(healthy=False, message="PyGithub not initialized")
        try:
            user = self._github.get_user()
            _ = user.login
            return HealthStatus(healthy=True, message=f"GitHub connected as {user.login}")
        except Exception as e:
            return HealthStatus(healthy=False, message=f"GitHub API error: {e}")

    async def cleanup(self):
        if self._github:
            self._github.close()

    def _repo_name(self, repo_url: str) -> str:
        """Extract 'owner/repo' from URL."""
        url = repo_url.rstrip("/").removesuffix(".git")
        parts = url.split("/")
        return f"{parts[-2]}/{parts[-1]}"

    async def clone_repo(self, repo_url: str, target_dir: str) -> None:
        auth_url = repo_url.replace("https://", f"https://x-access-token:{self._token}@")
        subprocess.run(["git", "clone", auth_url, target_dir], check=True, capture_output=True)

    async def create_branch(self, repo_dir: str, branch_name: str) -> None:
        subprocess.run(
            ["git", "checkout", "-b", branch_name], cwd=repo_dir, check=True, capture_output=True
        )

    async def commit_and_push(self, repo_dir: str, branch_name: str, message: str) -> None:
        cmds = [
            ["git", "add", "-A"],
            ["git", "commit", "-m", message, "--allow-empty"],
            ["git", "push", "origin", branch_name],
        ]
        for cmd in cmds:
            subprocess.run(cmd, cwd=repo_dir, check=True, capture_output=True)

    async def create_pull_request(self, repo_url: str, branch: str,
                                  title: str, body: str) -> dict:
        repo = self._github.get_repo(self._repo_name(repo_url))
        pr = repo.create_pull(title=title, body=body, head=branch, base="main")
        return {"pr_number": pr.number, "pr_url": pr.html_url}

    async def get_review_comments(self, repo_url: str, pr_number: int) -> list[dict]:
        repo = self._github.get_repo(self._repo_name(repo_url))
        pr = repo.get_pull(pr_number)
        comments = []
        for review in pr.get_reviews():
            if review.body:
                comments.append({"user": review.user.login, "body": review.body})
        for comment in pr.get_review_comments():
            comments.append({
                "user": comment.user.login,
                "body": comment.body,
                "path": comment.path,
            })
        return comments

    async def merge_pull_request(self, repo_url: str, pr_number: int) -> None:
        repo = self._github.get_repo(self._repo_name(repo_url))
        pr = repo.get_pull(pr_number)
        pr.merge()

    async def close_pull_request(self, repo_url: str, pr_number: int) -> None:
        repo = self._github.get_repo(self._repo_name(repo_url))
        pr = repo.get_pull(pr_number)
        pr.edit(state="closed")

    async def get_repo_structure(self, repo_dir: str) -> str:
        result = subprocess.run(
            ["find", ".", "-type", "f", "-not", "-path", "./.git/*",
             "-not", "-path", "./.venv/*", "-not", "-path", "./node_modules/*"],
            cwd=repo_dir, capture_output=True, text=True,
        )
        return result.stdout[:5000]
