"""Git operations: clone, branch management, and shared helpers."""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from opd.engine.workspace.paths import resolve_work_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _inject_token(repo_url: str, token: str | None) -> str:
    """Inject auth token into HTTPS git URLs."""
    if token and repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://x-access-token:{token}@")
    return repo_url


@functools.lru_cache(maxsize=1)
def _detect_proxy() -> tuple[tuple[str, str], ...]:
    """Detect system HTTPS proxy and return env dict for subprocess."""
    import os
    import subprocess as sp

    for var in ("https_proxy", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        if os.environ.get(var):
            return ()  # subprocess inherits it automatically

    try:
        out = sp.run(
            ["networksetup", "-getwebproxy", "Wi-Fi"],
            capture_output=True, text=True, timeout=3,
        )
        lines = {
            ln.split(":")[0].strip(): ln.split(":", 1)[1].strip()
            for ln in out.stdout.splitlines() if ":" in ln
        }
        if lines.get("Enabled") == "Yes" and lines.get("Server") and lines.get("Port"):
            proxy = f"http://{lines['Server']}:{lines['Port']}"
            logger.debug("Detected system proxy: %s", proxy)
            return (("https_proxy", proxy), ("http_proxy", proxy))
    except Exception:
        pass

    return ()


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
        proxy_env = dict(_detect_proxy())
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


# ---------------------------------------------------------------------------
# Clone operations
# ---------------------------------------------------------------------------


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
    proxy_env = dict(_detect_proxy())
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
# Branch management
# ---------------------------------------------------------------------------


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

    await _git(work_dir, "checkout", "main")

    rc, _, err = await _git(work_dir, "pull", "--ff-only", timeout=60, network=True)
    if rc != 0:
        logger.warning("git pull failed (continuing from current HEAD): %s", err)

    rc, _, err = await _git(work_dir, "checkout", "-b", branch_name)
    if rc != 0:
        raise RuntimeError(f"Failed to create branch {branch_name}: {err}")

    rc, _, err = await _git(
        work_dir, "push", "-u", "origin", branch_name, timeout=60, network=True,
    )
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
    rc, _, err = await _git(
        work_dir, "push", "origin", "--delete", branch_name, timeout=60, network=True,
    )
    if rc == 0:
        logger.info("Deleted remote branch %s", branch_name)
    else:
        logger.warning("Could not delete remote branch %s: %s", branch_name, err)


async def pull_main(project: Any) -> bool:
    """Checkout main and pull latest. Returns True on success."""
    work_dir = _is_git_workspace(project)
    if not work_dir:
        return False
    rc, _, err = await _git(work_dir, "checkout", "main")
    if rc != 0:
        logger.warning("Failed to checkout main: %s", err)
        return False
    rc, _, err = await _git(work_dir, "pull", "--ff-only", timeout=60, network=True)
    if rc != 0:
        logger.warning("Failed to pull main: %s", err)
        return False
    logger.info("Pulled latest main in %s", work_dir)
    return True


async def commit_and_push_file(
    project: Any, filepath: str, message: str,
    *, content: str | None = None, target_branch: str = "main",
) -> bool:
    """Write (optionally), commit, and push a file to target_branch.

    If content is provided, the file is written AFTER checking out target_branch
    to avoid losing it during branch switch.
    Safely stashes uncommitted work and restores the original branch afterwards.
    """
    work_dir = _is_git_workspace(project)
    if not work_dir:
        return False

    # Remember current branch
    rc, original_branch, _ = await _git(work_dir, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return False
    original_branch = original_branch.strip()

    need_switch = original_branch != target_branch
    stashed = False

    try:
        if need_switch:
            # Stash uncommitted changes to safely switch branches
            rc, stash_out, _ = await _git(work_dir, "stash", "push", "-m", "opd-sync-context")
            stashed = rc == 0 and "No local changes" not in stash_out

            rc, _, err = await _git(work_dir, "checkout", target_branch)
            if rc != 0:
                logger.warning("Failed to checkout %s: %s", target_branch, err)
                return False

        # Write file content after checkout so it exists on the target branch
        if content is not None:
            (work_dir / filepath).write_text(content, encoding="utf-8")

        rc, _, err = await _git(work_dir, "add", filepath)
        if rc != 0:
            logger.warning("git add failed for %s: %s", filepath, err)
            return False

        # Check if there are staged changes (avoid empty commits)
        rc, stdout, _ = await _git(work_dir, "diff", "--cached", "--name-only")
        if rc == 0 and not stdout.strip():
            logger.info("No changes to commit for %s", filepath)
            return True

        rc, _, err = await _git(work_dir, "commit", "-m", message)
        if rc != 0:
            logger.warning("git commit failed: %s", err)
            return False

        rc, _, err = await _git(work_dir, "push", timeout=60, network=True)
        if rc != 0:
            logger.warning("git push failed: %s", err)
            return False

        logger.info("Committed and pushed %s to %s in %s", filepath, target_branch, work_dir)
        return True
    finally:
        # Restore original branch
        if need_switch:
            await _git(work_dir, "checkout", original_branch)
            if stashed:
                await _git(work_dir, "stash", "pop")
