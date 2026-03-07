"""Assembler: programmatic CLAUDE.md generation from extracted snippets + AI descriptions."""

from __future__ import annotations

import logging
from pathlib import Path

from opd.engine.memory.extractor import CodeSnippet
from opd.engine.memory.generator import MODULE_ORDER, ModuleDoc

logger = logging.getLogger(__name__)


def assemble_claude_md(
    *,
    project_name: str,
    project_desc: str = "",
    tech_stack: str = "",
    directory_tree: str = "",
    modules: dict[str, ModuleDoc],
    commands: str = "",
    rules: str = "",
) -> str:
    """Assemble a complete CLAUDE.md from structured inputs.

    All formatting is controlled by this function — no AI decides the structure.
    """
    sections: list[str] = []

    # 1. Project header + overview
    sections.append(f"# {project_name}\n")
    if project_desc:
        sections.append(f"{project_desc}\n")

    # 2. Tech stack
    if tech_stack:
        sections.append(f"## 技术栈\n\n{tech_stack}\n")

    # 3. Common commands
    if commands:
        sections.append(f"## 常用命令\n\n{commands}\n")

    # 4. Project structure (directory tree)
    if directory_tree:
        sections.append(f"## 项目结构\n\n```\n{directory_tree}\n```\n")

    # 5. Module sections — ordered by MODULE_ORDER
    for category in MODULE_ORDER:
        if category not in modules:
            continue
        module = modules[category]
        if not module.snippets:
            continue

        sections.append(f"## {module.name}\n")

        # AI description (if available)
        if module.description:
            sections.append(f"{module.description}\n")

        # Code snippets (programmatically formatted)
        for snippet in module.snippets:
            snippet_section = _format_snippet(snippet)
            sections.append(snippet_section)

    # 6. Coding rules
    if rules:
        sections.append(f"## 编码规范\n\n{rules}\n")

    return "\n".join(sections).strip() + "\n"


def _format_snippet(snippet: CodeSnippet) -> str:
    """Format a single code snippet with filepath:line reference."""
    header = (
        f"`{snippet.filepath}:{snippet.start_line}-{snippet.end_line}` — `{snippet.name}`\n"
    )
    code_block = f"```{snippet.language}\n{snippet.code}\n```\n"
    return f"{header}\n{code_block}"


def build_directory_tree(
    work_dir: Path | str,
    max_depth: int = 4,
) -> str:
    """Build a directory tree string for the project.

    Reuses the skip dirs from scanner to exclude irrelevant directories.
    """
    from opd.engine.workspace.scanner import _SKIP_DIRS

    work_dir = Path(work_dir)
    if not work_dir.is_dir():
        return ""

    lines: list[str] = [f"{work_dir.name}/"]
    _walk_tree(work_dir, lines, depth=0, max_depth=max_depth, skip_dirs=_SKIP_DIRS)
    return "\n".join(lines)


def _walk_tree(
    directory: Path,
    lines: list[str],
    depth: int,
    max_depth: int,
    skip_dirs: set[str],
) -> None:
    """Recursively build directory tree lines."""
    if depth >= max_depth:
        return

    try:
        children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    except PermissionError:
        return

    for child in children:
        if child.name.startswith("."):
            continue
        indent = "  " * (depth + 1)
        if child.is_dir():
            if child.name in skip_dirs:
                continue
            lines.append(f"{indent}{child.name}/")
            _walk_tree(child, lines, depth + 1, max_depth, skip_dirs)
        else:
            lines.append(f"{indent}{child.name}")


def extract_commands(work_dir: Path | str) -> str:
    """Extract common commands from project build files.

    Scans pyproject.toml, package.json, and Makefile.
    """
    work_dir = Path(work_dir)
    parts: list[str] = []

    # Python: pyproject.toml
    pyproject = work_dir / "pyproject.toml"
    if pyproject.is_file():
        commands = _extract_pyproject_commands(pyproject)
        if commands:
            parts.append(commands)

    # Node: package.json
    package_json = work_dir / "package.json"
    if package_json.is_file():
        commands = _extract_package_json_commands(package_json)
        if commands:
            parts.append(commands)

    # Makefile
    makefile = work_dir / "Makefile"
    if makefile.is_file():
        commands = _extract_makefile_commands(makefile)
        if commands:
            parts.append(commands)

    return "\n\n".join(parts)


def _extract_pyproject_commands(filepath: Path) -> str:
    """Extract scripts section from pyproject.toml."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

    lines: list[str] = ["```bash"]

    # Look for [project.scripts] or [tool.poetry.scripts]
    in_scripts = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped in ("[project.scripts]", "[tool.poetry.scripts]"):
            in_scripts = True
            continue
        if in_scripts:
            if stripped.startswith("["):
                break
            if "=" in stripped:
                name, _, value = stripped.partition("=")
                lines.append(f"# {name.strip()}")
                lines.append(f"uv run {name.strip()}")

    # Common Python commands
    lines.extend([
        "# 安装依赖",
        "uv sync",
        "# 运行测试",
        "uv run pytest tests/",
        "# Lint 检查",
        "uv run ruff check .",
    ])
    lines.append("```")

    return "\n".join(lines)


def _extract_package_json_commands(filepath: Path) -> str:
    """Extract scripts section from package.json."""
    import json

    try:
        data = json.loads(filepath.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return ""

    scripts = data.get("scripts", {})
    if not scripts:
        return ""

    lines = ["```bash"]
    for name, cmd in scripts.items():
        lines.append(f"# {name}")
        lines.append(f"npm run {name}  # {cmd}")
    lines.append("```")

    return "\n".join(lines)


def _extract_makefile_commands(filepath: Path) -> str:
    """Extract target names from Makefile."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

    targets: list[str] = []
    for line in content.splitlines():
        if line and not line.startswith(("\t", " ", "#")) and ":" in line:
            target = line.split(":")[0].strip()
            if target and not target.startswith("."):
                targets.append(target)

    if not targets:
        return ""

    lines = ["```bash"]
    for t in targets[:15]:  # cap at 15 targets
        lines.append(f"make {t}")
    lines.append("```")

    return "\n".join(lines)
