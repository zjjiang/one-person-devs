"""Tests for opd.engine.memory.extractor — AST-based code snippet extraction."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from opd.engine.memory.extractor import (
    CodeSnippet,
    _categorize_file,
    _detect_language,
    _extract_generic_snippet,
    _extract_python_definitions,
    _rank_files_by_importance,
    extract_key_snippets,
)


# ── Helpers ─────────────────────────────────────────────────────────


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


# ── Tests: extract_key_snippets ─────────────────────────────────────


class TestExtractKeySnippets:
    """Integration tests for extract_key_snippets."""

    def test_empty_dir_returns_empty(self, tmp_path: Path):
        result = extract_key_snippets(tmp_path)
        assert result == []

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path):
        result = extract_key_snippets(tmp_path / "nonexistent")
        assert result == []

    def test_extracts_python_class(self, tmp_path: Path):
        _write(tmp_path / "engine" / "core.py", """\
            class Engine:
                def __init__(self, config):
                    self.config = config

                def run(self):
                    return True
        """)
        snippets = extract_key_snippets(tmp_path, max_snippets=10)
        assert len(snippets) >= 1
        names = [s.name for s in snippets]
        assert "Engine" in names

    def test_extracts_async_function(self, tmp_path: Path):
        _write(tmp_path / "api" / "routes.py", """\
            async def get_items(db):
                result = await db.execute("SELECT * FROM items")
                return result.all()
        """)
        snippets = extract_key_snippets(tmp_path, max_snippets=10)
        assert len(snippets) >= 1
        names = [s.name for s in snippets]
        assert "get_items" in names

    def test_skips_private_functions(self, tmp_path: Path):
        _write(tmp_path / "utils.py", """\
            def public_func():
                pass

            def _private_func():
                pass
        """)
        snippets = extract_key_snippets(tmp_path, max_snippets=10)
        names = [s.name for s in snippets]
        assert "public_func" in names
        assert "_private_func" not in names

    def test_keeps_dunder_methods(self, tmp_path: Path):
        _write(tmp_path / "engine" / "base.py", """\
            class Base:
                def __init__(self):
                    pass

                def __repr__(self):
                    return "Base()"
        """)
        snippets = extract_key_snippets(tmp_path, max_snippets=10)
        names = [s.name for s in snippets]
        assert "Base" in names

    def test_max_snippets_respected(self, tmp_path: Path):
        # Create many files
        for i in range(20):
            _write(tmp_path / f"module_{i}.py", f"""\
                class Class{i}:
                    pass

                def func_{i}():
                    pass
            """)
        snippets = extract_key_snippets(tmp_path, max_snippets=5)
        assert len(snippets) <= 5

    def test_generic_snippet_for_typescript(self, tmp_path: Path):
        _write(tmp_path / "web" / "src" / "App.tsx", """\
            import React from 'react';

            const App: React.FC = () => {
                return <div>Hello</div>;
            };

            export default App;
        """)
        snippets = extract_key_snippets(tmp_path, max_snippets=10)
        assert len(snippets) >= 1
        ts_snippets = [s for s in snippets if s.language == "typescript"]
        assert len(ts_snippets) >= 1

    def test_skips_node_modules(self, tmp_path: Path):
        _write(tmp_path / "node_modules" / "package" / "index.js", """\
            module.exports = {};
        """)
        _write(tmp_path / "src" / "main.py", """\
            def main():
                pass
        """)
        snippets = extract_key_snippets(tmp_path, max_snippets=10)
        for s in snippets:
            assert "node_modules" not in s.filepath

    def test_snippet_has_correct_fields(self, tmp_path: Path):
        _write(tmp_path / "api" / "handler.py", """\
            class Handler:
                def process(self, request):
                    return {"status": "ok"}
        """)
        snippets = extract_key_snippets(tmp_path, max_snippets=10)
        assert len(snippets) >= 1
        snippet = snippets[0]
        assert isinstance(snippet, CodeSnippet)
        assert snippet.filepath.endswith(".py")
        assert snippet.language == "python"
        assert snippet.start_line >= 1
        assert snippet.end_line >= snippet.start_line
        assert snippet.category == "api"
        assert len(snippet.code) > 0

    def test_syntax_error_python_falls_back(self, tmp_path: Path):
        """Python file with syntax error should not crash, falls back to generic."""
        _write(tmp_path / "broken.py", """\
            def broken(
                # missing closing paren and colon
                x
        """)
        snippets = extract_key_snippets(tmp_path, max_snippets=10)
        # Should still produce a snippet (generic fallback)
        broken = [s for s in snippets if "broken" in s.filepath]
        assert len(broken) >= 1

    def test_on_real_opd_project(self):
        """Run extraction on the OPD project itself — smoke test."""
        opd_root = Path(__file__).parent.parent
        if not (opd_root / "opd").is_dir():
            pytest.skip("OPD source not found")

        snippets = extract_key_snippets(opd_root, max_snippets=30)
        # Should extract at least 20 meaningful snippets
        assert len(snippets) >= 20

        # Should find key classes/functions from the project
        names = {s.name for s in snippets}
        # At least some well-known definitions should be present
        known_names = {
            "Orchestrator", "StateMachine", "create_app", "lifespan",
            "CodeSnippet", "Provider", "CapabilityRegistry",
            "TaskInfo", "StageContext", "CodingStage",
            "get_orchestrator", "create_project", "create_story",
        }
        found = names & known_names
        assert len(found) >= 2, f"Expected key names, found: {names}"

        # Should cover multiple categories
        categories = {s.category for s in snippets}
        assert len(categories) >= 3

        # All snippets should have code
        for s in snippets:
            assert len(s.code) > 0
            assert s.start_line >= 1


# ── Tests: _categorize_file ─────────────────────────────────────────


class TestCategorizeFile:
    def test_engine_dir(self):
        assert _categorize_file("opd/engine/orchestrator.py") == "engine"

    def test_api_dir(self):
        assert _categorize_file("opd/api/stories.py") == "api"

    def test_models_dir(self):
        assert _categorize_file("opd/db/models.py") == "model"

    def test_providers_dir(self):
        assert _categorize_file("opd/providers/ai/claude.py") == "provider"

    def test_frontend_dir(self):
        assert _categorize_file("web/src/App.tsx") == "frontend"

    def test_config_file(self):
        assert _categorize_file("config.py") == "config"

    def test_entry_file(self):
        assert _categorize_file("main.py") == "entry"

    def test_unknown(self):
        assert _categorize_file("random/stuff.py") == "other"


# ── Tests: _detect_language ──────────────────────────────────────────


class TestDetectLanguage:
    def test_python(self):
        assert _detect_language(Path("foo.py")) == "python"

    def test_typescript(self):
        assert _detect_language(Path("foo.ts")) == "typescript"

    def test_tsx(self):
        assert _detect_language(Path("foo.tsx")) == "typescript"

    def test_go(self):
        assert _detect_language(Path("foo.go")) == "go"

    def test_unknown(self):
        assert _detect_language(Path("foo.xyz")) == "text"


# ── Tests: _rank_files_by_importance ─────────────────────────────────


class TestRankFiles:
    def test_entry_file_ranks_highest(self, tmp_path: Path):
        main = _write(tmp_path / "main.py", "pass")
        util = _write(tmp_path / "utils.py", "pass")
        ranked = _rank_files_by_importance([util, main], tmp_path)
        # main.py should be first (higher score)
        assert ranked[0][0] == main

    def test_engine_dir_ranks_above_other(self, tmp_path: Path):
        engine_f = _write(tmp_path / "engine" / "core.py", "pass")
        other_f = _write(tmp_path / "misc" / "helper.py", "pass")
        ranked = _rank_files_by_importance([other_f, engine_f], tmp_path)
        assert ranked[0][0] == engine_f

    def test_test_files_deprioritized(self, tmp_path: Path):
        src = _write(tmp_path / "api" / "handler.py", "pass")
        test = _write(tmp_path / "api" / "test_handler.py", "pass")
        ranked = _rank_files_by_importance([test, src], tmp_path)
        assert ranked[0][0] == src


# ── Tests: _extract_python_definitions ───────────────────────────────


class TestExtractPythonDefinitions:
    def test_extracts_class_and_function(self, tmp_path: Path):
        f = _write(tmp_path / "module.py", """\
            class MyClass:
                def method(self):
                    pass

            def my_func():
                return 42
        """)
        snippets = _extract_python_definitions(f, "module.py", "python", "other", 30)
        names = [s.name for s in snippets]
        assert "MyClass" in names
        assert "my_func" in names

    def test_truncates_long_class(self, tmp_path: Path):
        lines = ["class Big:"] + [f"    x{i} = {i}" for i in range(100)]
        f = _write(tmp_path / "big.py", "\n".join(lines))
        snippets = _extract_python_definitions(f, "big.py", "python", "other", 30)
        assert len(snippets) == 1
        # Code should be truncated + have ellipsis
        assert "..." in snippets[0].code

    def test_syntax_error_returns_empty(self, tmp_path: Path):
        f = _write(tmp_path / "bad.py", "def broken(\n")
        snippets = _extract_python_definitions(f, "bad.py", "python", "other", 30)
        assert snippets == []


# ── Tests: _extract_generic_snippet ──────────────────────────────────


class TestExtractGenericSnippet:
    def test_reads_first_n_lines(self, tmp_path: Path):
        content = "\n".join(f"line {i}" for i in range(100))
        f = _write(tmp_path / "data.yaml", content)
        snippet = _extract_generic_snippet(f, "data.yaml", "yaml", "config", 10)
        assert snippet is not None
        assert snippet.end_line == 10
        assert "more lines" in snippet.code

    def test_empty_file_returns_none(self, tmp_path: Path):
        f = _write(tmp_path / "empty.txt", "")
        snippet = _extract_generic_snippet(f, "empty.txt", "text", "other", 30)
        assert snippet is None
