"""Ducc AI Provider — uses claude-code-sdk with custom CLI binary."""

from __future__ import annotations

import logging
import shutil
from collections.abc import AsyncIterator

from opd.capabilities.base import HealthStatus
from opd.providers.ai.base import AIProvider

logger = logging.getLogger(__name__)

try:
    from claude_code_sdk import ClaudeCodeOptions, query
    from claude_code_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

    _HAS_SDK = True
except ImportError:
    _HAS_SDK = False


class DuccProvider(AIProvider):
    """AI provider using ducc CLI (compatible with Claude Code interface).

    Auth is handled externally — user runs `ducc` once in terminal,
    scans QR code via 如流, and the token is cached locally.
    """

    CONFIG_SCHEMA = [
        {
            "name": "cli_path", "label": "CLI 路径", "type": "text",
            "required": False, "default": "ducc",
        },
        {
            "name": "model", "label": "模型", "type": "text",
            "required": False,
        },
    ]

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._cli_path = self.config.get("cli_path", "ducc")
        self._model = self.config.get("model") or None

    async def initialize(self):
        if not _HAS_SDK:
            logger.warning("claude-code-sdk not installed (required for ducc provider)")

    async def health_check(self) -> HealthStatus:
        if not _HAS_SDK:
            return HealthStatus(healthy=False, message="claude-code-sdk 未安装")
        if not shutil.which(self._cli_path):
            return HealthStatus(healthy=False, message=f"未找到 {self._cli_path} 命令")
        return HealthStatus(healthy=True, message=f"{self._cli_path} 可用")

    async def cleanup(self):
        pass

    def _build_options(self, system_prompt: str,
                       work_dir: str | None = None) -> "ClaudeCodeOptions":
        opts: dict = {"system_prompt": system_prompt, "permission_mode": "bypassPermissions"}
        if self._model:
            opts["model"] = self._model
        if work_dir:
            opts["cwd"] = work_dir
        return ClaudeCodeOptions(**opts)

    async def _invoke_stream(self, prompt: str, system_prompt: str,
                             work_dir: str | None = None) -> AsyncIterator[dict]:
        if not _HAS_SDK:
            yield {"type": "error", "content": "claude-code-sdk not installed"}
            return

        options = self._build_options(system_prompt, work_dir)
        transport = SubprocessCLITransport(
            prompt=prompt, options=options, cli_path=self._cli_path,
        )
        try:
            async for msg in query(prompt=prompt, options=options, transport=transport):
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
            logger.exception("Ducc CLI error")
            yield {"type": "error", "content": str(e)}

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
