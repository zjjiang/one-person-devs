"""Notion document provider."""

from __future__ import annotations

from opd.capabilities.base import HealthStatus

from .base import DocProvider


class NotionDocProvider(DocProvider):
    """Notion document provider (stub)."""

    async def get_document(self, doc_id: str) -> str:
        raise NotImplementedError

    async def search_documents(self, query: str) -> list[dict]:
        raise NotImplementedError

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=False, message="Not implemented yet")
