"""Tests for opd.engine.memory.assembler — programmatic CLAUDE.md assembly."""

from __future__ import annotations

import textwrap
from pathlib import Path

from opd.engine.memory.assembler import (
    _format_snippet,
    assemble_claude_md,
    build_directory_tree,
    extract_commands,
)
from opd.engine.memory.extractor import CodeSnippet
from opd.engine.memory.generator import ModuleDoc


# ── Helpers ─────────────────────────────────────────────────────────


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def _make_snippet(
    filepath: str = "opd/engine/core.py",
    name: str = "Engine",
    category: str = "engine",
    language: str = "python",
    code: str = "class Engine:\n    pass",
    start_line: int = 1,
    end_line: int = 2,
) -> CodeSnippet:
    return CodeSnippet(
        filepath=filepath,
        language=language,
        code=code,
        start_line=start_line,
        end_line=end_line,
        category=category,
        name=name,
    )


def _make_module(
    name: str = "核心引擎",
    category: str = "engine",
    description: str = "这是核心引擎模块。",
    snippets: list[CodeSnippet] | None = None,
) -> ModuleDoc:
    return ModuleDoc(
        name=name,
        category=category,
        description=description,
        snippets=snippets or [_make_snippet()],
    )


# ── Tests: assemble_claude_md ────────────────────────────────────────


class TestAssembleClaudeMd:
    """Tests for the main assembly function."""

    def test_basic_assembly(self):
        modules = {"engine": _make_module()}
        result = assemble_claude_md(
            project_name="TestProject",
            project_desc="A test project.",
            modules=modules,
        )
        assert "# TestProject" in result
        assert "A test project." in result
        assert "## 核心引擎" in result
        assert "这是核心引擎模块。" in result
        assert "```python" in result
        assert "class Engine:" in result

    def test_includes_tech_stack(self):
        result = assemble_claude_md(
            project_name="P",
            tech_stack="Python 3.11 + FastAPI",
            modules={},
        )
        assert "## 技术栈" in result
        assert "Python 3.11 + FastAPI" in result

    def test_includes_commands(self):
        result = assemble_claude_md(
            project_name="P",
            commands="```bash\npip install\n```",
            modules={},
        )
        assert "## 常用命令" in result
        assert "pip install" in result

    def test_includes_directory_tree(self):
        result = assemble_claude_md(
            project_name="P",
            directory_tree="project/\n  src/\n    main.py",
            modules={},
        )
        assert "## 项目结构" in result
        assert "project/" in result

    def test_includes_rules(self):
        result = assemble_claude_md(
            project_name="P",
            rules="- Always use type hints",
            modules={},
        )
        assert "## 编码规范" in result
        assert "Always use type hints" in result

    def test_multiple_modules_ordered(self):
        modules = {
            "api": _make_module(name="API 路由", category="api"),
            "engine": _make_module(name="核心引擎", category="engine"),
        }
        result = assemble_claude_md(project_name="P", modules=modules)
        # Engine should come before API based on MODULE_ORDER
        engine_pos = result.index("## 核心引擎")
        api_pos = result.index("## API 路由")
        assert engine_pos < api_pos

    def test_snippet_with_filepath_reference(self):
        snippet = _make_snippet(
            filepath="opd/engine/core.py",
            start_line=10,
            end_line=25,
            name="Engine",
        )
        modules = {"engine": _make_module(snippets=[snippet])}
        result = assemble_claude_md(project_name="P", modules=modules)
        assert "`opd/engine/core.py:10-25`" in result
        assert "`Engine`" in result

    def test_code_block_count_matches_snippets(self):
        snippets = [
            _make_snippet(name=f"Func{i}", start_line=i * 10, end_line=i * 10 + 5)
            for i in range(5)
        ]
        modules = {"engine": _make_module(snippets=snippets)}
        result = assemble_claude_md(project_name="P", modules=modules)
        # Each snippet should have opening + closing code fence
        code_fences = result.count("```python")
        assert code_fences == 5

    def test_module_without_description(self):
        modules = {"engine": _make_module(description="")}
        result = assemble_claude_md(project_name="P", modules=modules)
        assert "## 核心引擎" in result
        # Code should still be present
        assert "```python" in result

    def test_empty_modules_produces_minimal_doc(self):
        result = assemble_claude_md(project_name="P", modules={})
        assert "# P" in result
        # No module sections
        assert "## 核心引擎" not in result

    def test_no_conversational_artifacts(self):
        modules = {"engine": _make_module(description="模块说明。")}
        result = assemble_claude_md(project_name="P", modules=modules)
        # Should not contain any conversational patterns
        for pattern in ["我将", "让我", "首先", "I will", "Let me"]:
            assert pattern not in result


# ── Tests: _format_snippet ───────────────────────────────────────────


class TestFormatSnippet:
    def test_basic_format(self):
        snippet = _make_snippet(
            filepath="src/main.py", start_line=5, end_line=15,
            name="main", code="def main():\n    pass",
        )
        result = _format_snippet(snippet)
        assert "`src/main.py:5-15`" in result
        assert "`main`" in result
        assert "```python" in result
        assert "def main():" in result
        assert "```" in result


# ── Tests: build_directory_tree ──────────────────────────────────────


