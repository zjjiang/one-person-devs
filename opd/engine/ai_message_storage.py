"""AI message hybrid storage — transparent read/write with file fallback."""

from __future__ import annotations

import gzip
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opd.db.models import AIMessage

logger = logging.getLogger(__name__)

# Storage threshold (bytes)
FILE_THRESHOLD = 50 * 1024  # 50KB


def _get_message_file_path(project: Any, round_id: int, message_id: int) -> Path:
    """Return absolute path for message file storage.

    Pattern: {workspace_dir}/{project_name}/ai_messages/{round_id}/{message_id}.txt.gz
    """
    from opd.engine.workspace import resolve_work_dir

    work_dir = resolve_work_dir(project)
    return work_dir / "ai_messages" / str(round_id) / f"{message_id}.txt.gz"


def _get_message_file_relpath(round_id: int, message_id: int) -> str:
    """Return relative path stored in DB."""
    return f"ai_messages/{round_id}/{message_id}.txt.gz"


def write_ai_message_content(
    project: Any, round_id: int, message_id: int, content: str
) -> dict[str, Any]:
    """Write AI message content using hybrid storage strategy.

    Returns dict with fields to update on AIMessage:
        - storage_type: "inline" | "file"
        - content: str (for inline) or "" (for file)
        - content_file_path: str | None
        - content_size: int
    """
    content_bytes = content.encode("utf-8")
    size = len(content_bytes)

    # Strategy 1: Inline storage (< 50KB)
    if size < FILE_THRESHOLD:
        logger.debug("Storing message %s inline (%d bytes)", message_id, size)
        return {
            "storage_type": "inline",
            "content": content,
            "content_file_path": None,
            "content_size": size,
        }

    # Strategy 2: File storage (≥ 50KB)
    file_path = _get_message_file_path(project, round_id, message_id)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Write compressed to file (still use gzip for file storage efficiency)
    with gzip.open(file_path, "wb") as f:
        f.write(content_bytes)

    file_size = file_path.stat().st_size
    ratio = file_size / size if size > 0 else 1.0
    logger.info(
        "Stored message %s to file (%d → %d bytes, %.1f%%) at %s",
        message_id, size, file_size, ratio * 100, file_path,
    )

    return {
        "storage_type": "file",
        "content": "",  # Clear inline content
        "content_file_path": _get_message_file_relpath(round_id, message_id),
        "content_size": size,
    }


def read_ai_message_content(message: AIMessage, project: Any) -> str:
    """Read AI message content from hybrid storage.

    Handles both storage types transparently.
    Raises ValueError if content cannot be read.
    """
    storage_type = getattr(message, "storage_type", "inline")

    # Strategy 1: Inline storage
    if storage_type == "inline":
        return message.content

    # Strategy 2: File storage
    if storage_type == "file":
        file_path_rel = message.content_file_path
        if not file_path_rel:
            logger.error("Message %s marked file but no path", message.id)
            raise ValueError(f"File path missing for message {message.id}")

        from opd.engine.workspace import resolve_work_dir
        work_dir = resolve_work_dir(project)
        file_path = work_dir / file_path_rel

        if not file_path.is_file():
            logger.error("Message file not found: %s", file_path)
            raise ValueError(f"Message file not found: {file_path}")

        try:
            with gzip.open(file_path, "rb") as f:
                return f.read().decode("utf-8")
        except Exception as e:
            logger.error("Failed to read message file %s: %s", file_path, e)
            raise ValueError(f"File read failed for message {message.id}") from e

    # Unknown storage type — fallback to inline
    logger.warning(
        "Unknown storage_type '%s' for message %s, using inline",
        storage_type, message.id,
    )
    return message.content


def migrate_message_to_hybrid(
    message: AIMessage, project: Any
) -> dict[str, Any] | None:
    """Migrate an existing inline message to hybrid storage if beneficial.

    Returns update dict if migration needed, None otherwise.
    """
    # Skip if already migrated
    storage_type = getattr(message, "storage_type", "inline")
    if storage_type != "inline":
        return None

    # Skip if content is empty
    content = message.content
    if not content:
        return None

    size = len(content.encode("utf-8"))

    # Update content_size for all messages
    if size < FILE_THRESHOLD:
        return {"content_size": size}

    # Migrate large messages to file storage
    logger.info("Migrating message %s (%d bytes) to file storage", message.id, size)
    return write_ai_message_content(project, message.round_id, message.id, content)

