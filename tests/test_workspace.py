"""Tests for workspace utilities: branch management and doc I/O."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from opd.engine.workspace import (
    create_coding_branch,
    discard_branch,
    generate_branch_name,
    read_doc,
    story_docs_dir,
    write_doc,
)


class TestGenerateBranchName:
    def test_format(self):
        assert generate_branch_name(1, 1) == "opd/story-1-r1"

    def test_different_ids(self):
        assert generate_branch_name(42, 3) == "opd/story-42-r3"


class TestDocIO:
    def test_write_and_read(self, tmp_path):
        project = SimpleNamespace(name="test", workspace_dir=str(tmp_path))
        story = SimpleNamespace(id=1, title="test story")
        rel = write_doc(project, story, "test.md", "hello world")
        assert rel.startswith("docs/")
        content = read_doc(project, story, "test.md")
        assert content == "hello world"

    def test_read_nonexistent(self, tmp_path):
        project = SimpleNamespace(name="test", workspace_dir=str(tmp_path))
        story = SimpleNamespace(id=1, title="test story")
        assert read_doc(project, story, "missing.md") is None

    def test_invalid_filename_rejected(self, tmp_path):
        project = SimpleNamespace(name="test", workspace_dir=str(tmp_path))
        story = SimpleNamespace(id=1, title="test story")
        with pytest.raises(ValueError, match="Invalid filename"):
            write_doc(project, story, "../evil.md", "bad")

    def test_story_docs_dir_structure(self, tmp_path):
        project = SimpleNamespace(name="myproj", workspace_dir=str(tmp_path))
        story = SimpleNamespace(id=5, title="Login Feature")
        docs_dir = story_docs_dir(project, story)
        assert "myproj" in str(docs_dir)
        assert "docs" in str(docs_dir)


class TestCreateCodingBranch:
    async def test_returns_false_without_git(self, tmp_path):
        """No .git directory → returns False."""
        project = SimpleNamespace(name="test", workspace_dir=str(tmp_path))
        result = await create_coding_branch(project, "opd/story-1-r1")
        assert result is False

    async def test_pull_failure_non_fatal(self, tmp_path):
        """git pull failure should not prevent branch creation."""
        git_dir = tmp_path / "test" / ".git"
        git_dir.mkdir(parents=True)

        call_count = 0

        async def mock_git(work_dir, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            cmd = args[0] if args else ""
            if cmd == "pull":
                return (-1, "", "pull timed out after 60s")
            return (0, "", "")

        with patch("opd.engine.workspace._git", side_effect=mock_git):
            result = await create_coding_branch(
                SimpleNamespace(name="test", workspace_dir=str(tmp_path)),
                "opd/story-1-r1",
            )
        assert result is True
        assert call_count == 4  # checkout main, pull, checkout -b, push

    async def test_branch_creation_failure_raises(self, tmp_path):
        git_dir = tmp_path / "test" / ".git"
        git_dir.mkdir(parents=True)

        async def mock_git(work_dir, *args, **kwargs):
            cmd = args[0] if args else ""
            if cmd == "checkout" and len(args) > 1 and args[1] == "-b":
                return (1, "", "branch already exists")
            return (0, "", "")

        with patch("opd.engine.workspace._git", side_effect=mock_git):
            with pytest.raises(RuntimeError, match="Failed to create branch"):
                await create_coding_branch(
                    SimpleNamespace(name="test", workspace_dir=str(tmp_path)),
                    "opd/story-1-r1",
                )


class TestDiscardBranch:
    async def test_returns_early_without_git(self, tmp_path):
        project = SimpleNamespace(name="test", workspace_dir=str(tmp_path))
        # Should not raise
        await discard_branch(project, "opd/story-1-r1")

    async def test_deletes_local_and_remote(self, tmp_path):
        git_dir = tmp_path / "test" / ".git"
        git_dir.mkdir(parents=True)

        commands: list[tuple] = []

        async def mock_git(work_dir, *args, **kwargs):
            commands.append(args)
            return (0, "", "")

        with patch("opd.engine.workspace._git", side_effect=mock_git):
            await discard_branch(
                SimpleNamespace(name="test", workspace_dir=str(tmp_path)),
                "opd/story-1-r1",
            )

        # Should have: checkout main, branch -D, push --delete
        assert len(commands) == 3
        assert commands[0] == ("checkout", "main")
        assert commands[1] == ("branch", "-D", "opd/story-1-r1")
        assert commands[2][0] == "push"
        assert "--delete" in commands[2]
