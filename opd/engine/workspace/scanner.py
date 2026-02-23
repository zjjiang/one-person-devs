"""Source code scanning: directory tree and key file snippets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opd.engine.workspace.paths import resolve_work_dir

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
        all_lines = text.splitlines()
        file_lines = all_lines[:max_lines]
        if len(all_lines) > max_lines:
            file_lines.append(f"... ({len(all_lines) - max_lines} more lines)")
        return "\n".join(file_lines)
    except Exception:
        return "(unable to read)"
