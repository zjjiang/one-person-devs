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


def delete_doc(project: Any, story: Any, filename: str) -> bool:
    """Delete a document file. Returns True if deleted."""
    _validate_filename(filename)
    filepath = story_docs_dir(project, story) / filename
    if filepath.is_file():
        filepath.unlink()
        logger.debug("Deleted doc %s for story %s", filename, story.id)
        return True
    return False


def list_docs(project: Any, story: Any) -> list[str]:
    """List document filenames for a story."""
    docs_dir = story_docs_dir(project, story)
    if not docs_dir.is_dir():
        return []
    return sorted(f.name for f in docs_dir.iterdir() if f.is_file())


# ---------------------------------------------------------------------------
# Source code scanning
# ---------------------------------------------------------------------------

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".tox",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".next", ".nuxt",
    "target", "vendor", ".idea", ".vscode",
}

_KEY_FILES = {
    "README.md", "README.rst", "pyproject.toml", "package.json",
    "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
    "Makefile", "Dockerfile", "docker-compose.yml",
    "CLAUDE.md",
}

_CODE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
    ".yaml", ".yml", ".toml", ".json", ".sql",
}


def scan_workspace(
    project: Any,
    max_depth: int = 3,
    max_chars: int = 8000,
) -> str:
    """Scan project workspace and return a formatted source context string.

    Generates a directory tree and reads snippets from key files.
    Returns empty string if workspace doesn't exist.
    """
    work_dir = resolve_work_dir(project)
    if not work_dir.is_dir():
        return ""

    lines: list[str] = ["## 项目源码结构\n```"]
    _build_tree(work_dir, work_dir, lines, depth=0, max_depth=max_depth)
    lines.append("```\n")

    # Read key files
    snippets: list[str] = []
    chars_used = sum(len(line) for line in lines)

    for kf in sorted(_KEY_FILES):
        fp = work_dir / kf
        if fp.is_file():
            content = _read_snippet(fp, max_lines=30)
            snippet = f"### {kf}\n```\n{content}\n```"
            if chars_used + len(snippet) > max_chars:
                break
            snippets.append(snippet)
            chars_used += len(snippet)

    # Also scan a few top-level source files for structure hints
    for child in sorted(work_dir.iterdir()):
        if child.is_file() and child.suffix in _CODE_EXTS and child.name not in _KEY_FILES:
            content = _read_snippet(child, max_lines=15)
            snippet = f"### {child.name}\n```\n{content}\n```"
            if chars_used + len(snippet) > max_chars:
                break
            snippets.append(snippet)
            chars_used += len(snippet)

    if snippets:
        lines.append("## 关键文件内容\n")
        lines.extend(snippets)

    return "\n".join(lines)


def _build_tree(
    root: Path, current: Path, lines: list[str],
    depth: int, max_depth: int,
) -> None:
    """Recursively build a directory tree representation."""
    if depth > max_depth:
        return
    indent = "  " * depth
    if depth > 0:
        lines.append(f"{indent}{current.name}/")

    try:
        children = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    except PermissionError:
        return

    for child in children:
        if child.name.startswith(".") and child.name not in (".env.example",):
            if child.name in _SKIP_DIRS:
                continue
        if child.is_dir():
            if child.name in _SKIP_DIRS:
                continue
            _build_tree(root, child, lines, depth + 1, max_depth)
        else:
            lines.append(f"{'  ' * (depth + 1)}{child.name}")


def _read_snippet(filepath: Path, max_lines: int = 30) -> str:
    """Read the first N lines of a file, handling encoding errors."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
        file_lines = text.splitlines()[:max_lines]
        if len(text.splitlines()) > max_lines:
            file_lines.append(f"... ({len(text.splitlines()) - max_lines} more lines)")
        return "\n".join(file_lines)
    except Exception:
        return "(unable to read)"


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


# ---------------------------------------------------------------------------
# Git branch management
# ---------------------------------------------------------------------------


def _is_git_workspace(project: Any) -> Path | None:
    """Return workspace path if it's a git repo, else None."""
    work_dir = resolve_work_dir(project)
    return work_dir if (work_dir / ".git").exists() else None


async def _git(
    work_dir: Path, *args: str, timeout: int = 30, network: bool = False,
) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr).

    Args:
        network: If True, inject proxy env and http.version=HTTP/1.1 for
                 commands that talk to a remote (pull, push, fetch).
        timeout: Seconds before killing the process.
    """
    cmd: list[str] = ["git"]
    env = None
    if network:
        cmd.extend(["-c", "http.version=HTTP/1.1"])
        proxy_env = _detect_proxy()
        if proxy_env:
            import os
            env = {**os.environ, **proxy_env}
    cmd.extend(args)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(work_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", f"git {args[0]} timed out after {timeout}s"
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


def generate_branch_name(story_id: int, round_number: int) -> str:
    """Generate a branch name for a coding round."""
    return f"opd/story-{story_id}-r{round_number}"


async def create_coding_branch(project: Any, branch_name: str) -> bool:
    """Create and checkout a new coding branch from main.

    Returns True if branch was created, False if workspace is not a git repo.
    """
    work_dir = _is_git_workspace(project)
    if not work_dir:
        return False

    # Ensure we're on main first
    await _git(work_dir, "checkout", "main")

    # Pull latest — non-fatal, branch from current HEAD if pull fails
    rc, _, err = await _git(work_dir, "pull", "--ff-only", timeout=60, network=True)
    if rc != 0:
        logger.warning("git pull failed (continuing from current HEAD): %s", err)

    # Create new branch
    rc, _, err = await _git(work_dir, "checkout", "-b", branch_name)
    if rc != 0:
        raise RuntimeError(f"Failed to create branch {branch_name}: {err}")

    # Push to remote so it's visible on GitHub
    rc, _, err = await _git(work_dir, "push", "-u", "origin", branch_name, timeout=60, network=True)
    if rc != 0:
        logger.warning("Failed to push branch %s: %s", branch_name, err)

    logger.info("Created branch %s in %s", branch_name, work_dir)
    return True


async def checkout_branch(project: Any, branch_name: str) -> bool:
    """Checkout an existing branch. Returns True on success."""
    work_dir = _is_git_workspace(project)
    if not work_dir:
        return False
    rc, _, err = await _git(work_dir, "checkout", branch_name)
    if rc != 0:
        raise RuntimeError(f"Failed to checkout {branch_name}: {err}")
    return True


async def discard_branch(project: Any, branch_name: str) -> None:
    """Switch to main and delete the given branch (local + remote)."""
    work_dir = _is_git_workspace(project)
    if not work_dir:
        return
    await _git(work_dir, "checkout", "main")
    rc, _, _ = await _git(work_dir, "branch", "-D", branch_name)
    if rc == 0:
        logger.info("Deleted local branch %s", branch_name)
    else:
        logger.warning("Could not delete local branch %s (may not exist)", branch_name)
    # Also delete remote branch
    rc, _, err = await _git(
        work_dir, "push", "origin", "--delete", branch_name, timeout=60, network=True,
    )
    if rc == 0:
        logger.info("Deleted remote branch %s", branch_name)
    else:
        logger.warning("Could not delete remote branch %s: %s", branch_name, err)
