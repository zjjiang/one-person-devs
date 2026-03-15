"""GitHub SCM Provider."""

from __future__ import annotations

import asyncio
import logging
import os

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

        import asyncio
        import json
        import urllib.error
        import urllib.request

        headers = {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "OPD/1.0",
        }
        repo_url = self.config.get("repo_url")

        try:
            if repo_url:
                # Single call: GET /repos/{owner}/{repo} — returns permissions + validates token
                repo_name = self._repo_name(repo_url)
                api_url = f"https://api.github.com/repos/{repo_name}"
                req = urllib.request.Request(api_url, headers=headers)
                resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=8)
                data = json.loads(resp.read())
                perms = data.get("permissions", {})
                perm_str = "/".join(
                    p for p in ("pull", "push", "admin") if perms.get(p)
                )
                owner = data.get("owner", {}).get("login", "")
                return HealthStatus(
                    healthy=True,
                    message=f"仓库 {repo_name} 权限: {perm_str}（owner: {owner}）",
                )
            else:
                # No repo_url, just verify token
                req = urllib.request.Request("https://api.github.com/user", headers=headers)
                resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=8)
                data = json.loads(resp.read())
                return HealthStatus(healthy=True, message=f"已连接 {data.get('login')}")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return HealthStatus(healthy=False, message=f"Token 认证失败 (HTTP {e.code})")
            if e.code == 404:
                return HealthStatus(healthy=False, message="仓库不存在或无访问权限")
            return HealthStatus(healthy=False, message=f"GitHub API 错误 (HTTP {e.code})")
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            return HealthStatus(healthy=False, message=f"无法连接 GitHub: {reason}")

    async def cleanup(self):
        if self._github:
            self._github.close()

    def _repo_name(self, repo_url: str) -> str:
        """Extract 'owner/repo' from URL."""
        url = repo_url.rstrip("/").removesuffix(".git")
        parts = url.split("/")
        return f"{parts[-2]}/{parts[-1]}"

    def _ensure_github(self):
        """Raise if PyGithub client is not initialized."""
        if self._github is None:
            raise RuntimeError("GitHub client not initialized — check PyGithub installation and token")

    async def clone_repo(self, repo_url: str, target_dir: str) -> None:
        auth_url = repo_url.replace("https://", f"https://x-access-token:{self._token}@")
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", auth_url, target_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git clone failed: {stderr.decode()}")

    async def create_branch(self, repo_dir: str, branch_name: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "git", "checkout", "-b", branch_name,
            cwd=repo_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git checkout -b failed: {stderr.decode()}")

    async def commit_and_push(self, repo_dir: str, branch_name: str, message: str) -> None:
        cmds = [
            ["git", "add", "-A"],
            ["git", "commit", "-m", message, "--allow-empty"],
            ["git", "push", "origin", branch_name],
        ]
        for cmd in cmds:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=repo_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"git command {' '.join(cmd)} failed: {stderr.decode()}")

    async def create_pull_request(self, repo_url: str, branch: str,
                                  title: str, body: str) -> dict:
        self._ensure_github()

        def _create():
            repo = self._github.get_repo(self._repo_name(repo_url))
            return repo.create_pull(title=title, body=body, head=branch, base="main")

        pr = await asyncio.to_thread(_create)
        return {"pr_number": pr.number, "pr_url": pr.html_url}

    async def get_review_comments(self, repo_url: str, pr_number: int) -> list[dict]:
        self._ensure_github()

        def _fetch():
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

        return await asyncio.to_thread(_fetch)

    async def merge_pull_request(self, repo_url: str, pr_number: int) -> None:
        self._ensure_github()

        def _merge():
            from github import GithubException
            repo = self._github.get_repo(self._repo_name(repo_url))
            pr = repo.get_pull(pr_number)
            if not pr.mergeable:
                raise RuntimeError(
                    f"PR #{pr_number} 存在合并冲突，请先解决冲突后再合并"
                )
            try:
                pr.merge()
            except GithubException as e:
                status = e.status
                msg = e.data.get("message", str(e)) if isinstance(e.data, dict) else str(e)
                if status == 405:
                    raise RuntimeError(f"PR #{pr_number} 无法合并: {msg}") from e
                if status == 403:
                    raise RuntimeError(f"Token 权限不足，无法合并 PR #{pr_number}") from e
                if status == 409:
                    raise RuntimeError(
                        f"PR #{pr_number} 存在合并冲突: {msg}"
                    ) from e
                raise RuntimeError(f"合并 PR #{pr_number} 失败 (HTTP {status}): {msg}") from e

        await asyncio.to_thread(_merge)

    async def close_pull_request(self, repo_url: str, pr_number: int) -> None:
        self._ensure_github()

        def _close():
            repo = self._github.get_repo(self._repo_name(repo_url))
            pr = repo.get_pull(pr_number)
            pr.edit(state="closed")

        await asyncio.to_thread(_close)

    async def get_repo_structure(self, repo_dir: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "find", ".", "-type", "f", "-not", "-path", "./.git/*",
            "-not", "-path", "./.venv/*", "-not", "-path", "./node_modules/*",
            cwd=repo_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode()[:5000]
