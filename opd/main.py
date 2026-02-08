"""OPD application entry point.

Provides the FastAPI application factory and the ``opd serve`` CLI command.
"""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from opd.api.deps import init_orchestrator
from opd.api.projects import router as projects_router
from opd.api.routes import router as health_router
from opd.api.stories import router as stories_router
from opd.api.webhooks import router as webhooks_router
from opd.config import OPDConfig
from opd.db.session import init_db
from opd.middleware import setup_middleware

logger = logging.getLogger("opd")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_WEB_DIR = Path(__file__).resolve().parent / "web"
_STATIC_DIR = _WEB_DIR / "static"
_TEMPLATES_DIR = _WEB_DIR / "templates"

# Jinja2 templates (available for import by other modules)
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialise DB and providers on startup."""
    logger.info("Starting OPD server ...")

    # Initialise database tables
    await init_db()
    logger.info("Database initialised")

    # Load config and build provider instances
    config = OPDConfig.load()
    providers = await _build_providers(config)

    # Initialise the orchestrator singleton
    init_orchestrator(providers, workspace_dir=config.workspace.base_dir)
    logger.info("Orchestrator ready")

    yield

    # Cleanup providers
    for name, provider in providers.items():
        if hasattr(provider, "cleanup"):
            await provider.cleanup()
    logger.info("OPD server shut down")


async def _build_providers(config: OPDConfig) -> dict:
    """Instantiate providers from configuration.

    Returns a dict mapping provider names to provider instances.
    Providers that are not configured are omitted.
    """
    from opd.providers.registry import ProviderRegistry

    registry = ProviderRegistry()
    providers: dict = {}

    for name in ("ai", "scm", "ci", "sandbox", "notification",
                 "requirement", "document"):
        prov_config = getattr(config.providers, name)
        if prov_config.type:
            try:
                providers[name] = await registry.create(
                    name, prov_config.type, prov_config.config
                )
                logger.info("Loaded provider: %s/%s", name, prov_config.type)
            except (KeyError, RuntimeError) as exc:
                logger.warning("Failed to load provider %s/%s: %s", name, prov_config.type, exc)

    logger.info(
        "Providers loaded: %s",
        list(providers.keys()) if providers else "(none - using stubs)",
    )
    return providers


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="OPD - One Person Devs",
        description="AI-powered engineering workflow orchestration platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Setup middleware (CORS, logging, error handling)
    setup_middleware(app)

    # Include API routers
    app.include_router(health_router)  # Health check and root endpoints
    app.include_router(projects_router)
    app.include_router(stories_router)
    app.include_router(webhooks_router)

    # Include web UI router (imported here to avoid circular imports)
    from opd.web.routes import router as web_router
    app.include_router(web_router)

    # Mount static files (CSS, JS, images)
    if _STATIC_DIR.exists():
        app.mount(
            "/static",
            StaticFiles(directory=str(_STATIC_DIR)),
            name="static",
        )

    return app


# The application instance (used by uvicorn: ``uvicorn opd.main:app``)
app = create_app()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cli() -> None:
    """CLI entry point: ``opd serve``."""
    parser = argparse.ArgumentParser(
        prog="opd",
        description="OPD - AI-powered engineering workflow orchestration",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- serve ---
    serve_parser = subparsers.add_parser(
        "serve", help="Start the OPD web server"
    )
    serve_parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Bind host (default: from opd.yaml or 0.0.0.0)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port (default: from opd.yaml or 8080)",
    )
    serve_parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable auto-reload for development",
    )
    serve_parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to opd.yaml config file",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "serve":
        _run_serve(args)


def _run_serve(args: argparse.Namespace) -> None:
    """Run the uvicorn server."""
    import uvicorn

    config = OPDConfig.load(args.config)
    host = args.host or config.server.host
    port = args.port or config.server.port

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Starting OPD on %s:%d", host, port)
    uvicorn.run(
        "opd.main:app",
        host=host,
        port=port,
        reload=args.reload,
    )


if __name__ == "__main__":
    cli()
