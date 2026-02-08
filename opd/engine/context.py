"""Context builders for AI prompts.

Assembles the three-layer context hierarchy (Project -> Story -> Round)
into prompt strings that are fed to the AI provider.
"""

from __future__ import annotations

from opd.db.models import Clarification, Project, Round, Rule, Story


def _rules_block(rules: list[Rule]) -> str:
    """Format project rules into a prompt section."""
    if not rules:
        return ""
    lines: list[str] = ["## Project Rules", ""]
    for rule in rules:
        if not rule.enabled:
            continue
        lines.append(f"- [{rule.category.value}] {rule.content}")
    lines.append("")
    return "\n".join(lines)


def build_system_prompt(project: Project, rules: list[Rule]) -> str:
    """Build the system-level prompt with project context and rules.

    Parameters
    ----------
    project:
        The project ORM instance.
    rules:
        The list of Rule ORM instances for this project.
    """
    parts: list[str] = [
        "You are an expert software engineer working on the following project.",
        "",
        f"# Project: {project.name}",
        "",
    ]
    if project.description:
        parts.append(f"## Description\n{project.description}\n")
    if project.tech_stack:
        parts.append(f"## Tech Stack\n{project.tech_stack}\n")
    if project.architecture:
        parts.append(f"## Architecture\n{project.architecture}\n")

    rules_text = _rules_block(rules)
    if rules_text:
        parts.append(rules_text)

    parts.append(
        "Follow the project rules strictly. "
        "Write clean, well-tested code that matches the existing style."
    )
    return "\n".join(parts)


def _clarifications_block(clarifications: list[Clarification]) -> str:
    """Format clarification Q&A pairs into a prompt section."""
    if not clarifications:
        return ""
    lines: list[str] = ["## Clarifications", ""]
    for c in clarifications:
        lines.append(f"**Q:** {c.question}")
        lines.append(f"**A:** {c.answer or '(not yet answered)'}")
        lines.append("")
    return "\n".join(lines)


def _story_block(story: Story) -> str:
    """Format the story requirement into a prompt section."""
    parts: list[str] = [
        f"# Story: {story.title}",
        "",
        "## Requirement",
        story.requirement,
        "",
    ]
    if story.acceptance_criteria:
        parts.append(f"## Acceptance Criteria\n{story.acceptance_criteria}\n")
    return "\n".join(parts)


def _round_block(round_: Round) -> str:
    """Format round metadata into a prompt section."""
    parts: list[str] = [
        f"# Round #{round_.round_number} (type: {round_.type.value})",
        "",
    ]
    if round_.requirement_snapshot:
        parts.append(
            f"## Requirement Snapshot\n{round_.requirement_snapshot}\n"
        )
    return "\n".join(parts)


def build_plan_prompt(
    project: Project,
    story: Story,
    round_: Round,
) -> str:
    """Build a prompt asking the AI to produce an implementation plan.

    The AI should return a structured plan with file changes, new files,
    and a brief description of each step.
    """
    parts: list[str] = [
        _story_block(story),
        _round_block(round_),
        _clarifications_block(list(round_.clarifications)),
        "## Instructions",
        "",
        "Analyze the requirement and produce a detailed implementation plan.",
        "For each step, specify:",
        "1. Which files to create or modify",
        "2. A brief description of the changes",
        "3. Any dependencies between steps",
        "",
        "Return the plan as a structured markdown document.",
    ]
    return "\n".join(parts)


def build_coding_prompt(
    project: Project,
    story: Story,
    round_: Round,
    clarifications: list[Clarification],
) -> str:
    """Build the prompt for the main coding task.

    Includes the full three-layer context: project info, story requirement,
    round details, and any clarification Q&A.
    """
    parts: list[str] = [
        _story_block(story),
        _round_block(round_),
        _clarifications_block(clarifications),
        "## Instructions",
        "",
        "Implement the requirement described above.",
        "Make sure to:",
        "- Follow the project rules and coding conventions",
        "- Write tests for new functionality",
        "- Keep changes minimal and focused on the requirement",
        "- Commit with clear, descriptive messages",
    ]
    return "\n".join(parts)


def build_revision_prompt(
    project: Project,
    story: Story,
    round_: Round,
    feedback: str,
) -> str:
    """Build the prompt for a revision pass.

    Parameters
    ----------
    feedback:
        Either review comments from the SCM provider or a free-form
        prompt from the user.
    """
    parts: list[str] = [
        _story_block(story),
        _round_block(round_),
        "## Review Feedback",
        "",
        feedback,
        "",
        "## Instructions",
        "",
        "Address the review feedback above.",
        "Make targeted changes to resolve each comment.",
        "Do not introduce unrelated changes.",
    ]
    return "\n".join(parts)
