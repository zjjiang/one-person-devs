"""Document provider base class."""

from __future__ import annotations

from abc import abstractmethod

from opd.capabilities.base import HealthStatus, Provider


class DocProvider(Provider):
    """Abstract base for document providers."""

    @abstractmethod
    async def get_document(self, doc_id: str) -> str:
        """Retrieve a document by ID."""

    @abstractmethod
    async def search_documents(self, query: str) -> list[dict]:
        """Search documents matching a query."""

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Check if the document provider is reachable."""
