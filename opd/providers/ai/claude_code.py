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

        # Actually test connectivity by hitting the messages endpoint
        base_url = self.config.get("base_url") or os.environ.get("ANTHROPIC_BASE_URL", "")
        if base_url:
            import asyncio
            import json
            import urllib.error
            import urllib.request

            # POST a minimal request to /v1/messages to verify URL + auth
            test_url = base_url.rstrip("/") + "/v1/messages"
            body = json.dumps({
                "model": self._model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            }).encode()
            try:
                req = urllib.request.Request(test_url, data=body, method="POST")
                req.add_header("Authorization", f"Bearer {auth_token}")
                req.add_header("Content-Type", "application/json")
                req.add_header("anthropic-version", "2023-06-01")
                await asyncio.to_thread(
                    urllib.request.urlopen, req, timeout=10
                )
                return HealthStatus(healthy=True, message="连接正常")
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    return HealthStatus(healthy=False, message=f"认证失败 (HTTP {e.code})")
                if e.code == 404:
                    return HealthStatus(healthy=False, message="API 地址错误 (404)")
                if e.code == 400:
                    # 400 = bad request but endpoint exists and auth passed
                    return HealthStatus(healthy=True, message="连接正常")
                if e.code >= 500:
                    return HealthStatus(healthy=False, message=f"服务端错误 (HTTP {e.code})")
                # Other 4xx (e.g. 429 rate limit) = connection works
                return HealthStatus(healthy=True, message="连接正常")
            except (urllib.error.URLError, OSError) as e:
                reason = getattr(e, "reason", e)
                return HealthStatus(healthy=False, message=f"无法连接: {reason}")

        return HealthStatus(healthy=True, message="连接正常")

    async def cleanup(self):
        pass

    def _build_options(self, system_prompt: str,
                       work_dir: str | None = None,
                       max_turns: int | None = None) -> "ClaudeCodeOptions":
        opts = {
            "system_prompt": system_prompt,
            "model": self._model,
            "permission_mode": "bypassPermissions",
        }
        if work_dir:
            opts["cwd"] = work_dir
        if max_turns is not None:
            opts["max_turns"] = max_turns
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
                             work_dir: str | None = None,
                             max_turns: int | None = None) -> AsyncIterator[dict]:
        """Call Claude Code SDK and yield normalized message dicts."""
        if not _HAS_SDK:
            yield {"type": "error", "content": "claude-code-sdk not installed"}
            return

        options = self._build_options(system_prompt, work_dir, max_turns)
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

    async def refine_prd(self, system_prompt: str,
                         user_prompt: str) -> AsyncIterator[dict]:
        async for msg in self._invoke_stream(user_prompt, system_prompt):
            yield msg
