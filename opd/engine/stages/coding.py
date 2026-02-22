"""Coding stage: AI writes code based on detailed design."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from opd.db.models import StoryStatus
from opd.engine.context import build_coding_prompt
from opd.engine.stages.base import Stage, StageContext, StageResult
from opd.engine.workspace import read_doc, resolve_work_dir

logger = logging.getLogger(__name__)


def _build_coding_report(
    story_title: str,
    round_number: int,
    branch_name: str | None,
    repo_url: str | None,
    pr_urls: list[str],
    assistant_msgs: list[str],
    tool_msgs: list[str],
) -> str:
    """Build a markdown coding report from collected AI messages."""
    lines: list[str] = []
    lines.append(f"# 编码报告: {story_title}")
    lines.append("")

    # ── 交付说明 ──
    lines.append("## 交付说明")
    lines.append("")
    lines.append("| 项目 | 内容 |")
    lines.append("|------|------|")
    lines.append(f"| 轮次 | {round_number} |")
    if branch_name and repo_url:
        base_url = repo_url.rstrip("/").removesuffix(".git")
        branch_link = f"[{branch_name}]({base_url}/tree/{branch_name})"
        lines.append(f"| 代码分支 | {branch_link} |")
    elif branch_name:
        lines.append(f"| 代码分支 | `{branch_name}` |")
    else:
        lines.append("| 代码分支 | ⚠️ 未创建 |")
    for url in pr_urls:
        lines.append(f"| Pull Request | {url} |")
    lines.append(
        f"| 生成时间 | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} |"
    )
    lines.append("")

    # ── AI 编码摘要 ──
    lines.append("## AI 编码摘要")
    lines.append("")
    if assistant_msgs:
        for msg in assistant_msgs:
            lines.append(msg.strip())
            lines.append("")
    else:
        lines.append("_无 assistant 消息_")
        lines.append("")

    # ── 工具调用记录 (last 20, truncated) ──
    if tool_msgs:
        lines.append("## 工具调用记录")
        lines.append("")
        for msg in tool_msgs[-20:]:
            truncated = msg[:200] + "..." if len(msg) > 200 else msg
            lines.append(f"- {truncated}")
        lines.append("")

    return "\n".join(lines)


def _build_test_guide(
    story_title: str,
    branch_name: str | None,
    repo_url: str | None,
    assistant_msgs: list[str],
) -> str:
    """Build a test guide from coding output."""
    lines: list[str] = []
    lines.append(f"# 测试指南: {story_title}")
    lines.append("")

    # ── 代码获取 ──
    lines.append("## 代码获取")
    lines.append("")
    if branch_name:
        lines.append("```bash")
        lines.append(f"git fetch origin {branch_name}")
        lines.append(f"git checkout {branch_name}")
        lines.append("```")
    else:
        lines.append("⚠️ 未创建代码分支，请确认代码位置。")
    lines.append("")

    # ── 变更说明 (from last assistant message) ──
    lines.append("## 变更说明")
    lines.append("")
    if assistant_msgs:
        lines.append(assistant_msgs[-1].strip())
    else:
        lines.append("_AI 未输出变更说明_")
    lines.append("")

    lines.append("## 验证步骤")
    lines.append("")
    lines.append("请根据以上变更说明，按以下步骤验证：")
    lines.append("")
    lines.append("1. 拉取代码分支并本地运行")
    lines.append("2. 验证主要功能是否正常")
    lines.append("3. 检查边界情况和异常处理")
    lines.append("4. 确认无回归问题")
    lines.append("")

    return "\n".join(lines)


class CodingStage(Stage):
    """Execute AI coding based on the detailed design."""

    required_capabilities = ["ai", "scm"]

    async def validate_preconditions(self, ctx: StageContext) -> list[str]:
        errors: list[str] = []
        if not ctx.story.detailed_design:
            errors.append("Story detailed_design is required for coding")
        return errors

    async def execute(self, ctx: StageContext) -> StageResult:
        ai = ctx.capabilities.get("ai")
        if not ai:
            return StageResult(success=False, errors=["AI capability not available"])

        dd = ctx.story.detailed_design or ""
        if dd.startswith("docs/"):
            file_content = read_doc(ctx.project, ctx.story, "detailed_design.md")
            if file_content:
                dd = file_content

        system_prompt, user_prompt = build_coding_prompt(
            ctx.story, ctx.project, ctx.round,
        )

        work_dir = str(resolve_work_dir(ctx.project))

        collected: list[str] = []
        tool_msgs: list[str] = []
        async for msg in ai.provider.code(system_prompt, user_prompt, work_dir):
            if ctx.publish:
                await ctx.publish(msg)
            msg_type = msg.get("type", "")
            if msg_type == "assistant":
                collected.append(msg["content"])
            elif msg_type == "tool":
                tool_msgs.append(msg.get("content", ""))

        branch_name = ctx.round.branch_name if ctx.round else None
        repo_url = ctx.project.repo_url if ctx.project else None
        # PRs don't exist yet during coding — avoid lazy-loading the relationship
        pr_urls: list[str] = []
        report = _build_coding_report(
            story_title=ctx.story.title,
            round_number=ctx.round.round_number if ctx.round else 0,
            branch_name=branch_name,
            repo_url=repo_url,
            pr_urls=pr_urls,
            assistant_msgs=collected,
            tool_msgs=tool_msgs,
        )
        test_guide = _build_test_guide(
            story_title=ctx.story.title,
            branch_name=branch_name,
            repo_url=repo_url,
            assistant_msgs=collected,
        )

        return StageResult(
            success=True,
            output={"coding_report": report, "test_guide": test_guide},
            next_status=StoryStatus.verifying,
        )

    async def validate_output(self, result: StageResult) -> list[str]:
        errors: list[str] = []
        if "coding_report" not in result.output:
            errors.append("Stage output missing 'coding_report'")
        if "test_guide" not in result.output:
            errors.append("Stage output missing 'test_guide'")
        return errors
