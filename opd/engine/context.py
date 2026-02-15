"""AI context/prompt builder for each stage."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opd.db.models import Project, Round, Story


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


def build_clarifying_prompt(story: Story, project: Project) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for requirement clarification."""
    system = (
        "你是一个资深研发工程师。分析以下 PRD，基于你对当前系统的理解，"
        "提出需要澄清的问题。每个问题应该帮助明确需求的边界和实现细节。\n"
        "以 JSON 数组格式输出问题列表：[{\"question\": \"...\"}]\n\n"
        + build_project_context(project)
    )
    user = f"## PRD\n{story.prd}"
    clarifications = _clarifications_block(story)
    if clarifications:
        user += f"\n\n{clarifications}"
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
    )
    user = f"## 确认后的 PRD\n{story.confirmed_prd or story.prd}"
    return system, user


def build_designing_prompt(story: Story, project: Project) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for detailed design."""
    system = (
        "你是一个高级开发者。根据概要设计和 Task 列表，生成一份详细设计文档。\n"
        "详细设计应覆盖所有 Task 的实现细节，包括：改哪些文件、每个文件的改动说明。\n"
        "使用 Markdown 格式输出。\n\n"
        + build_project_context(project)
    )
    tasks = _tasks_block(story)
    user = f"## 概要设计\n{story.technical_design}\n\n{tasks}"
    return system, user


def build_coding_prompt(story: Story, project: Project, round_: Round) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for AI coding."""
    system = (
        "你是一个资深开发者。根据详细设计文档，按照 Task 顺序编写代码。\n"
        "严格按照设计文档实现，不要添加额外功能。\n\n"
        + build_project_context(project)
    )
    user = f"## 详细设计\n{story.detailed_design}"
    tasks = _tasks_block(story)
    if tasks:
        user += f"\n\n{tasks}"
    # Add round context for iterate/restart
    if round_.type.value == "iterate" and round_.close_reason:
        user += f"\n\n## 上一轮 Review 意见\n{round_.close_reason}\n请根据以上意见修改代码。"
    elif round_.type.value == "restart" and round_.close_reason:
        user += f"\n\n## 上一轮失败原因\n{round_.close_reason}\n请避免重蹈覆辙。"
    return system, user
