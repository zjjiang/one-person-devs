"""Local filesystem document provider.

Reads Markdown (``.md``) files from a configured directory tree and
provides simple substring-based search.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from opd.providers.document.base import DocumentProvider

logger = logging.getLogger(__name__)


class LocalDocumentProvider(DocumentProvider):
    """Serves documents from a local directory.

    Config keys:

    - ``base_dir`` -- root directory to scan for ``*.md`` files.
      Defaults to ``./docs``.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._base_dir = Path(config.get("base_dir", "./docs")).resolve()

    async def initialize(self) -> None:
        if not self._base_dir.exists():
            logger.warning("Document directory does not exist: %s", self._base_dir)
            self._base_dir.mkdir(parents=True, exist_ok=True)

    def _doc_from_path(self, path: Path) -> dict[str, Any]:
        """Build a document dict from a file path."""
        rel = path.relative_to(self._base_dir)
        content = path.read_text(encoding="utf-8")
        # Use the first ``# heading`` as title, fall back to filename.
        title = path.stem
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped.removeprefix("# ").strip()
                break
        return {
            "id": str(rel),
            "title": title,
            "content": content,
        }

    async def get_document(self, doc_id: str) -> dict[str, Any]:
        path = self._base_dir / doc_id
        if not path.is_file():
            raise KeyError(f"Document not found: {doc_id}")
        return self._doc_from_path(path)

    async def search_documents(self, query: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if not self._base_dir.is_dir():
            return results
        query_lower = query.lower()
        for path in sorted(self._base_dir.rglob("*.md")):
            doc = self._doc_from_path(path)
            # Simple case-insensitive substring match on title + content
            if query_lower in doc["title"].lower() or query_lower in doc["content"].lower():
                results.append(doc)
        return results
