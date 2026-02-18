"""AI context/prompt builder for each stage."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from opd.engine.workspace import read_doc

if TYPE_CHECKING:
    from opd.db.models import Project, Round, Story

logger = logging.getLogger(__name__)

# Marker that AI should output at the end of a complete document.
# Used to detect truncation and trigger continuation.
COMPLETION_MARKER = "<!-- DOCUMENT_COMPLETE -->"

_COMPLETION_INSTRUCTION = (
    f"\n\n重要：文档全部输出完成后，必须在最后单独一行输出 `{COMPLETION_MARKER}` 标记。"
    "这个标记用于确认文档已完整输出，不要遗漏。"
)


def _resolve_doc(story: Story, project: Project, field: str, filename: str) -> str:
    """Resolve a doc field: if it looks like a path, read from file; otherwise return as-is."""
    value = getattr(story, field, None) or ""
    if value.startswith("docs/"):
        content = read_doc(project, story, filename)
        if content is None:
            logger.warning("Doc file not found: %s for story %s", filename, story.id)
            return ""
        return content
    return value


def _rules_block(project: Project) -> str:
    rules = [r for r in (project.rules or []) if r.enabled]
    if not rules:
        return ""
    lines = []
    for r in rules:
        lines.append(f"- [{r.category.value}] {r.content}")
    return "## 项目规则\n" + "\n".join(lines)


def _clarifications_block(story: Story) -> str:
    if not story.clarifications:
        return ""
    lines = []
    for c in story.clarifications:
        lines.append(f"Q: {c.question}")
        if c.answer:
            lines.append(f"A: {c.answer}")
    return "## 需求澄清记录\n" + "\n".join(lines)


def _tasks_block(story: Story) -> str:
    if not story.tasks:
        return ""
    lines = []
    for t in story.tasks:
        deps = f" (依赖: {t.depends_on})" if t.depends_on else ""
        lines.append(f"- Task {t.order}: {t.title}{deps}\n  {t.description}")
    return "## Task 列表\n" + "\n".join(lines)


def build_project_context(project: Project) -> str:
    """Build project-level context for AI prompts."""
    sections = [f"## 项目: {project.name}"]
    if project.description:
        sections.append(f"描述: {project.description}")
    if project.tech_stack:
        sections.append(f"## 技术栈\n{project.tech_stack}")
    if project.architecture:
        sections.append(f"## 架构\n{project.architecture}")
    rules = _rules_block(project)
    if rules:
        sections.append(rules)
    return "\n\n".join(sections)


def build_preparing_prompt(story: Story, project: Project) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for PRD generation."""
    system = (
        "你是一个资深产品经理助理。根据用户提供的原始需求输入，生成一份结构化的 PRD 文档。\n"
        "PRD 应包含：需求背景、功能描述、验收标准、边界条件。\n"
        "使用 Markdown 格式输出。\n\n"
        + build_project_context(project)
    )
    user = f"请根据以下原始需求生成 PRD：\n\n{story.raw_input}"
    return system, user


