"""Module generator: group snippets by module and generate AI descriptions."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from opd.engine.memory.extractor import CodeSnippet

logger = logging.getLogger(__name__)

# Module mapping: category → display name
MODULE_DISPLAY_NAMES: dict[str, str] = {
    "entry": "入口与启动",
    "engine": "核心引擎",
    "api": "API 路由",
    "model": "数据模型",
    "provider": "Provider 系统",
    "capability": "Capability 系统",
    "stage": "阶段实现",
    "middleware": "中间件",
    "frontend": "前端",
    "config": "配置",
    "other": "其他模块",
}

# Module display order
MODULE_ORDER: list[str] = [
    "entry", "engine", "stage", "api", "model",
    "provider", "capability", "middleware",
    "frontend", "config", "other",
]


@dataclass
class ModuleDoc:
    """Documentation for a single module."""

    name: str                               # display name
    category: str                           # category key
    description: str = ""                   # AI-generated description
    snippets: list[CodeSnippet] = field(default_factory=list)


def group_snippets_by_module(snippets: list[CodeSnippet]) -> dict[str, ModuleDoc]:
    """Group code snippets by module category.

    Returns an ordered dict of ModuleDoc keyed by category.
    Empty modules are excluded.
    """
    groups: dict[str, list[CodeSnippet]] = defaultdict(list)
    for snippet in snippets:
        groups[snippet.category].append(snippet)

    result: dict[str, ModuleDoc] = {}
    for category in MODULE_ORDER:
        if category not in groups:
            continue
        display_name = MODULE_DISPLAY_NAMES.get(category, category)
        result[category] = ModuleDoc(
            name=display_name,
            category=category,
            snippets=groups[category],
        )

    return result


def _build_module_prompt(module_name: str, snippets: list[CodeSnippet]) -> str:
    """Build a user prompt containing snippets for AI to describe a module."""
    parts = [f"模块名称: {module_name}\n\n以下是该模块的关键代码片段：\n"]

    for snippet in snippets:
        parts.append(
            f"### `{snippet.filepath}:{snippet.start_line}-{snippet.end_line}` — `{snippet.name}`\n"
            f"```{snippet.language}\n{snippet.code}\n```\n"
        )

    return "\n".join(parts)


_MODULE_SYSTEM_PROMPT = (
    "你是一个资深工程师。根据提供的代码片段，为这个模块写一段说明。\n"
    "要求：\n"
    "- 写 2-3 段文字，说明模块职责和设计决策\n"
    "- 说明模块内各组件的关系\n"
    "- 指出需要注意的陷阱或约定\n"
    "- 不要重复代码（代码已经在文档中了）\n"
    "- 直接输出文字，不要输出对话内容（如「我将...」「让我...」）\n"
    "- 不要用 markdown 代码块包裹输出\n"
    "- 使用中文"
)


async def generate_module_description(
    ai_cap,
    module_name: str,
    snippets: list[CodeSnippet],
    work_dir: str,
) -> str:
    """Call AI to generate a 2-3 paragraph description for a module.

    Uses max_turns=8 for focused, cheap generation.
    Falls back to empty string if AI fails.
    """
    user_prompt = _build_module_prompt(module_name, snippets)

    collected: list[str] = []
    try:
        async for msg in ai_cap.provider.plan(
            _MODULE_SYSTEM_PROMPT, user_prompt, work_dir, max_turns=8,
        ):
            if msg.get("type") == "assistant" and msg.get("content"):
                content = msg["content"].strip()
                if content:
                    collected.append(content)
    except Exception:
        logger.exception("AI module description generation failed for %s", module_name)
        return ""

    result = "\n\n".join(collected).strip()

    # Basic sanity filter: reject if it looks like conversational garbage
    _CONVERSATION_PREFIXES = ("我将", "让我", "首先我", "I will", "Let me", "I'll")
    if result and result.startswith(_CONVERSATION_PREFIXES):
        # Try to salvage: skip the first line
        lines = result.split("\n", 1)
        result = lines[1].strip() if len(lines) > 1 else ""

    return result
