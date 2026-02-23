"""Tests for workspace scanner module."""

from __future__ import annotations

from types import SimpleNamespace

from opd.engine.workspace.scanner import (
    _build_tree,
    _read_snippet,
    scan_workspace,
)


class TestReadSnippet:
    def test_reads_first_n_lines(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("\n".join(f"line {i}" for i in range(50)))
        result = _read_snippet(f, max_lines=5)
        assert "line 0" in result
        assert "line 4" in result
        assert "45 more lines" in result

    def test_short_file_no_truncation(self, tmp_path):
        f = tmp_path / "short.py"
        f.write_text("hello\nworld")
        result = _read_snippet(f, max_lines=30)
        assert "hello" in result
        assert "world" in result
        assert "more lines" not in result

    def test_unreadable_file(self, tmp_path):
        f = tmp_path / "bad.bin"
        f.write_bytes(b"\x80\x81\x82")
        result = _read_snippet(f)
        assert isinstance(result, str)


class TestBuildTree:
    def test_basic_tree(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("pass")
        (tmp_path / "README.md").write_text("hi")
        lines: list[str] = []
        _build_tree(tmp_path, tmp_path, lines, depth=0, max_depth=2)
        text = "\n".join(lines)
        assert "src/" in text
        assert "main.py" in text
        assert "README.md" in text

    def test_skips_node_modules(self, tmp_path):
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg.json").write_text("{}")
        lines: list[str] = []
        _build_tree(tmp_path, tmp_path, lines, depth=0, max_depth=2)
        text = "\n".join(lines)
        assert "node_modules" not in text

    def test_respects_max_depth(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "file.txt").write_text("deep")
        lines: list[str] = []
        _build_tree(tmp_path, tmp_path, lines, depth=0, max_depth=1)
        text = "\n".join(lines)
        assert "d/" not in text


class TestScanWorkspace:
    def test_returns_empty_for_missing_dir(self):
        project = SimpleNamespace(name="nope", workspace_dir="/nonexistent/path")
        assert scan_workspace(project) == ""

    def test_includes_tree_and_key_files(self, tmp_path):
        proj_dir = tmp_path / "myproj"
        proj_dir.mkdir()
        (proj_dir / "README.md").write_text("# Hello")
        (proj_dir / "src").mkdir()
        (proj_dir / "src" / "app.py").write_text("pass")
        project = SimpleNamespace(name="myproj", workspace_dir=str(tmp_path))
        result = scan_workspace(project)
        assert "项目源码结构" in result
        assert "README.md" in result

    def test_respects_max_chars(self, tmp_path):
        proj_dir = tmp_path / "myproj"
        proj_dir.mkdir()
        (proj_dir / "README.md").write_text("x" * 5000)
        (proj_dir / "pyproject.toml").write_text("y" * 5000)
        project = SimpleNamespace(name="myproj", workspace_dir=str(tmp_path))
        result = scan_workspace(project, max_chars=200)
        # Should be truncated, not include all files
        assert len(result) < 6000
