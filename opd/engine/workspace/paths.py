"""Workspace path resolution and document I/O."""

from __future__ import annotations

import logging
import re
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