class TestBuildDirectoryTree:
    def test_basic_tree(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("pass")
        (tmp_path / "README.md").write_text("hi")

        tree = build_directory_tree(tmp_path, max_depth=3)
        assert tmp_path.name in tree
        assert "src/" in tree
        assert "main.py" in tree
        assert "README.md" in tree

    def test_skips_hidden_dirs(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("x")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("pass")

        tree = build_directory_tree(tmp_path, max_depth=3)
        assert ".git" not in tree
        assert "app.py" in tree

    def test_skips_node_modules(self, tmp_path: Path):
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg").mkdir()
        (tmp_path / "node_modules" / "pkg" / "index.js").write_text("x")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.ts").write_text("x")

        tree = build_directory_tree(tmp_path, max_depth=3)
        # Skip the root line (first line) which is the tmp_path dir name
        child_lines = tree.splitlines()[1:]
        for line in child_lines:
            assert "node_modules" not in line

    def test_nonexistent_dir(self, tmp_path: Path):
        tree = build_directory_tree(tmp_path / "nope")
        assert tree == ""

    def test_max_depth_respected(self, tmp_path: Path):
        deep = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text("pass")

        tree = build_directory_tree(tmp_path, max_depth=2)
        # Should not reach depth 5
        assert "deep.py" not in tree


# ── Tests: extract_commands ──────────────────────────────────────────


class TestExtractCommands:
    def test_pyproject_toml(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""\
            [project]
            name = "myapp"

            [project.scripts]
            serve = "myapp.main:serve"
            migrate = "myapp.db:migrate"
        """))
        commands = extract_commands(tmp_path)
        assert "uv run" in commands
        assert "pytest" in commands

    def test_package_json(self, tmp_path: Path):
        import json
        data = {
            "name": "myapp",
            "scripts": {
                "dev": "vite",
                "build": "tsc && vite build",
            },
        }
        (tmp_path / "package.json").write_text(json.dumps(data))
        commands = extract_commands(tmp_path)
        assert "npm run dev" in commands
        assert "npm run build" in commands

    def test_makefile(self, tmp_path: Path):
        (tmp_path / "Makefile").write_text(textwrap.dedent("""\
            build:
            \tgo build ./...

            test:
            \tgo test ./...
        """))
        commands = extract_commands(tmp_path)
        assert "make build" in commands
        assert "make test" in commands

    def test_empty_dir_returns_empty(self, tmp_path: Path):
        commands = extract_commands(tmp_path)
        assert commands == ""


# ── Tests: generator module ──────────────────────────────────────────


class TestGeneratorGrouping:
    """Tests for group_snippets_by_module."""

    def test_groups_by_category(self):
        from opd.engine.memory.generator import group_snippets_by_module

        snippets = [
            _make_snippet(category="engine", name="Engine"),
            _make_snippet(category="engine", name="StateMachine"),
            _make_snippet(category="api", name="get_stories"),
        ]
        modules = group_snippets_by_module(snippets)
        assert "engine" in modules
        assert "api" in modules
        assert len(modules["engine"].snippets) == 2
        assert len(modules["api"].snippets) == 1

    def test_order_follows_module_order(self):
        from opd.engine.memory.generator import group_snippets_by_module

        snippets = [
            _make_snippet(category="config", name="Config"),
            _make_snippet(category="engine", name="Engine"),
            _make_snippet(category="api", name="Handler"),
        ]
        modules = group_snippets_by_module(snippets)
        keys = list(modules.keys())
        assert keys.index("engine") < keys.index("api")
        assert keys.index("api") < keys.index("config")

    def test_empty_snippets(self):
        from opd.engine.memory.generator import group_snippets_by_module

        modules = group_snippets_by_module([])
        assert modules == {}

    def test_display_names(self):
        from opd.engine.memory.generator import group_snippets_by_module

        snippets = [_make_snippet(category="engine")]
        modules = group_snippets_by_module(snippets)
        assert modules["engine"].name == "核心引擎"


# ── Integration test: full pipeline ──────────────────────────────────


class TestFullPipeline:
    """End-to-end test: extract → group → assemble."""

    def test_extract_and_assemble(self, tmp_path: Path):
        from opd.engine.memory.extractor import extract_key_snippets
        from opd.engine.memory.generator import group_snippets_by_module

        # Create a mini project
        _write(tmp_path / "main.py", """\
            from engine import App

            def main():
                app = App()
                app.run()

            if __name__ == "__main__":
                main()
        """)
        _write(tmp_path / "engine" / "app.py", """\
            class App:
                def __init__(self):
                    self.running = False

                def run(self):
                    self.running = True
                    print("Running!")
        """)
        _write(tmp_path / "api" / "routes.py", """\
            async def get_status():
                return {"status": "ok"}

            async def post_action(data: dict):
                return {"result": "done"}
        """)

        # Extract
        snippets = extract_key_snippets(tmp_path, max_snippets=20)
        assert len(snippets) >= 3

        # Group
        modules = group_snippets_by_module(snippets)
        assert len(modules) >= 2

        # Add mock descriptions
        for mod in modules.values():
            mod.description = f"{mod.name}模块负责处理相关逻辑。"

        # Assemble
        result = assemble_claude_md(
            project_name="TestProject",
            project_desc="A test project",
            tech_stack="Python 3.11",
            directory_tree=build_directory_tree(tmp_path),
            modules=modules,
            commands="```bash\npython main.py\n```",
        )

        # Verify quality
        assert "# TestProject" in result
        assert "A test project" in result
        assert "## 技术栈" in result
        assert "## 项目结构" in result
        assert "## 常用命令" in result

        # Must have code blocks
        code_blocks = result.count("```python")
        assert code_blocks >= 3

        # Must have filepath:line references
        assert ":" in result  # filepath:line references
        assert "`" in result  # backtick-quoted names

        # No conversational artifacts
        for pattern in ["我将", "让我", "I will", "Let me"]:
            assert pattern not in result