def build_clarifying_prompt(
    story: Story, project: Project, source_context: str = "",
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for requirement clarification."""
    system = (
        "你是一个资深研发工程师。分析以下 PRD，基于你对当前系统的理解，"
        "提出需要澄清的问题。每个问题应该帮助明确需求的边界和实现细节。\n"
        "以 JSON 数组格式输出问题列表：[{\"question\": \"...\"}]\n\n"
        + build_project_context(project)
    )
    user = f"## PRD\n{_resolve_doc(story, project, 'prd', 'prd.md')}"
    clarifications = _clarifications_block(story)
    if clarifications:
        user += f"\n\n{clarifications}"
    if source_context:
        user += f"\n\n{source_context}"
    return system, user


def build_planning_prompt(story: Story, project: Project) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for technical design + task breakdown."""
    system = (
        "你是一个资深架构师。根据确认后的 PRD，完成以下两项工作：\n"
        "1. 概要设计：整体技术方案，包括架构变更、数据模型变更、接口变更\n"
        "2. Task 拆分：将方案拆分为可执行的 Task，标注依赖关系\n\n"
        "输出格式：先输出概要设计（Markdown），然后输出 Task 列表（JSON 数组）：\n"
        '[{"title": "...", "description": "...", "scope": "...", '
        '"acceptance_criteria": "...", "order": 1, "depends_on": []}]\n\n'
        + build_project_context(project)
        + _COMPLETION_INSTRUCTION
    )
    user = f"## 确认后的 PRD\n{_resolve_doc(story, project, 'confirmed_prd', 'prd.md') or _resolve_doc(story, project, 'prd', 'prd.md')}"
    return system, user


def build_designing_prompt(story: Story, project: Project) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for detailed design."""
    system = (
        "你是一个高级开发者。根据概要设计和 Task 列表，生成一份详细设计文档。\n"
        "详细设计应覆盖所有 Task 的实现细节，包括：改哪些文件、每个文件的改动说明。\n"
        "使用 Markdown 格式输出。\n\n"
        + build_project_context(project)
        + _COMPLETION_INSTRUCTION
    )
    tasks = _tasks_block(story)
    user = f"## 概要设计\n{_resolve_doc(story, project, 'technical_design', 'technical_design.md')}\n\n{tasks}"
    return system, user


def build_coding_prompt(story: Story, project: Project, round_: Round) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for AI coding."""
    system = (
        "你是一个资深开发者。根据详细设计文档，按照 Task 顺序编写代码。\n"
        "严格按照设计文档实现，不要添加额外功能。\n\n"
        + build_project_context(project)
    )
    user = f"## 详细设计\n{_resolve_doc(story, project, 'detailed_design', 'detailed_design.md')}"
    tasks = _tasks_block(story)
    if tasks:
        user += f"\n\n{tasks}"
    # Add round context for iterate/restart
    if round_.type.value == "iterate" and round_.close_reason:
        user += f"\n\n## 上一轮 Review 意见\n{round_.close_reason}\n请根据以上意见修改代码。"
    elif round_.type.value == "restart" and round_.close_reason:
        user += f"\n\n## 上一轮失败原因\n{round_.close_reason}\n请避免重蹈覆辙。"
    return system, user


def build_continuation_prompt(output_so_far: str, tail_chars: int = 500) -> str:
    """Build a user prompt asking AI to continue from where it was truncated."""
    tail = output_so_far[-tail_chars:]
    return (
        "你的上一次输出被截断了，请从截断处继续输出（不要重复已输出的内容）。\n\n"
        f"---上次输出的末尾---\n{tail}\n---\n\n"
        f"请继续输出剩余内容。完成后在最后单独一行输出 `{COMPLETION_MARKER}` 标记。"
    )


def is_output_complete(text: str) -> bool:
    """Check if AI output contains the completion marker."""
    return COMPLETION_MARKER in text


def strip_completion_marker(text: str) -> str:
    """Remove the completion marker from final output."""
    return text.replace(COMPLETION_MARKER, "").rstrip()


# ---------------------------------------------------------------------------
# Document refinement (chat-based)
# ---------------------------------------------------------------------------

_REFINE_FORMAT_INSTRUCTION = (
    "\n\n你的回复必须使用以下格式：\n"
    "<discussion>\n你的讨论回复内容（限 2-3 句简短回复，不要输出大段内容）\n</discussion>\n\n"
    "<updated_doc>\n（仅当文档需要修改时才包含此块）\n完整的更新后文档 markdown\n</updated_doc>\n\n"
    "重要：\n"
    "- discussion 部分只做简短对话回复（2-3 句话），不要在其中输出文档内容或大段分析。\n"
    "- 如果文档不需要修改，只输出 <discussion> 块即可。\n"
    "- 如果需要修改文档，<updated_doc> 中必须包含完整的文档内容（不是增量）。"
)


def _history_block(history: list[dict]) -> str:
    if not history:
        return ""
    lines = []
    for m in history:
        role = "用户" if m["role"] == "user" else "AI"
        lines.append(f"{role}: {m['content']}")
    return "## 对话历史\n" + "\n".join(lines)


def build_refine_prd_prompt(
    story: Story,
    project: Project,
    history: list[dict],
    user_message: str,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for chat-based PRD refinement in preparing stage."""
    system = (
        "你是一个资深产品经理助理。你正在和用户讨论并完善一份 PRD 文档。\n"
        "用户可能会提出修改意见、提问、或要求调整 PRD 的某些部分。\n"
        + _REFINE_FORMAT_INSTRUCTION + "\n\n"
        + build_project_context(project)
    )
    prd_content = _resolve_doc(story, project, "prd", "prd.md") or "（尚未生成）"
    parts = [f"## 当前 PRD\n{prd_content}"]
    hb = _history_block(history)
    if hb:
        parts.append(hb)
    parts.append(f"## 用户新消息\n{user_message}")
    return system, "\n\n".join(parts)


def build_clarifying_chat_prompt(
    story: Story,
    project: Project,
    history: list[dict],
    user_message: str,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for chat-based discussion in clarifying stage."""
    system = (
        "你是一个资深研发工程师。你正在和用户讨论需求 PRD，帮助澄清需求边界和实现细节。\n"
        "基于你对项目的理解，分析 PRD 中可能存在的模糊点，提出建议或回答用户的问题。\n"
        "如果讨论中发现 PRD 需要修改，请输出更新后的完整 PRD。\n"
        + _REFINE_FORMAT_INSTRUCTION + "\n\n"
        + build_project_context(project)
    )
    prd_content = _resolve_doc(story, project, "prd", "prd.md") or "（尚未生成）"
    parts = [f"## 当前 PRD\n{prd_content}"]
    clarifications = _clarifications_block(story)
    if clarifications:
        parts.append(clarifications)
    hb = _history_block(history)
    if hb:
        parts.append(hb)
    parts.append(f"## 用户新消息\n{user_message}")
    return system, "\n\n".join(parts)


def build_planning_chat_prompt(
    story: Story,
    project: Project,
    history: list[dict],
    user_message: str,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for chat-based technical design refinement."""
    system = (
        "你是一个资深架构师。你正在和用户讨论并完善技术方案文档。\n"
        "用户可能会提出修改意见、提问、或要求调整技术方案的某些部分。\n"
        + _REFINE_FORMAT_INSTRUCTION + "\n\n"
        + build_project_context(project)
    )
    td_content = _resolve_doc(story, project, "technical_design", "technical_design.md") or "（尚未生成）"
    prd_content = _resolve_doc(story, project, "confirmed_prd", "prd.md") or _resolve_doc(
        story, project, "prd", "prd.md"
    )
    parts = [f"## 确认后的 PRD\n{prd_content}", f"## 当前技术方案\n{td_content}"]
    tasks = _tasks_block(story)
    if tasks:
        parts.append(tasks)
    hb = _history_block(history)
    if hb:
        parts.append(hb)
    parts.append(f"## 用户新消息\n{user_message}")
    return system, "\n\n".join(parts)


def build_designing_chat_prompt(
    story: Story,
    project: Project,
    history: list[dict],
    user_message: str,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for chat-based detailed design refinement."""
    system = (
        "你是一个高级开发者。你正在和用户讨论并完善详细设计文档。\n"
        "用户可能会提出修改意见、提问、或要求调整详细设计的某些部分。\n"
        + _REFINE_FORMAT_INSTRUCTION + "\n\n"
        + build_project_context(project)
    )
    dd_content = _resolve_doc(story, project, "detailed_design", "detailed_design.md") or "（尚未生成）"
    td_content = _resolve_doc(story, project, "technical_design", "technical_design.md") or ""
    parts = []
    if td_content:
        parts.append(f"## 技术方案\n{td_content}")
    parts.append(f"## 当前详细设计\n{dd_content}")
    tasks = _tasks_block(story)
    if tasks:
        parts.append(tasks)
    hb = _history_block(history)
    if hb:
        parts.append(hb)
    parts.append(f"## 用户新消息\n{user_message}")
    return system, "\n\n".join(parts)


def parse_refine_response(full_text: str) -> tuple[str, str | None]:
    """Parse AI refinement response into (discussion, updated_doc_or_none)."""
    discussion = ""
    updated_doc = None

    disc_match = re.search(r"<discussion>(.*?)</discussion>", full_text, re.DOTALL)
    if disc_match:
        discussion = disc_match.group(1).strip()
    else:
        # Fallback: strip updated_doc blocks, take remaining as discussion
        discussion = re.sub(
            r"<updated_(?:doc|prd)>.*?</updated_(?:doc|prd)>", "", full_text, flags=re.DOTALL,
        ).strip()
        # Safety: if no tags were used and discussion is too long, truncate to first few sentences
        if len(discussion) > 500:
            sentences = re.split(r'(?<=[。！？.!?])\s*', discussion)
            truncated = ""
            for s in sentences[:3]:
                truncated += s
                if len(truncated) > 200:
                    break
            discussion = truncated.strip() if truncated.strip() else discussion[:300] + "..."

    # Support both <updated_doc> (new) and <updated_prd> (legacy)
    doc_match = re.search(r"<updated_doc>(.*?)</updated_doc>", full_text, re.DOTALL)
    if not doc_match:
        doc_match = re.search(r"<updated_prd>(.*?)</updated_prd>", full_text, re.DOTALL)
    if doc_match:
        updated_doc = doc_match.group(1).strip()

    return discussion, updated_doc
