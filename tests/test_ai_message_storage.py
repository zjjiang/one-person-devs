"""Tests for AI message hybrid storage."""

import gzip
from pathlib import Path
from types import SimpleNamespace

import pytest

from opd.engine.ai_message_storage import (
    FILE_THRESHOLD,
    read_ai_message_content,
    write_ai_message_content,
    migrate_message_to_hybrid,
)


@pytest.fixture
def mock_project(tmp_path):
    """Mock project with temp workspace."""
    return SimpleNamespace(
        id=1,
        name="test-project",
        workspace_dir=str(tmp_path),
    )


def test_inline_storage_small_message(mock_project):
    """Short messages should use inline storage."""
    content = "Short message" * 100  # ~1.3KB
    result = write_ai_message_content(mock_project, round_id=1, message_id=1, content=content)

    assert result["storage_type"] == "inline"
    assert result["content"] == content
    assert result["content_file_path"] is None
    assert result["content_size"] == len(content.encode("utf-8"))


def test_inline_storage_medium_message(mock_project):
    """Medium messages (< 50KB) should still use inline storage."""
    content = "Medium message " * 2000  # ~30KB
    result = write_ai_message_content(mock_project, round_id=1, message_id=2, content=content)

    assert result["storage_type"] == "inline"
    assert result["content"] == content
    assert result["content_file_path"] is None
    assert result["content_size"] == len(content.encode("utf-8"))


def test_file_storage_large_message(mock_project):
    """Large messages should use file storage."""
    content = "Large message " * 5000  # ~70KB
    result = write_ai_message_content(mock_project, round_id=1, message_id=3, content=content)

    assert result["storage_type"] == "file"
    assert result["content"] == ""
    assert result["content_file_path"] == "ai_messages/1/3.txt.gz"
    assert result["content_size"] == len(content.encode("utf-8"))

    # Verify file exists and is readable (resolve_work_dir adds project name)
    from opd.engine.workspace import resolve_work_dir
    work_dir = resolve_work_dir(mock_project)
    file_path = work_dir / result["content_file_path"]
    assert file_path.is_file()

    with gzip.open(file_path, "rb") as f:
        decompressed = f.read().decode("utf-8")
    assert decompressed == content


def test_read_inline_message():
    """Read inline message."""
    msg = SimpleNamespace(
        id=1,
        storage_type="inline",
        content="Test content",
        content_file_path=None,
    )
    project = SimpleNamespace(id=1, name="test")

    result = read_ai_message_content(msg, project)
    assert result == "Test content"


def test_migrate_small_message_stays_inline(mock_project):
    """Small messages should stay inline after migration."""
    msg = SimpleNamespace(
        id=7,
        round_id=1,
        storage_type="inline",
        content="Small message" * 100,  # ~1.3KB
        content_compressed=None,
        content_file_path=None,
    )

    result = migrate_message_to_hybrid(msg, mock_project)
    assert result == {"content_size": len(msg.content.encode("utf-8"))}


def test_migrate_large_message_to_file(mock_project):
    """Large inline messages should migrate to file storage."""
    content = "Migrate me " * 5000  # ~50KB+
    msg = SimpleNamespace(
        id=8,
        round_id=1,
        storage_type="inline",
        content=content,
        content_compressed=None,
        content_file_path=None,
    )

    result = migrate_message_to_hybrid(msg, mock_project)
    assert result is not None
    assert result["storage_type"] == "file"
    assert result["content_file_path"] is not None


def test_migrate_already_migrated_message(mock_project):
    """Already migrated messages should be skipped."""
    msg = SimpleNamespace(
        id=9,
        round_id=1,
        storage_type="file",
        content="",
        content_file_path="ai_messages/1/9.txt.gz",
    )

    result = migrate_message_to_hybrid(msg, mock_project)
    assert result is None

