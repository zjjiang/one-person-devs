"""Claude Code AI Provider using claude-code-sdk."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator

from opd.capabilities.base import HealthStatus
from opd.providers.ai.base import AIProvider

logger = logging.getLogger(__name__)

try:
    from claude_code_sdk import ClaudeCodeOptions, query

    _HAS_SDK = True
except ImportError:
    _HAS_SDK = False


class ClaudeCodeProvider(AIProvider):
    """AI provider backed by Claude Code SDK. All methods stream via SSE."""

    CONFIG_SCHEMA = [
        {"name": "base_url", "label": "Base URL", "type": "text", "required": False},
        {"name": "auth_token", "label": "Auth Token", "type": "password", "required": True},
        {
            "name": "model", "label": "Model", "type": "select", "required": False,
            "default": "sonnet",
            "options": ["sonnet", "opus", "haiku"],
        },
    ]

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._model = self.config.get("model", "sonnet")

    async def initialize(self):
        if not _HAS_SDK:
            logger.warning(
                "claude-code-sdk not installed. Install with: uv sync --extra ai"
            )

    async def health_check(self) -> HealthStatus:
        if not _HAS_SDK:
            return HealthStatus(healthy=False, message="claude-code-sdk not installed")
        auth_token = self.config.get("auth_token") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if not auth_token:
            return HealthStatus(healthy=False, message="Auth Token 未配置")
        return HealthStatus(healthy=True, message="Claude Code SDK available")

    async def cleanup(self):
        pass

    def _build_options(self, system_prompt: str,
                       work_dir: str | None = None) -> "ClaudeCodeOptions":
        opts = {
            "system_prompt": system_prompt,
            "model": self._model,
            "permission_mode": "bypassPermissions",
        }
        if work_dir:
            opts["cwd"] = work_dir
        return ClaudeCodeOptions(**opts)

    def _apply_env(self) -> dict[str, str | None]:
        """Set config values as env vars for the SDK, return old values for restore."""
        mapping = {
            "auth_token": "ANTHROPIC_AUTH_TOKEN",
            "base_url": "ANTHROPIC_BASE_URL",
        }
        old = {}
        for cfg_key, env_key in mapping.items():
            val = self.config.get(cfg_key)
            if val:
                old[env_key] = os.environ.get(env_key)
                os.environ[env_key] = val
        return old

    def _restore_env(self, old: dict[str, str | None]):
        """Restore env vars to previous values."""
        for key, val in old.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    async def _invoke_stream(self, prompt: str, system_prompt: str,
                             work_dir: str | None = None) -> AsyncIterator[dict]:
        """Call Claude Code SDK and yield normalized message dicts."""
        if not _HAS_SDK:
            yield {"type": "error", "content": "claude-code-sdk not installed"}
            return

        options = self._build_options(system_prompt, work_dir)
        old_env = self._apply_env()
        try:
            async for msg in query(prompt=prompt, options=options):
                if hasattr(msg, "content") and msg.content:
                    for block in msg.content:
                        if hasattr(block, "text"):
                            yield {"type": "assistant", "content": block.text}
                        elif hasattr(block, "tool_name"):
                            yield {
                                "type": "tool_use",
                                "name": block.tool_name,
                                "input": getattr(block, "tool_input", ""),
                            }
        except Exception as e:
            logger.exception("Claude Code SDK error")
            yield {"type": "error", "content": str(e)}
        finally:
            self._restore_env(old_env)

    async def prepare_prd(self, system_prompt: str,
                          user_prompt: str) -> AsyncIterator[dict]:
        async for msg in self._invoke_stream(user_prompt, system_prompt):
            yield msg

    async def clarify(self, system_prompt: str,
                      user_prompt: str) -> AsyncIterator[dict]:
        async for msg in self._invoke_stream(user_prompt, system_prompt):
            yield msg

    async def plan(self, system_prompt: str,
                   user_prompt: str) -> AsyncIterator[dict]:
        async for msg in self._invoke_stream(user_prompt, system_prompt):
            yield msg

    async def design(self, system_prompt: str,
                     user_prompt: str) -> AsyncIterator[dict]:
        async for msg in self._invoke_stream(user_prompt, system_prompt):
            yield msg

    async def code(self, system_prompt: str, user_prompt: str,
                   work_dir: str) -> AsyncIterator[dict]:
        async for msg in self._invoke_stream(user_prompt, system_prompt, work_dir):
            yield msg
