"""Tests for workspace utilities: branch management, doc I/O, paths, git helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from opd.engine.workspace import (
    checkout_branch,
    create_coding_branch,
    delete_doc,
    discard_branch,
    generate_branch_name,
    list_docs,
    read_doc,
    resolve_work_dir,
    story_docs_dir,
    story_slug,
    write_doc,
)
from opd.engine.workspace.git import _inject_token
from opd.engine.workspace.paths import _sanitize


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

        with patch("opd.engine.workspace.git._git", side_effect=mock_git):
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

        with patch("opd.engine.workspace.git._git", side_effect=mock_git):
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

        with patch("opd.engine.workspace.git._git", side_effect=mock_git):
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


class TestSanitize:
    def test_basic(self):
        assert _sanitize("Hello World") == "hello-world"

    def test_special_chars(self):
        result = _sanitize("My Project! @#$%")
        assert "/" not in result
        assert "@" not in result

    def test_unicode(self):
        result = _sanitize("项目名称")
        assert isinstance(result, str)

    def test_truncates_long_names(self):
        result = _sanitize("a" * 200)
        assert len(result) <= 80


class TestResolveWorkDir:
    def test_uses_workspace_dir(self, tmp_path):
        project = SimpleNamespace(name="myproj", workspace_dir=str(tmp_path))
        result = resolve_work_dir(project)
        assert result.name == "myproj"
        assert str(tmp_path) in str(result)

    def test_defaults_to_workspace(self):
        project = SimpleNamespace(name="test", workspace_dir="")
        result = resolve_work_dir(project)
        assert "workspace" in str(result)


class TestStorySlug:
    def test_includes_id_and_title(self):
        story = SimpleNamespace(id=42, title="Login Feature")
        slug = story_slug(story)
        assert slug.startswith("42-")
        assert "login" in slug

    def test_id_only_for_empty_title(self):
        story = SimpleNamespace(id=7, title="")
        assert story_slug(story) == "7"


class TestDeleteDoc:
    def test_deletes_existing(self, tmp_path):
        project = SimpleNamespace(name="test", workspace_dir=str(tmp_path))
        story = SimpleNamespace(id=1, title="test")
        write_doc(project, story, "test.md", "content")
        assert delete_doc(project, story, "test.md") is True
        assert read_doc(project, story, "test.md") is None

    def test_returns_false_for_missing(self, tmp_path):
        project = SimpleNamespace(name="test", workspace_dir=str(tmp_path))
        story = SimpleNamespace(id=1, title="test")
        assert delete_doc(project, story, "nope.md") is False


class TestListDocs:
    def test_lists_files(self, tmp_path):
        project = SimpleNamespace(name="test", workspace_dir=str(tmp_path))
        story = SimpleNamespace(id=1, title="test")
        write_doc(project, story, "a.md", "aaa")
        write_doc(project, story, "b.md", "bbb")
        files = list_docs(project, story)
        assert files == ["a.md", "b.md"]

    def test_empty_for_no_dir(self, tmp_path):
        project = SimpleNamespace(name="test", workspace_dir=str(tmp_path))
        story = SimpleNamespace(id=99, title="nope")
        assert list_docs(project, story) == []


class TestInjectToken:
    def test_injects_into_https(self):
        url = _inject_token("https://github.com/org/repo", "mytoken")
        assert "x-access-token:mytoken@" in url

    def test_no_token_returns_original(self):
        url = _inject_token("https://github.com/org/repo", None)
        assert url == "https://github.com/org/repo"

    def test_non_https_unchanged(self):
        url = _inject_token("git@github.com:org/repo.git", "token")
        assert url == "git@github.com:org/repo.git"


class TestCheckoutBranch:
    async def test_returns_false_without_git(self, tmp_path):
        project = SimpleNamespace(name="test", workspace_dir=str(tmp_path))
        result = await checkout_branch(project, "some-branch")
        assert result is False

    async def test_raises_on_failure(self, tmp_path):
        git_dir = tmp_path / "test" / ".git"
        git_dir.mkdir(parents=True)

        async def mock_git(work_dir, *args, **kwargs):
            return (1, "", "error: pathspec 'bad' did not match")

        with patch("opd.engine.workspace.git._git", side_effect=mock_git):
            with pytest.raises(RuntimeError, match="Failed to checkout"):
                await checkout_branch(
                    SimpleNamespace(name="test", workspace_dir=str(tmp_path)),
                    "bad-branch",
                )
