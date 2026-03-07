"""Memory module: programmatic CLAUDE.md generation with AST extraction + AI descriptions."""

from opd.engine.memory.assembler import assemble_claude_md
from opd.engine.memory.extractor import CodeSnippet, extract_key_snippets
from opd.engine.memory.generator import ModuleDoc, generate_module_description, group_snippets_by_module

__all__ = [
    "CodeSnippet",
    "ModuleDoc",
    "assemble_claude_md",
    "extract_key_snippets",
    "generate_module_description",
    "group_snippets_by_module",
]
