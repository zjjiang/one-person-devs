"""Abstract base class for document providers."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from opd.providers.base import Provider


class DocumentProvider(Provider):
    """Interface for retrieving project documentation.

    A *document* is represented as a plain ``dict`` with at least:

    - ``id`` -- unique identifier (string, typically the relative path)
    - ``title`` -- human-readable title
    - ``content`` -- full text content of the document
    """

    @abstractmethod
    async def get_document(self, doc_id: str) -> dict[str, Any]:
        """Return a single document by *doc_id*.

        Raises ``KeyError`` when the document does not exist.
        """

    @abstractmethod
    async def search_documents(self, query: str) -> list[dict[str, Any]]:
        """Return documents whose content matches *query*.

        The search is provider-specific -- it may be full-text, keyword,
        or semantic depending on the backend.
        """
