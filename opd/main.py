"""OPD v2 application entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from opd.capabilities.registry import CapabilityRegistry
from opd.config import load_config
from opd.db.models import StoryStatus
from opd.db.session import close_db, init_db
from opd.engine.orchestrator import Orchestrator
from opd.engine.stages.clarifying import ClarifyingStage
from opd.engine.stages.coding import CodingStage
from opd.engine.stages.designing import DesigningStage
from opd.engine.stages.planning import PlanningStage
from opd.engine.stages.preparing import PreparingStage
from opd.engine.stages.verifying import VerifyingStage
from opd.engine.state_machine import StateMachine
from opd.middleware import ErrorHandlingMiddleware, LoggingMiddleware

load_dotenv()

logger = logging.getLogger("opd")

# Global singleton
_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    assert _orchestrator is not None, "Orchestrator not initialized"
    return _orchestrator


def _setup_logging(config):
    log_dir = Path(config.logging.dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, config.logging.level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.handlers.RotatingFileHandler(
                log_dir / "opd.log", maxBytes=10_000_000, backupCount=5
            ),
        ],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan: initialize DB, capabilities, orchestrator."""
    global _orchestrator

    config = app.state.config
    _setup_logging(config)
    logger.info("Starting OPD v2...")

    # Database
    init_db(config.database.url)
    logger.info("Database initialized")

    # Capabilities
    registry = CapabilityRegistry()
    await registry.initialize_from_config(config.capabilities)
    logger.info("Capabilities initialized")

    # Orchestrator
    stages = {
        StoryStatus.preparing.value: PreparingStage(),
        StoryStatus.clarifying.value: ClarifyingStage(),
        StoryStatus.planning.value: PlanningStage(),
        StoryStatus.designing.value: DesigningStage(),
        StoryStatus.coding.value: CodingStage(),
        StoryStatus.verifying.value: VerifyingStage(),
    }
    sm = StateMachine()
    _orchestrator = Orchestrator(stages=stages, state_machine=sm, capabilities=registry)
    logger.info("Orchestrator ready")

    yield

    # Shutdown
    await registry.cleanup()
    await close_db()
    logger.info("OPD shutdown complete")


def create_app(config_path: str = "opd.yaml") -> FastAPI:
    config = load_config(config_path)

    app = FastAPI(title="OPD", version="2.0.0", lifespan=lifespan)
    app.state.config = config

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check
    @app.get("/api/health")
    async def health(orch: Orchestrator = Depends(get_orchestrator)):
        cap_names = list(config.capabilities.keys())
        health_results = await orch.capabilities.check_health(cap_names)
        return {
            "status": "ok" if all(h.healthy for h in health_results.values()) else "degraded",
            "capabilities": {
                name: {"healthy": h.healthy, "message": h.message}
                for name, h in health_results.items()
            },
        }

    # API routers
    from opd.api.projects import router as projects_router
    from opd.api.stories import router as stories_router
    from opd.api.webhooks import router as webhooks_router

    app.include_router(projects_router)
    app.include_router(stories_router)
    app.include_router(webhooks_router)

    # Web UI
    from opd.web.routes import router as web_router

    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory="opd/web/static"), name="static")

    # ASGI middleware (added last = runs first)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(ErrorHandlingMiddleware)

    return app


def cli():
    parser = argparse.ArgumentParser(prog="opd", description="OPD - AI Engineering Workflow")
    sub = parser.add_subparsers(dest="command")

    serve_parser = sub.add_parser("serve", help="Start the OPD server")
    serve_parser.add_argument("--host", default=None)
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.add_argument("--reload", action="store_true")
    serve_parser.add_argument("--config", default="opd.yaml")

    args = parser.parse_args()

    if args.command == "serve":
        config = load_config(args.config)
        host = args.host or config.server.host
        port = args.port or config.server.port
        uvicorn.run(
            "opd.main:create_app",
            factory=True,
            host=host,
            port=port,
            reload=args.reload,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    cli()
