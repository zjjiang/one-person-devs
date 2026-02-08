"""Middleware for CORS, logging, and error handling."""

from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("opd.middleware")


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware.

    Args:
        app: FastAPI application instance
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure based on environment
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all requests and responses."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Process request and log details.

        Args:
            request: Incoming request
            call_next: Next middleware or route handler

        Returns:
            Response from the application
        """
        start_time = time.time()

        # Log request
        logger.info(
            "Request: %s %s",
            request.method,
            request.url.path,
        )

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Log response
        logger.info(
            "Response: %s %s - Status: %d - Duration: %.3fs",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )

        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware to handle exceptions and return consistent error responses."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Process request and handle exceptions.

        Args:
            request: Incoming request
            call_next: Next middleware or route handler

        Returns:
            Response from the application or error response
        """
        try:
            response = await call_next(request)
            return response
        except ValueError as exc:
            logger.warning("Validation error: %s", str(exc))
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "Validation Error",
                    "detail": str(exc),
                },
            )
        except PermissionError as exc:
            logger.warning("Permission denied: %s", str(exc))
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "Permission Denied",
                    "detail": str(exc),
                },
            )
        except FileNotFoundError as exc:
            logger.warning("Resource not found: %s", str(exc))
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={
                    "error": "Not Found",
                    "detail": str(exc),
                },
            )
        except Exception as exc:
            logger.exception("Unhandled exception: %s", str(exc))
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "Internal Server Error",
                    "detail": "An unexpected error occurred",
                },
            )


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the application.

    Args:
        app: FastAPI application instance
    """
    # Setup CORS
    setup_cors(app)

    # Add logging middleware
    app.add_middleware(LoggingMiddleware)

    # Add error handling middleware
    app.add_middleware(ErrorHandlingMiddleware)
