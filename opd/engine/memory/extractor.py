"""Code extractor: AST-based extraction of key code snippets from project source."""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from pathlib import Path

from opd.engine.workspace.scanner import _CODE_EXTS, _SKIP_DIRS

logger = logging.getLogger(__name__)

# Additional dirs to skip (project workspaces, docs archives, legacy code, etc.)
_EXTRA_SKIP_DIRS = {
    "workspace", "docs", "logs", "tmp", "temp", "coverage", "htmlcov",
    "_archived", "archived", "deprecated", "legacy", "old", "backup",
    "migrations", "alembic", "sqls",
}

# Max snippets per single file to avoid one file dominating the output
_MAX_SNIPPETS_PER_FILE = 5

# Additional extensions for generic snippet extraction
_GENERIC_EXTS = {".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".yaml", ".yml"}

# Importance scores by directory prefix
_DIR_IMPORTANCE: dict[str, int] = {
    "main": 100,
    "app": 100,
    "manage": 80,
    "engine": 50,
    "core": 50,
    "lib": 40,
    "api": 40,
    "routes": 40,
    "models": 30,
    "db": 30,
    "providers": 25,
    "capabilities": 25,
    "config": 20,
    "utils": 15,
    "helpers": 15,
    "middleware": 20,
    "services": 35,
    "controllers": 35,
    "components": 30,
    "pages": 25,
    "views": 25,
}

# Entry-point file names that get a bonus
_ENTRY_FILES = {
    "main.py", "app.py", "server.py", "manage.py", "wsgi.py", "asgi.py",
    "index.ts", "index.tsx", "index.js", "main.ts", "main.tsx", "main.go",
    "mod.rs", "lib.rs", "Main.java", "App.java",
}


@dataclass(frozen=True)
class CodeSnippet:
    """A code snippet extracted from project source."""

    filepath: str       # relative path from work_dir
    language: str       # python / typescript / javascript / go / ...
    code: str           # code text
    start_line: int
    end_line: int
    category: str       # engine / api / model / provider / frontend / config / other
    name: str           # class/function name or filename


def extract_key_snippets(
    work_dir: Path | str,
    max_snippets: int = 30,
    max_lines_per_snippet: int = 30,
) -> list[CodeSnippet]:
    """Extract key code snippets from a project workspace.

    Uses AST parsing for Python files, falls back to first N lines for others.
    Returns snippets sorted by importance.
    """
    work_dir = Path(work_dir)
    if not work_dir.is_dir():
        return []

    # Collect all candidate source files
    source_files = _collect_source_files(work_dir)
    if not source_files:
        return []

    # Rank files by importance
    ranked = _rank_files_by_importance(source_files, work_dir)

    # Two-pass extraction to ensure module diversity:
    # Pass 1: Take 1 snippet per file from ALL ranked files (ensures breadth)
    # Pass 2: Fill remaining slots with overflow (2nd-5th snippets per file)
    snippets: list[CodeSnippet] = []
    overflow: list[CodeSnippet] = []  # extras from pass 1

    for filepath, _score in ranked:
        rel_path = str(filepath.relative_to(work_dir))
        category = _categorize_file(rel_path)
        language = _detect_language(filepath)

        if filepath.suffix == ".py":
            extracted = _extract_python_definitions(
                filepath, rel_path, language, category, max_lines_per_snippet,
            )
            if extracted:
                # Take first 1 in pass 1, save rest for pass 2
                snippets.append(extracted[0])
                overflow.extend(extracted[1:_MAX_SNIPPETS_PER_FILE])
                continue

        # Non-Python or AST parse failure: use generic snippet
        snippet = _extract_generic_snippet(
            filepath, rel_path, language, category, max_lines_per_snippet,
        )
        if snippet:
            snippets.append(snippet)

    # Pass 2: fill remaining budget from overflow (by original rank order)
    for snippet in overflow:
        if len(snippets) >= max_snippets:
            break
        snippets.append(snippet)

    # Final truncation
    return snippets[:max_snippets]


def _collect_source_files(work_dir: Path) -> list[Path]:
    """Recursively collect source files, respecting skip dirs."""
    all_skip = _SKIP_DIRS | _EXTRA_SKIP_DIRS
    files: list[Path] = []

    def _walk(directory: Path, depth: int = 0) -> None:
        if depth > 8:
            return
        try:
            children = sorted(directory.iterdir())
        except PermissionError:
            return

        for child in children:
            if child.name.startswith(".") and child.name != ".env.example":
                continue
            if child.is_dir():
                if child.name in all_skip:
                    continue
                _walk(child, depth + 1)
            elif child.is_file() and child.suffix in _CODE_EXTS:
                files.append(child)

    _walk(work_dir)
    return files


def _rank_files_by_importance(
    files: list[Path], work_dir: Path,
) -> list[tuple[Path, int]]:
    """Rank files by importance heuristic. Higher = more important."""
    scored: list[tuple[Path, int]] = []
    for f in files:
        rel = f.relative_to(work_dir)
        parts = rel.parts
        score = 0

        # Entry-point file bonus
        if f.name in _ENTRY_FILES:
            score += 100

        # Directory-based scoring
        for part in parts[:-1]:  # directories only
            part_lower = part.lower()
            if part_lower in _DIR_IMPORTANCE:
                score += _DIR_IMPORTANCE[part_lower]

        # Top-level files get a small bonus
        if len(parts) <= 2:
            score += 10

        # __init__.py deprioritized (usually just imports)
        if f.name == "__init__.py":
            score -= 20

        # config/test files deprioritized
        if f.name.startswith("test_") or f.name.startswith("conftest"):
            score -= 30

        scored.append((f, score))

    # Sort by score descending, then by path for stability
    scored.sort(key=lambda x: (-x[1], str(x[0])))
    return scored


def _categorize_file(rel_path: str) -> str:
    """Categorize a file by its directory prefix."""
    parts = rel_path.lower().split("/")

    # Check directory parts
    for part in parts[:-1]:
        if part in ("engine", "core", "lib"):
            return "engine"
        if part in ("api", "routes", "controllers", "views"):
            return "api"
        if part in ("models", "db", "database", "schema"):
            return "model"
        if part in ("providers", "adapters", "integrations"):
            return "provider"
        if part in ("capabilities", "plugins"):
            return "capability"
        if part in ("web", "frontend", "client", "src", "components", "pages"):
            return "frontend"
        if part in ("config", "settings", "conf"):
            return "config"
        if part in ("stages",):
            return "stage"
        if part in ("middleware",):
            return "middleware"

    # Check filename for categorization
    filename = parts[-1]
    if filename in ("main.py", "app.py", "server.py", "wsgi.py", "asgi.py"):
        return "entry"
    if filename.startswith("config") or filename.startswith("settings"):
        return "config"

    return "other"


def _detect_language(filepath: Path) -> str:
    """Detect programming language from file extension."""
    ext_map = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".json": "json",
        ".sql": "sql",
    }
    return ext_map.get(filepath.suffix, "text")


