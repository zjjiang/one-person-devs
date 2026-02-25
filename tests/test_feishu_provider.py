"""Tests for Feishu notification provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from opd.providers.notification.feishu import FeishuProvider


@pytest.fixture
def feishu():
    return FeishuProvider({
        "app_id": "test_app_id",
        "app_secret": "test_secret",
        "receive_id": "oc_test_chat",
        "receive_id_type": "chat_id",
    })


class TestFeishuHealthCheck:
    async def test_missing_credentials(self):
        prov = FeishuProvider({})
        status = await prov.health_check()
        assert not status.healthy
        assert "app_id" in status.message

    async def test_healthy_with_valid_token(self, feishu):
        with patch.object(feishu, "_get_tenant_token", new_callable=AsyncMock) as mock:
            mock.return_value = "fake_token"
            status = await feishu.health_check()
            assert status.healthy

    async def test_unhealthy_on_token_error(self, feishu):
        with patch.object(feishu, "_get_tenant_token", new_callable=AsyncMock) as mock:
            mock.side_effect = RuntimeError("token error")
            status = await feishu.health_check()
            assert not status.healthy


class TestFeishuGetToken:
    async def test_caches_token(self, feishu):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 0,
            "tenant_access_token": "tok_123",
            "expire": 7200,
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("opd.providers.notification.feishu.httpx.AsyncClient",
                    return_value=mock_client):
            token1 = await feishu._get_tenant_token()
            token2 = await feishu._get_tenant_token()

        assert token1 == "tok_123"
        assert token2 == "tok_123"
        # Only one HTTP call due to caching
        assert mock_client.post.call_count == 1

    async def test_token_error_raises(self, feishu):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 10003, "msg": "invalid app_id"}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("opd.providers.notification.feishu.httpx.AsyncClient",
                    return_value=mock_client):
            with pytest.raises(RuntimeError, match="invalid app_id"):
                await feishu._get_tenant_token()


class TestFeishuSend:
    async def test_send_success(self, feishu):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 0}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(feishu, "_get_tenant_token",
                          new_callable=AsyncMock, return_value="tok"):
            with patch("opd.providers.notification.feishu.httpx.AsyncClient",
                        return_value=mock_client):
                result = await feishu.send("Title", "Content", "/link")

        assert result is True

    async def test_send_failure(self, feishu):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 99999, "msg": "bad request"}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(feishu, "_get_tenant_token",
                          new_callable=AsyncMock, return_value="tok"):
            with patch("opd.providers.notification.feishu.httpx.AsyncClient",
                        return_value=mock_client):
                result = await feishu.send("Title", "Content")

        assert result is False
