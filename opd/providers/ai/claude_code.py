"""Claude Code AI provider using claude-code-sdk."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import AsyncIterator
from typing import Any

from opd.providers.ai.base import AIProvider

logger = logging.getLogger(__name__)

try:
    from claude_code_sdk import (
        AssistantMessage,
        ClaudeCodeOptions,
        ResultMessage,
        TextBlock,
        ToolUseBlock,
        query,
    )

    _HAS_SDK = True
except ImportError:  # pragma: no cover
    _HAS_SDK = False


def _require_sdk() -> None:
    if not _HAS_SDK:
        raise RuntimeError(
            "claude-code-sdk is required for ClaudeCodeAIProvider. "
            "Install it with: pip install claude-code-sdk"
        )


# ------------------------------------------------------------------
# Prompt templates
# ------------------------------------------------------------------

_CLARIFY_PROMPT = (
    "You are an expert software engineer. Analyze the following requirement and "
    "return a JSON array of clarifying questions. Each element must be an object "
    'with a "question" key (string) and an optional "options" key (array of strings).\n'
    "\n"
    "Return ONLY valid JSON -- no markdown fences, no commentary.\n"
    "\n"
    "## Requirement\n"
    "Title: {title}\n"
    "Description:\n"
    "{description}\n"
    "\n"
    "## Project context\n"
    "{context}"
)

_PLAN_PROMPT = (
    "You are an expert software engineer. Create a detailed implementation plan "
    "for the following requirement. Return a JSON object with a \"steps\" key "
    "containing an array of objects, each with \"description\" (string) and "
    "\"files\" (array of file paths that will be touched).\n"
    "\n"
    "Return ONLY valid JSON -- no markdown fences, no commentary.\n"
    "\n"
    "## Requirement\n"
    "Title: {title}\n"
    "Description:\n"
    "{description}\n"
    "\n"
    "## Project context\n"
    "{context}"
)

_CODE_PROMPT = (
    "You are an expert software engineer. Implement the following requirement "
    "according to the plan below. Write production-quality code with proper "
    "error handling, type hints, and tests where appropriate.\n"
    "\n"
    "## Requirement\n"
    "Title: {title}\n"
    "Description:\n"
    "{description}\n"
    "\n"
    "## Implementation plan\n"
    "{plan}\n"
    "\n"
    "## Project context\n"
    "{context}\n"
    "\n"
    "## Rules\n"
    "{rules}"
)

_REVISE_PROMPT = (
    "You are an expert software engineer. Address the following review feedback "
    "by making the necessary code changes.\n"
    "\n"
    "## Feedback\n"
    "{feedback}\n"
    "\n"
    "## Project context\n"
    "{context}\n"
    "\n"
    "## Rules\n"
    "{rules}"
)


def _format_context(context: dict[str, Any] | None) -> str:
    """Flatten a context dict into a readable string."""
    if not context:
        return "(none)"
    parts: list[str] = []
    for key, value in context.items():
        if isinstance(value, str):
            parts.append(f"- {key}: {value}")
        else:
            parts.append(f"- {key}: {json.dumps(value, default=str)}")
    return "\n".join(parts) or "(none)"


def _extract_json(text: str) -> str:
    """Strip markdown code fences and extract the JSON portion from AI output."""
    # Remove ```json ... ``` blocks
    fenced = re.findall(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced[0].strip()
    # Try to find a JSON object or array
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return text


class ClaudeCodeAIProvider(AIProvider):
    """AI provider backed by Claude Code via ``claude-code-sdk``.

    Config keys:

    - ``model`` -- model name to use (default ``sonnet``).
    - ``rules`` -- list of project-level rules / instructions injected
      into every prompt.
    - ``max_turns`` -- maximum conversation turns (default ``50``).
    - ``env`` -- extra environment variables to pass to Claude Code
      (e.g. ``ANTHROPIC_BASE_URL``, ``ANTHROPIC_AUTH_TOKEN``).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._model: str = config.get("model", "sonnet")
        self._rules: list[str] = config.get("rules", [])
        self._max_turns: int = int(config.get("max_turns", 50))
        self._env: dict[str, str] = config.get("env", {})

    def _build_env(self) -> dict[str, str]:
        """Build env dict: inherit relevant vars from os.environ, overlay config."""
        env: dict[str, str] = {}
        for key in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
            val = os.environ.get(key)
            if val:
                env[key] = val
        env.update(self._env)
        return env

    def _build_options(self, cwd: str | None = None) -> "ClaudeCodeOptions":
        """Build ClaudeCodeOptions for a query call."""
        _require_sdk()
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_turns": self._max_turns,
            "permission_mode": "bypassPermissions",
        }
        env = self._build_env()
        if env:
            kwargs["env"] = env
        if cwd:
            kwargs["cwd"] = cwd
        return ClaudeCodeOptions(**kwargs)

    def _rules_text(self) -> str:
        if not self._rules:
            return "(no project rules configured)"
        return "\n".join(f"- {r}" for r in self._rules)

    async def _invoke(self, prompt: str, work_dir: str | None = None) -> str:
        """Invoke Claude Code and return the full text response."""
        options = self._build_options(cwd=work_dir)
        texts: list[str] = []
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        texts.append(block.text)
            elif isinstance(msg, ResultMessage) and msg.result:
                texts.append(msg.result)
        return "\n".join(texts)

    async def _invoke_stream(
        self, prompt: str, work_dir: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Invoke Claude Code and yield messages as they arrive."""
        options = self._build_options(cwd=work_dir)
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        yield {"type": "text", "content": block.text}
                    elif isinstance(block, ToolUseBlock):
                        yield {
                            "type": "tool_use",
                            "name": block.name,
                            "input": block.input,
                        }
            elif isinstance(msg, ResultMessage):
                yield {
                    "type": "result",
                    "content": msg.result or "done",
                    "is_error": msg.is_error,
                }

    # ------------------------------------------------------------------
    # AIProvider interface
    # ------------------------------------------------------------------

    async def clarify(
        self,
        requirement: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        prompt = _CLARIFY_PROMPT.format(
            title=requirement.get("title", ""),
            description=requirement.get("description", ""),
            context=_format_context(context),
        )
        raw = await self._invoke(prompt)
        cleaned = _extract_json(raw)
        try:
            questions = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse clarify response as JSON: %s", raw[:200])
            questions = [{"question": raw}]
        if isinstance(questions, dict):
            questions = [questions]
        return questions

    async def plan(
        self,
        requirement: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        prompt = _PLAN_PROMPT.format(
            title=requirement.get("title", ""),
            description=requirement.get("description", ""),
            context=_format_context(context),
        )
        raw = await self._invoke(prompt)
        cleaned = _extract_json(raw)
        try:
            plan_data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse plan response as JSON: %s", raw[:200])
            plan_data = {"steps": [{"description": raw, "files": []}]}
        return plan_data

    async def code(
        self,
        requirement: dict[str, Any],
        plan: dict[str, Any],
        context: dict[str, Any] | None = None,
        work_dir: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        plan_text = json.dumps(plan, indent=2, default=str)
        prompt = _CODE_PROMPT.format(
            title=requirement.get("title", ""),
            description=requirement.get("description", ""),
            plan=plan_text,
            context=_format_context(context),
            rules=self._rules_text(),
        )
        async for msg in self._invoke_stream(prompt, work_dir=work_dir):
            yield msg

    async def revise(
        self,
        feedback: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
        work_dir: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        feedback_text = json.dumps(feedback, indent=2, default=str)
        prompt = _REVISE_PROMPT.format(
            feedback=feedback_text,
            context=_format_context(context),
            rules=self._rules_text(),
        )
        async for msg in self._invoke_stream(prompt, work_dir=work_dir):
            yield msg
