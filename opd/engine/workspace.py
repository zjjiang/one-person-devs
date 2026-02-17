"""Workspace utilities: directory resolution, doc I/O, git clone."""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _sanitize(name: str) -> str:
    """Sanitize a string for use as a directory name."""
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r"[^\w\s-]", "", name.lower())
    return re.sub(r"[\s_]+", "-", name).strip("-")[:80]


def resolve_work_dir(project: Any) -> Path:
    """Resolve the project workspace directory.

    Returns {workspace_dir}/{sanitized_project_name}.
    """
    workspace_dir = getattr(project, "workspace_dir", "") or "./workspace"
    project_name = _sanitize(project.name) or "project"
    return Path(workspace_dir).resolve() / project_name


def story_slug(story: Any) -> str:
    """Generate a story directory slug: {id}-{sanitized_title}."""
    title = _sanitize(getattr(story, "title", ""))
    return f"{story.id}-{title}" if title else str(story.id)


def story_docs_dir(project: Any, story: Any) -> Path:
    """Return the absolute docs directory for a story."""
    return resolve_work_dir(project) / "docs" / story_slug(story)


def story_docs_relpath(story: Any, filename: str) -> str:
    """Return the relative path stored in DB: docs/{slug}/{filename}."""
    return f"docs/{story_slug(story)}/{filename}"


def _validate_filename(filename: str) -> None:
    """Validate filename to prevent path traversal."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ValueError(f"Invalid filename: {filename}")


def write_doc(project: Any, story: Any, filename: str, content: str) -> str:
    """Write a document file and return its relative path."""
    _validate_filename(filename)
    docs_dir = story_docs_dir(project, story)
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / filename).write_text(content, encoding="utf-8")
    logger.debug("Wrote doc %s for story %s", filename, story.id)
    return story_docs_relpath(story, filename)


def read_doc(project: Any, story: Any, filename: str) -> str | None:
    """Read a document file. Returns None if not found."""
    _validate_filename(filename)
    filepath = story_docs_dir(project, story) / filename
    if filepath.is_file():
        return filepath.read_text(encoding="utf-8")
    logger.debug("Doc not found: %s for story %s", filename, story.id)
    return None


def list_docs(project: Any, story: Any) -> list[str]:
    """List document filenames for a story."""
    docs_dir = story_docs_dir(project, story)
    if not docs_dir.is_dir():
        return []
    return sorted(f.name for f in docs_dir.iterdir() if f.is_file())


def _inject_token(repo_url: str, token: str | None) -> str:
    """Inject auth token into HTTPS git URLs."""
    if token and repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://x-access-token:{token}@")
    return repo_url


def _detect_proxy() -> dict[str, str]:
    """Detect system HTTPS proxy and return env dict for subprocess."""
    import os
    import subprocess as sp

    # 1) Already set in environment
    for var in ("https_proxy", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        if os.environ.get(var):
            return {}  # subprocess inherits it automatically

    # 2) macOS: read from networksetup
    try:
        out = sp.run(
            ["networksetup", "-getwebproxy", "Wi-Fi"],
            capture_output=True, text=True, timeout=3,
        )
        lines = {
            l.split(":")[0].strip(): l.split(":", 1)[1].strip()
            for l in out.stdout.splitlines() if ":" in l
        }
        if lines.get("Enabled") == "Yes" and lines.get("Server") and lines.get("Port"):
            proxy = f"http://{lines['Server']}:{lines['Port']}"
            logger.debug("Detected system proxy: %s", proxy)
            return {"https_proxy": proxy, "http_proxy": proxy}
    except Exception:
        pass

    return {}


async def clone_workspace(
    project: Any,
    repo_url: str,
    publish: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
    token: str | None = None,
) -> None:
    """Clone a git repo into the project workspace directory.

    Publishes progress events via the optional publish callback.
    If token is provided, injects it into HTTPS URLs for authentication.
    """
    work_dir = resolve_work_dir(project)
    auth_url = _inject_token(repo_url, token)
    proxy_env = _detect_proxy()
    # Merge proxy into current env for subprocess
    import os
    sub_env = {**os.environ, **proxy_env} if proxy_env else None

    if (work_dir / ".git").exists():
        logger.info("Workspace already cloned at %s, pulling latest", work_dir)
        proc = await asyncio.create_subprocess_exec(
            "git", "-c", "http.version=HTTP/1.1", "pull", "--ff-only",
            cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=sub_env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError("git pull timed out after 60s")
        if proc.returncode != 0:
            error = stderr.decode().strip()
            raise RuntimeError(f"git pull failed: {error}")
        if publish:
            await publish({"type": "workspace", "content": "Workspace updated (git pull)"})
        return

    work_dir.parent.mkdir(parents=True, exist_ok=True)
    if publish:
        await publish({"type": "workspace", "content": f"Cloning {repo_url}..."})

    proc = await asyncio.create_subprocess_exec(
        "git", "-c", "http.version=HTTP/1.1", "clone", auth_url, str(work_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=sub_env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("git clone timed out after 120s")
    if proc.returncode != 0:
        error = stderr.decode().strip()
        raise RuntimeError(f"git clone failed: {error}")

    if publish:
        await publish({"type": "workspace", "content": "Clone complete"})
