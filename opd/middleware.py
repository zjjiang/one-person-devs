"""ASGI middleware: logging + error handling, SSE passthrough."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

STREAMING_SUFFIXES = ("/stream", "/logs")


class LoggingMiddleware:
    """Pure ASGI middleware. Does NOT use BaseHTTPMiddleware to avoid buffering SSE."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Pass through streaming paths without any wrapping
        if any(path.endswith(s) for s in STREAMING_SUFFIXES):
            await self.app(scope, receive, send)
            return

        start = time.time()
        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("Unhandled error: %s %s", scope.get("method", ""), path)
            raise
        finally:
            elapsed = (time.time() - start) * 1000
            logger.info("%s %s %d %.0fms", scope.get("method", ""), path, status_code, elapsed)


class ErrorHandlingMiddleware:
    """Pure ASGI middleware for catching common errors."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.endswith(s) for s in STREAMING_SUFFIXES):
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except ValueError as e:
            await self._send_error(send, 400, str(e))
        except PermissionError as e:
            await self._send_error(send, 403, str(e))
        except FileNotFoundError as e:
            await self._send_error(send, 404, str(e))

    @staticmethod
    async def _send_error(send, status: int, message: str):
        import json
        body = json.dumps({"error": message}).encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [[b"content-type", b"application/json"]],
        })
        await send({"type": "http.response.body", "body": body})
