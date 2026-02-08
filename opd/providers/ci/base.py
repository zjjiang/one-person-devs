"""Abstract base class for CI/CD pipeline providers."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from opd.providers.base import Provider


class CIProvider(Provider):
    """Interface for triggering and monitoring CI/CD pipelines."""

    @abstractmethod
    async def trigger_pipeline(
        self, repo: str, branch: str, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Trigger a pipeline run and return its metadata.

        The returned dict must contain at least:

        - ``pipeline_id`` -- unique identifier for the pipeline run
        - ``status`` -- initial status (e.g. ``pending``)
        """

    @abstractmethod
    async def get_pipeline_status(self, pipeline_id: str) -> str:
        """Return the current status of a pipeline run.

        Typical values: ``pending``, ``running``, ``success``, ``failure``,
        ``cancelled``.
        """

    @abstractmethod
    async def get_pipeline_logs(self, pipeline_id: str) -> str:
        """Return the full log output of a pipeline run."""
