"""Local filesystem document provider."""

from __future__ import annotations

from pathlib import Path

from opd.capabilities.base import HealthStatus

from .base import DocProvider


class LocalDocProvider(DocProvider):
    """Reads local markdown files from a configured base directory."""

    CONFIG_SCHEMA = [
        {"name": "base_dir", "label": "Base Directory", "type": "string",
         "required": False, "default": "."},
    ]

    @property
    def base_dir(self) -> Path:
        return Path(self.config.get("base_dir", "."))

    async def get_document(self, doc_id: str) -> str:
        path = self.base_dir / doc_id
        return path.read_text(encoding="utf-8")

    async def search_documents(self, query: str) -> list[dict]:
        results = []
        for md in self.base_dir.glob("**/*.md"):
            content = md.read_text(encoding="utf-8")
            if query.lower() in content.lower():
                results.append({"id": str(md.relative_to(self.base_dir)), "path": str(md)})
        return results

    async def health_check(self) -> HealthStatus:
        if self.base_dir.is_dir():
            return HealthStatus(healthy=True, message=f"base_dir exists: {self.base_dir}")
        return HealthStatus(healthy=False, message=f"base_dir not found: {self.base_dir}")
