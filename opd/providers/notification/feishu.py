"""飞书应用 Notification Provider — 通过飞书开放平台发送消息卡片."""

from __future__ import annotations

import json
import logging
import time

import httpx

from opd.capabilities.base import HealthStatus
from opd.providers.notification.base import NotificationProvider

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
_SEND_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
_FILE_URL = "https://open.feishu.cn/open-apis/im/v1/files"


class FeishuProvider(NotificationProvider):
    """飞书应用消息推送 provider."""

    CONFIG_SCHEMA = [
        {"name": "app_id", "label": "App ID", "type": "text", "required": True},
        {"name": "app_secret", "label": "App Secret", "type": "password", "required": True},
        {
            "name": "receive_id", "label": "接收者 ID",
            "type": "text", "required": True,
        },
        {
            "name": "receive_id_type", "label": "ID 类型",
            "type": "select", "required": False,
            "default": "chat_id",
            "options": [
                {"label": "群聊 chat_id", "value": "chat_id"},
                {"label": "用户 open_id", "value": "open_id"},
            ],
        },
    ]

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._token: str = ""
        self._token_expires: float = 0

    async def _get_tenant_token(self) -> str:
        """Fetch or return cached tenant_access_token."""
        if self._token and time.time() < self._token_expires:
            return self._token

        app_id = self.config.get("app_id", "")
        app_secret = self.config.get("app_secret", "")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _TOKEN_URL,
                json={"app_id": app_id, "app_secret": app_secret},
            )
            data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书 token 获取失败: {data.get('msg', 'unknown')}")
        self._token = data["tenant_access_token"]
        # Token expires in `expire` seconds; refresh 60s early
        self._token_expires = time.time() + data.get("expire", 7200) - 60
        return self._token

    async def send(self, title: str, content: str, link: str = "") -> bool:
        """Send an interactive card message via Feishu API."""
        token = await self._get_tenant_token()
        receive_id = self.config.get("receive_id", "")
        receive_id_type = self.config.get("receive_id_type", "chat_id")

        elements = [{"tag": "markdown", "content": content}]
        if link:
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看详情"},
                    "type": "primary",
                    "url": link,
                }],
            })

        card = {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            },
            "elements": elements,
        }

        payload = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card),
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_SEND_URL}?receive_id_type={receive_id_type}",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()

        if data.get("code") != 0:
            logger.error("飞书消息发送失败: %s", data.get("msg", "unknown"))
            return False
        return True

    async def _upload_file(self, file_content: bytes, file_name: str) -> str | None:
        """Upload a file to Feishu and return the file_key."""
        token = await self._get_tenant_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _FILE_URL,
                headers={"Authorization": f"Bearer {token}"},
                data={"file_type": "stream", "file_name": file_name},
                files={"file": (file_name, file_content)},
            )
            data = resp.json()
        if data.get("code") != 0:
            logger.error("飞书文件上传失败: %s", data.get("msg", "unknown"))
            return None
        return data.get("data", {}).get("file_key")

    async def send_file(
        self, title: str, content: str, link: str,
        file_content: bytes, file_name: str,
    ) -> bool:
        """Send a card notification followed by the document file."""
        # 1. Send the card notification as usual
        await self.send(title, content, link)
        # 2. Upload and send the file
        file_key = await self._upload_file(file_content, file_name)
        if not file_key:
            return False
        token = await self._get_tenant_token()
        receive_id = self.config.get("receive_id", "")
        receive_id_type = self.config.get("receive_id_type", "chat_id")
        payload = {
            "receive_id": receive_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key}),
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_SEND_URL}?receive_id_type={receive_id_type}",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
        if data.get("code") != 0:
            logger.error("飞书文件消息发送失败: %s", data.get("msg", "unknown"))
            return False
        return True

    async def health_check(self) -> HealthStatus:
        if not self.config.get("app_id") or not self.config.get("app_secret"):
            return HealthStatus(healthy=False, message="缺少 app_id 或 app_secret")
        try:
            await self._get_tenant_token()
            return HealthStatus(healthy=True, message="飞书 token 获取成功")
        except Exception as e:
            return HealthStatus(healthy=False, message=str(e))
