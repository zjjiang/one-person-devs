"""Tests for log viewer API endpoints."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from fastapi import FastAPI
from opd.api.logs import router as logs_router

SAMPLE_LINES = [
    "2026-02-24 10:00:00,000 [INFO] opd: Starting OPD v2...",
    "2026-02-24 10:00:01,000 [INFO] opd: Database initialized",
    "2026-02-24 10:00:02,000 [WARNING] opd.engine: Slow query",
    "2026-02-24 10:00:03,000 [ERROR] opd.api: Request failed",
    "2026-02-24 10:00:04,000 [DEBUG] opd.db: SELECT * FROM ...",
]


@pytest.fixture
async def log_client(tmp_path: Path):
    """Lightweight test client — only mounts the logs router."""
    log_file = tmp_path / "opd.log"
    log_file.write_text("\n".join(SAMPLE_LINES) + "\n")

    app = FastAPI()
    app.include_router(logs_router)

    transport = ASGITransport(app=app)
    with patch("opd.api.logs._log_dir", return_value=tmp_path):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


class TestLogHistory:
    async def test_returns_entries_newest_first(self, log_client):
        resp = await log_client.get("/api/logs/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5
        # Newest first
        assert data["items"][0]["level"] == "DEBUG"
        assert data["items"][-1]["level"] == "INFO"

    async def test_filter_by_level(self, log_client):
        resp = await log_client.get("/api/logs/history?level=WARNING")
        data = resp.json()
        assert data["total"] == 2
        levels = {e["level"] for e in data["items"]}
        assert levels <= {"WARNING", "ERROR", "CRITICAL"}

    async def test_invalid_level_rejected(self, log_client):
        resp = await log_client.get("/api/logs/history?level=BANANA")
        assert resp.status_code == 422

    async def test_search_keyword(self, log_client):
        resp = await log_client.get("/api/logs/history?search=query")
        data = resp.json()
        assert data["total"] == 1
        assert "query" in data["items"][0]["msg"].lower()

    async def test_pagination(self, log_client):
        resp = await log_client.get("/api/logs/history?page=1&page_size=2")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1

    async def test_empty_log_file(self, tmp_path):
        """Separate client with empty log file."""
        (tmp_path / "opd.log").write_text("")
        app = FastAPI()
        app.include_router(logs_router)
        transport = ASGITransport(app=app)
        with patch("opd.api.logs._log_dir", return_value=tmp_path):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/logs/history")
        assert resp.json()["total"] == 0


class TestLogHelpers:
    async def test_parse_line(self):
        from opd.api.logs import _parse_line

        entry = _parse_line("2026-02-24 10:00:00,000 [INFO] opd: Starting OPD v2...")
        assert entry is not None
        assert entry["level"] == "INFO"
        assert entry["name"] == "opd"
        assert entry["msg"] == "Starting OPD v2..."

    async def test_parse_line_invalid(self):
        from opd.api.logs import _parse_line

        assert _parse_line("not a log line") is None
        assert _parse_line("") is None

    async def test_matches_level_filter(self):
        from opd.api.logs import _matches

        info = {"level": "INFO", "name": "opd", "msg": "test"}
        error = {"level": "ERROR", "name": "opd", "msg": "test"}
        assert _matches(info, "INFO", None) is True
        assert _matches(info, "WARNING", None) is False
        assert _matches(error, "WARNING", None) is True

    async def test_matches_search_filter(self):
        from opd.api.logs import _matches

        entry = {"level": "INFO", "name": "opd.api", "msg": "Request failed"}
        assert _matches(entry, None, "failed") is True
        assert _matches(entry, None, "success") is False
        assert _matches(entry, None, "opd.api") is True

    async def test_read_tail(self, tmp_path):
        from opd.api.logs import _read_tail

        f = tmp_path / "test.log"
        f.write_text("\n".join(f"line {i}" for i in range(100)))
        lines = _read_tail(f, 10)
        assert len(lines) == 10
        assert lines[-1] == "line 99"

    async def test_read_tail_missing_file(self, tmp_path):
        from opd.api.logs import _read_tail

        lines = _read_tail(tmp_path / "nonexistent.log")
        assert lines == []

    async def test_queue_handler_format_called_once(self):
        """Verify _QueueHandler.emit() only formats the record once."""
        import asyncio
        from unittest.mock import MagicMock

        from opd.api.logs import _QueueHandler

        loop = asyncio.get_running_loop()
        queue = asyncio.Queue(maxsize=10)
        handler = _QueueHandler(queue, loop)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

        record = logging.LogRecord(
            name="opd.test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        # Spy on format
        original_format = handler.format
        call_count = 0

        def counting_format(r):
            nonlocal call_count
            call_count += 1
            return original_format(r)

        handler.format = counting_format
        handler.emit(record)

        assert call_count == 1
        # call_soon_threadsafe schedules on the loop; yield control to let it execute
        await asyncio.sleep(0)
        entry = queue.get_nowait()
        assert entry["msg"] == "hello"
        assert entry["level"] == "INFO"