def _extract_python_definitions(
    filepath: Path,
    rel_path: str,
    language: str,
    category: str,
    max_lines: int,
) -> list[CodeSnippet]:
    """Extract class and function definitions from a Python file using AST.

    Falls back to empty list if parsing fails (caller should use generic).
    """
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    source_lines = source.splitlines()
    snippets: list[CodeSnippet] = []

    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Skip private helpers that start with underscore (keep __init__, __call__ etc.)
        if node.name.startswith("_") and not node.name.startswith("__"):
            continue

        start = node.lineno - 1  # 0-indexed
        # Calculate end line: use end_lineno if available, otherwise estimate
        end = getattr(node, "end_lineno", start + max_lines)
        # Clip to max_lines
        if end - start > max_lines:
            end = start + max_lines

        code_text = "\n".join(source_lines[start:end])
        # Add ellipsis if truncated
        actual_end = getattr(node, "end_lineno", end)
        if actual_end > end:
            code_text += "\n    ..."

        snippets.append(CodeSnippet(
            filepath=rel_path,
            language=language,
            code=code_text,
            start_line=start + 1,  # back to 1-indexed
            end_line=min(end, len(source_lines)),
            category=category,
            name=node.name,
        ))

    return snippets


def _extract_generic_snippet(
    filepath: Path,
    rel_path: str,
    language: str,
    category: str,
    max_lines: int,
) -> CodeSnippet | None:
    """Extract first N lines of a non-Python file as a snippet."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    lines = source.splitlines()
    if not lines:
        return None

    snippet_lines = lines[:max_lines]
    code_text = "\n".join(snippet_lines)
    if len(lines) > max_lines:
        code_text += f"\n// ... ({len(lines) - max_lines} more lines)"

    return CodeSnippet(
        filepath=rel_path,
        language=language,
        code=code_text,
        start_line=1,
        end_line=min(max_lines, len(lines)),
        category=category,
        name=filepath.stem,
    )
