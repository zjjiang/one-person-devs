"""Workspace path resolution and document I/O."""

from __future__ import annotations

import logging
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Story field → document filename mapping (single source of truth)
DOC_FIELD_MAP: dict[str, str] = {
    "prd": "prd.md",
    "technical_design": "technical_design.md",
    "detailed_design": "detailed_design.md",
    "coding_report": "coding_report.md",
    "test_guide": "test_guide.md",
}

# Reverse mapping: filename → Story field
DOC_FILENAME_MAP: dict[str, str] = {v: k for k, v in DOC_FIELD_MAP.items()}


def _sanitize(name: str) -> str:
    """Sanitize a string for use as a directory name."""
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r"[^\w\s-]", "", name.lower())
    return re.sub(r"[\s_]+", "-", name).strip("-")[:80]


def resolve_work_dir(project: Any) -> Path:
    """Resolve the project workspace directory.

    Returns {workspace_dir}/{sanitized_project_name}.
    """
    workspace_dir = (getattr(project, "workspace_dir", "") or "./workspace").strip()
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


def _story_branches(work_dir: Path, story_id: int) -> list[str]:
    """Return local opd branches for a story, sorted by round number descending.

    E.g. for story 1: ["opd/story-1-r3", "opd/story-1-r2", "opd/story-1-r1"].
    Latest round first so callers always read the newest version.
    """
    try:
        result = subprocess.run(
            ["git", "branch", "--list", f"opd/story-{story_id}-*"],
            cwd=str(work_dir), capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return []
        branches = [b.strip().lstrip("* ") for b in result.stdout.splitlines() if b.strip()]

        def _round_num(name: str) -> int:
            m = re.search(r"-r(\d+)$", name)
            return int(m.group(1)) if m else 0

        branches.sort(key=_round_num, reverse=True)
        return branches
    except Exception:
        logger.debug("Failed to list branches for story %s", story_id, exc_info=True)
        return []


def _git_show_doc(work_dir: Path, story_id: int, rel_path: str) -> str | None:
    """Try to read a file from the latest story branch via git show.

    When the workspace is on main, story docs committed on coding branches
    are not on the filesystem. This falls back to ``git show branch:path``.
    Checks branches in reverse round order (latest first).
    """
    for branch in _story_branches(work_dir, story_id):
        try:
            out = subprocess.run(
                ["git", "show", f"{branch}:{rel_path}"],
                cwd=str(work_dir), capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0 and out.stdout:
                logger.debug("Read doc %s from branch %s via git show", rel_path, branch)
                return out.stdout
        except Exception:
            pass
    return None


def _git_list_docs(work_dir: Path, story_id: int, slug: str) -> list[str]:
    """List doc filenames from the latest story branch via git ls-tree."""
    for branch in _story_branches(work_dir, story_id):
        try:
            out = subprocess.run(
                ["git", "-c", "core.quotePath=false",
                 "ls-tree", "--name-only", branch, f"docs/{slug}/"],
                cwd=str(work_dir), capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0 and out.stdout.strip():
                files = []
                for line in out.stdout.strip().splitlines():
                    name = line.strip().rsplit("/", 1)[-1]
                    if name:
                        files.append(name)
                if files:
                    return sorted(files)
        except Exception:
            pass
    return []


def read_doc(project: Any, story: Any, filename: str) -> str | None:
    """Read a document file. Falls back to git show if not on current branch."""
    _validate_filename(filename)
    filepath = story_docs_dir(project, story) / filename
    if filepath.is_file():
        return filepath.read_text(encoding="utf-8")
    # Fallback: read from story branch via git show
    work_dir = resolve_work_dir(project)
    if (work_dir / ".git").exists():
        rel_path = story_docs_relpath(story, filename)
        content = _git_show_doc(work_dir, story.id, rel_path)
        if content is not None:
            return content
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
    if docs_dir.is_dir():
        return sorted(f.name for f in docs_dir.iterdir() if f.is_file())
    # Fallback: list from story branches via git ls-tree
    work_dir = resolve_work_dir(project)
    if (work_dir / ".git").exists():
        return _git_list_docs(work_dir, story.id, story_slug(story))
    return []
