"""Global log viewer API — SSE real-time stream + paginated history."""

from __future__ import annotations

import asyncio
import functools
import json
import logging
from enum import Enum
from pathlib import Path
from re import compile as re_compile

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from opd.config import load_config

router = APIRouter(prefix="/api/logs", tags=["logs"])

logger = logging.getLogger("opd.api.logs")

# ---------------------------------------------------------------------------
# Constants & types
# ---------------------------------------------------------------------------

_LOG_RE = re_compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)"
    r" \[(?P<level>\w+)\]"
    r" (?P<name>[^:]+):"
    r" (?P<msg>.*)$"
)

LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}

VALID_LEVELS = set(LEVEL_ORDER.keys())


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _log_dir() -> Path:
    """Resolve log directory once and cache it (doesn't change at runtime)."""
    try:
        cfg = load_config()
        return Path(cfg.logging.dir)
    except Exception:
        return Path("./logs")


def _parse_line(line: str) -> dict | None:
    m = _LOG_RE.match(line.strip())
    if not m:
        return None
    return {
        "ts": m.group("ts"),
        "level": m.group("level"),
        "name": m.group("name"),
        "msg": m.group("msg"),
    }


def _matches(entry: dict, level: str | None, search: str | None) -> bool:
    if level and LEVEL_ORDER.get(entry["level"], 0) < LEVEL_ORDER.get(level.upper(), 0):
        return False
    if search and search.lower() not in (entry["msg"] + entry["name"]).lower():
        return False
    return True


def _read_tail(path: Path, max_lines: int = 2000) -> list[str]:
    """Read last *max_lines* from a file efficiently."""
    if not path.exists():
        return []
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        chunk = min(size, 2 * 1024 * 1024)
        f.seek(size - chunk)
        data = f.read().decode("utf-8", errors="replace")
    lines = data.splitlines()
    return lines[-max_lines:]


# ---------------------------------------------------------------------------
# SSE real-time stream
# ---------------------------------------------------------------------------

_OPD_LOGGER_NAME = "opd"


class _QueueHandler(logging.Handler):
    """Push log records into an asyncio queue for SSE streaming."""

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.queue = queue
        self.loop = loop
        self.dropped = 0

    def emit(self, record: logging.LogRecord):
        formatted = self.format(record)
        ts = formatted.split(" [")[0] if " [" in formatted else ""
        entry = {
            "ts": ts,
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        try:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, entry)
        except asyncio.QueueFull:
            self.dropped += 1
            if self.dropped % 100 == 1:
                logger.warning("SSE log queue full, %d messages dropped", self.dropped)


@router.get("/stream")
async def stream_logs(
    level: LogLevel | None = Query(None, description="Minimum log level filter"),
):
    """SSE endpoint — streams new log entries in real time."""
    level_str = level.value if level else None

    queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    loop = asyncio.get_running_loop()

    handler = _QueueHandler(queue, loop)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    # Attach to opd logger only, not root — avoids third-party library noise
    opd_logger = logging.getLogger(_OPD_LOGGER_NAME)
    opd_logger.addHandler(handler)

    async def generate():
        try:
            # Replay recent history
            log_file = _log_dir() / "opd.log"
            for line in _read_tail(log_file, 100):
                entry = _parse_line(line)
                if entry and _matches(entry, level_str, None):
                    yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"

            # Stream live
            while True:
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=15)
                    if _matches(entry, level_str, None):
                        yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            opd_logger.removeHandler(handler)

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Paginated history
# ---------------------------------------------------------------------------

@router.get("/history")
async def log_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000),
    level: LogLevel | None = Query(None),
    search: str | None = Query(None),
):
    """Return paginated log entries from opd.log (newest first)."""
    level_str = level.value if level else None
    log_file = _log_dir() / "opd.log"
    raw_lines = _read_tail(log_file, 10000)

    # Parse, filter, reverse (newest first)
    entries: list[dict] = []
    for line in reversed(raw_lines):
        entry = _parse_line(line)
        if entry and _matches(entry, level_str, search):
            entries.append(entry)

    total = len(entries)
    start = (page - 1) * page_size
    page_entries = entries[start : start + page_size]

    return {
        "items": page_entries,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
