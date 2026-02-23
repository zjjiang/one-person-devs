"""Tests for webhook handler."""

from __future__ import annotations

from unittest.mock import AsyncMock


class TestGithubWebhook:
    async def test_pr_review_event(self):
        from opd.api.webhooks import github_webhook

        request = AsyncMock()
        request.headers = {"X-GitHub-Event": "pull_request_review"}
        request.json.return_value = {
            "action": "submitted",
            "pull_request": {"number": 42},
        }
        result = await github_webhook(request)
        assert result["status"] == "ok"

    async def test_pr_event(self):
        from opd.api.webhooks import github_webhook

        request = AsyncMock()
        request.headers = {"X-GitHub-Event": "pull_request"}
        request.json.return_value = {
            "action": "opened",
            "pull_request": {"number": 1},
        }
        result = await github_webhook(request)
        assert result["status"] == "ok"

    async def test_unknown_event(self):
        from opd.api.webhooks import github_webhook

        request = AsyncMock()
        request.headers = {"X-GitHub-Event": "push"}
        request.json.return_value = {}
        result = await github_webhook(request)
        assert result["status"] == "ok"
