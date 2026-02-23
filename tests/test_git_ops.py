"""Tests for workspace/git.py operations."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from opd.engine.workspace.git import (
    _detect_proxy,
    _git,
    _is_git_workspace,
    clone_workspace,
    create_coding_branch,
    discard_branch,
    get_latest_merge_diff,
)


# ── _detect_proxy ──


class TestDetectProxy:
    def setup_method(self):
        _detect_proxy.cache_clear()

    @patch.dict("os.environ", {"https_proxy": "http://proxy:8080"})
    def test_returns_empty_when_env_set(self):
        assert _detect_proxy() == ()

    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run")
    def test_detects_macos_proxy(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="Enabled: Yes\nServer: 127.0.0.1\nPort: 7890\n"
        )
        result = dict(_detect_proxy())
        assert result["https_proxy"] == "http://127.0.0.1:7890"

    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_returns_empty_on_error(self, _):
        assert _detect_proxy() == ()

    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run")
    def test_returns_empty_when_disabled(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="Enabled: No\nServer: 127.0.0.1\nPort: 7890\n"
        )
        assert _detect_proxy() == ()


# ── _git ──


class TestGitCommand:
    @patch("opd.engine.workspace.git._detect_proxy", return_value={})
    async def test_git_success(self, _):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"output\n", b"")
        mock_proc.returncode = 0
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            rc, out, err = await _git("/tmp", "status")
        assert rc == 0
        assert out == "output"

    @patch("opd.engine.workspace.git._detect_proxy", return_value={})
    async def test_git_failure(self, _):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"fatal: error\n")
        mock_proc.returncode = 128
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            rc, out, err = await _git("/tmp", "checkout", "missing")
        assert rc == 128
        assert "fatal" in err

    @patch("opd.engine.workspace.git._detect_proxy", return_value={})
    async def test_git_timeout(self, _):
        import asyncio
        mock_proc = AsyncMock()
        mock_proc.communicate.side_effect = asyncio.TimeoutError
        mock_proc.kill = MagicMock()
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            rc, out, err = await _git("/tmp", "pull", timeout=1)
        assert rc == -1
        assert "timed out" in err

    @patch("opd.engine.workspace.git._detect_proxy", return_value={"https_proxy": "http://p:8080"})
    async def test_git_network_injects_proxy(self, _):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"ok", b"")
        mock_proc.returncode = 0
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await _git("/tmp", "push", network=True)
            # Should include -c http.version=HTTP/1.1
            call_args = mock_exec.call_args
            cmd = call_args[0]
            assert "http.version=HTTP/1.1" in cmd


# ── _is_git_workspace ──


class TestIsGitWorkspace:
    @patch("opd.engine.workspace.git.resolve_work_dir")
    def test_is_git(self, mock_resolve, tmp_path):
        (tmp_path / ".git").mkdir()
        mock_resolve.return_value = tmp_path
        result = _is_git_workspace(SimpleNamespace())
        assert result == tmp_path

    @patch("opd.engine.workspace.git.resolve_work_dir")
    def test_not_git(self, mock_resolve, tmp_path):
        mock_resolve.return_value = tmp_path
        assert _is_git_workspace(SimpleNamespace()) is None


# ── clone_workspace ──


class TestCloneWorkspace:
    @patch("opd.engine.workspace.git._detect_proxy", return_value={})
    @patch("opd.engine.workspace.git.resolve_work_dir")
    async def test_clone_fresh(self, mock_resolve, _, tmp_path):
        work_dir = tmp_path / "workspace"
        work_dir.parent.mkdir(parents=True, exist_ok=True)
        mock_resolve.return_value = work_dir

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await clone_workspace(SimpleNamespace(), "https://github.com/t/r")

    @patch("opd.engine.workspace.git._detect_proxy", return_value={})
    @patch("opd.engine.workspace.git.resolve_work_dir")
    async def test_clone_existing_pulls(self, mock_resolve, _, tmp_path):
        work_dir = tmp_path / "workspace"
        work_dir.mkdir()
        (work_dir / ".git").mkdir()
        mock_resolve.return_value = work_dir

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"Already up to date.", b"")
        mock_proc.returncode = 0
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await clone_workspace(SimpleNamespace(), "https://github.com/t/r")

    @patch("opd.engine.workspace.git._detect_proxy", return_value={})
    @patch("opd.engine.workspace.git.resolve_work_dir")
    async def test_clone_with_token(self, mock_resolve, _, tmp_path):
        work_dir = tmp_path / "workspace"
        work_dir.parent.mkdir(parents=True, exist_ok=True)
        mock_resolve.return_value = work_dir

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await clone_workspace(SimpleNamespace(), "https://github.com/t/r",
                                  token="ghp_test123")
            cmd = mock_exec.call_args[0]
            assert any("x-access-token:ghp_test123@" in str(c) for c in cmd)

    @patch("opd.engine.workspace.git._detect_proxy", return_value={})
    @patch("opd.engine.workspace.git.resolve_work_dir")
    async def test_clone_failure_raises(self, mock_resolve, _, tmp_path):
        work_dir = tmp_path / "workspace"
        work_dir.parent.mkdir(parents=True, exist_ok=True)
        mock_resolve.return_value = work_dir

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"fatal: repo not found")
        mock_proc.returncode = 128
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="git clone failed"):
                await clone_workspace(SimpleNamespace(), "https://github.com/t/r")

    @patch("opd.engine.workspace.git._detect_proxy", return_value={})
    @patch("opd.engine.workspace.git.resolve_work_dir")
    async def test_clone_with_publish(self, mock_resolve, _, tmp_path):
        work_dir = tmp_path / "workspace"
        work_dir.parent.mkdir(parents=True, exist_ok=True)
        mock_resolve.return_value = work_dir

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0
        published = []
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await clone_workspace(SimpleNamespace(), "https://github.com/t/r",
                                  publish=AsyncMock(side_effect=lambda e: published.append(e)))
        assert len(published) >= 1


# ── create_coding_branch ──


class TestCreateCodingBranch:
    @patch("opd.engine.workspace.git._is_git_workspace", return_value=None)
    async def test_not_git_returns_false(self, _):
        result = await create_coding_branch(SimpleNamespace(), "branch")
        assert result is False

    @patch("opd.engine.workspace.git._is_git_workspace")
    @patch("opd.engine.workspace.git._git")
    async def test_create_branch_ok(self, mock_git, mock_is_git, tmp_path):
        mock_is_git.return_value = tmp_path
        mock_git.return_value = (0, "", "")
        result = await create_coding_branch(SimpleNamespace(), "opd/story-1-r1")
        assert result is True
        assert mock_git.call_count >= 3  # checkout main, pull, checkout -b, push

    @patch("opd.engine.workspace.git._is_git_workspace")
    @patch("opd.engine.workspace.git._git")
    async def test_create_branch_fails(self, mock_git, mock_is_git, tmp_path):
        mock_is_git.return_value = tmp_path
        mock_git.side_effect = [
            (0, "", ""),  # checkout main
            (0, "", ""),  # pull
            (128, "", "already exists"),  # checkout -b fails
        ]
        with pytest.raises(RuntimeError, match="Failed to create branch"):
            await create_coding_branch(SimpleNamespace(), "opd/story-1-r1")


# ── discard_branch ──


class TestDiscardBranch:
    @patch("opd.engine.workspace.git._is_git_workspace", return_value=None)
    async def test_not_git_returns_early(self, _):
        await discard_branch(SimpleNamespace(), "branch")  # should not raise

    @patch("opd.engine.workspace.git._is_git_workspace")
    @patch("opd.engine.workspace.git._git")
    async def test_discard_ok(self, mock_git, mock_is_git, tmp_path):
        mock_is_git.return_value = tmp_path
        mock_git.return_value = (0, "", "")
        await discard_branch(SimpleNamespace(), "opd/story-1-r1")
        assert mock_git.call_count >= 3  # checkout main, branch -D, push --delete


# ── get_latest_merge_diff ──


class TestGetLatestMergeDiff:
    @patch("opd.engine.workspace.git._is_git_workspace", return_value=None)
    async def test_not_git_returns_none(self, _):
        result = await get_latest_merge_diff(SimpleNamespace())
        assert result is None

    @patch("opd.engine.workspace.git._is_git_workspace")
    @patch("opd.engine.workspace.git._git")
    async def test_returns_stat_and_diff(self, mock_git, mock_is_git, tmp_path):
        mock_is_git.return_value = tmp_path
        mock_git.side_effect = [
            (0, "file.py | 3 +++", ""),   # --stat
            (0, "+added line", ""),         # diff
        ]
        result = await get_latest_merge_diff(SimpleNamespace())
        assert "Changed files" in result
        assert "+added line" in result

    @patch("opd.engine.workspace.git._is_git_workspace")
    @patch("opd.engine.workspace.git._git")
    async def test_stat_fails_returns_none(self, mock_git, mock_is_git, tmp_path):
        mock_is_git.return_value = tmp_path
        mock_git.return_value = (128, "", "fatal")
        result = await get_latest_merge_diff(SimpleNamespace())
        assert result is None

    @patch("opd.engine.workspace.git._is_git_workspace")
    @patch("opd.engine.workspace.git._git")
    async def test_diff_fails_returns_stat_only(self, mock_git, mock_is_git, tmp_path):
        mock_is_git.return_value = tmp_path
        mock_git.side_effect = [
            (0, "file.py | 3 +++", ""),
            (128, "", "fatal"),
        ]
        result = await get_latest_merge_diff(SimpleNamespace())
        assert result == "file.py | 3 +++"

    @patch("opd.engine.workspace.git._is_git_workspace")
    @patch("opd.engine.workspace.git._git")
    async def test_truncates_large_diff(self, mock_git, mock_is_git, tmp_path):
        mock_is_git.return_value = tmp_path
        big_diff = "x" * 10000
        mock_git.side_effect = [
            (0, "stat", ""),
            (0, big_diff, ""),
        ]
        result = await get_latest_merge_diff(SimpleNamespace(), max_chars=100)
        assert "truncated" in result
