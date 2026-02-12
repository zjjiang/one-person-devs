"""Middleware for CORS, logging, and error handling.

Both LoggingMiddleware and ErrorHandlingMiddleware are implemented as pure ASGI
middleware (not BaseHTTPMiddleware) so that StreamingResponse / SSE endpoints
are never buffered.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("opd.middleware")

# Paths that use SSE streaming — pass through without any wrapping
_STREAMING_SUFFIXES = ("/stream", "/logs")


def _is_streaming_path(path: str) -> bool:
    return any(path.endswith(s) for s in _STREAMING_SUFFIXES)


def setup_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


class LoggingMiddleware:
    """Pure ASGI logging middleware — no buffering."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        # Streaming paths: just log the request and pass through
        if _is_streaming_path(path):
            logger.info("Request: %s %s (streaming)", method, path)
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        logger.info("Request: %s %s", method, path)

        status_code = 0

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration = time.time() - start_time
        logger.info(
            "Response: %s %s - Status: %d - Duration: %.3fs",
            method, path, status_code, duration,
        )


class ErrorHandlingMiddleware:
    """Pure ASGI error-handling middleware — no buffering."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or _is_streaming_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: dict) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except ValueError as exc:
            if response_started:
                raise
            logger.warning("Validation error: %s", str(exc))
            resp = JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Validation Error", "detail": str(exc)},
            )
            await resp(scope, receive, send)
        except PermissionError as exc:
            if response_started:
                raise
            logger.warning("Permission denied: %s", str(exc))
            resp = JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "Permission Denied", "detail": str(exc)},
            )
            await resp(scope, receive, send)
        except FileNotFoundError as exc:
            if response_started:
                raise
            logger.warning("Resource not found: %s", str(exc))
            resp = JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "Not Found", "detail": str(exc)},
            )
            await resp(scope, receive, send)
        except Exception as exc:
            if response_started:
                raise
            logger.exception("Unhandled exception: %s", str(exc))
            resp = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "Internal Server Error",
                    "detail": "An unexpected error occurred",
                },
            )
            await resp(scope, receive, send)


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the application."""
    setup_cors(app)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(ErrorHandlingMiddleware)
