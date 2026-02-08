"""Local filesystem requirement provider.

Requirements are stored as individual Markdown files inside a
configurable directory.  Each file uses YAML front-matter for metadata
and the remainder of the file as the description body.

Example file ``REQ-001.md``::

    ---
    title: Add user login
    status: open
    ---
    Implement OAuth2 login flow with Google and GitHub providers.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from opd.providers.requirement.base import RequirementProvider

logger = logging.getLogger(__name__)

_FRONT_MATTER_RE = re.compile(
    r"\A---\s*\n(?P<meta>.*?)\n---\s*\n(?P<body>.*)",
    re.DOTALL,
)


def _parse_simple_yaml(text: str) -> dict[str, str]:
    """Minimal YAML-like parser for front-matter key: value pairs.

    This avoids pulling in PyYAML at import time just for trivial
    front-matter.  Only flat ``key: value`` lines are supported.
    """
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        if value:
            result[key.strip()] = value.strip()
    return result


def _parse_requirement_file(path: Path) -> dict[str, Any]:
    """Parse a single requirement Markdown file into a dict."""
    raw = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER_RE.match(raw)
    if match:
        meta = _parse_simple_yaml(match.group("meta"))
        body = match.group("body").strip()
    else:
        meta = {}
        body = raw.strip()

    req_id = path.stem  # filename without extension
    return {
        "id": req_id,
        "title": meta.get("title", req_id),
        "status": meta.get("status", "open"),
        "description": body,
        **{k: v for k, v in meta.items() if k not in ("title", "status")},
    }


class LocalRequirementProvider(RequirementProvider):
    """Reads requirements from local Markdown files.

    Config keys:

    - ``base_dir`` -- directory containing ``*.md`` requirement files.
      Defaults to ``./requirements``.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._base_dir = Path(config.get("base_dir", "./requirements")).resolve()

    async def initialize(self) -> None:
        if not self._base_dir.exists():
            logger.warning("Requirement directory does not exist: %s", self._base_dir)
            self._base_dir.mkdir(parents=True, exist_ok=True)

    async def get_requirement(self, requirement_id: str) -> dict[str, Any]:
        path = self._base_dir / f"{requirement_id}.md"
        if not path.is_file():
            raise KeyError(f"Requirement not found: {requirement_id}")
        return _parse_requirement_file(path)

    async def list_requirements(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        filters = filters or {}
        results: list[dict[str, Any]] = []
        if not self._base_dir.is_dir():
            return results
        for path in sorted(self._base_dir.glob("*.md")):
            req = _parse_requirement_file(path)
            # Apply simple equality filters
            if all(req.get(k) == v for k, v in filters.items()):
                results.append(req)
        return results

    async def update_status(self, requirement_id: str, status: str) -> None:
        path = self._base_dir / f"{requirement_id}.md"
        if not path.is_file():
            raise KeyError(f"Requirement not found: {requirement_id}")

        raw = path.read_text(encoding="utf-8")
        match = _FRONT_MATTER_RE.match(raw)
        if match:
            meta = _parse_simple_yaml(match.group("meta"))
            meta["status"] = status
            front = "\n".join(f"{k}: {v}" for k, v in meta.items())
            body = match.group("body").strip()
            new_content = f"---\n{front}\n---\n{body}\n"
        else:
            # No front-matter yet -- prepend one
            new_content = f"---\ntitle: {requirement_id}\nstatus: {status}\n---\n{raw}"

        path.write_text(new_content, encoding="utf-8")
        logger.info("Updated requirement %s status to %s", requirement_id, status)
