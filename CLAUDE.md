# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OPD (One Person Devs) — AI-driven engineering workflow orchestration platform. Integrates Claude Code's coding capabilities into a complete software engineering iteration lifecycle: requirement clarification → plan design → AI coding → code review → manual verification → merge.

**Tech stack**: FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 + MySQL (aiomysql) + Alembic + React 18 + TypeScript + Ant Design + Vite + claude-code-sdk + PyGithub/GitPython. Managed with `uv` (Python >= 3.11) + npm (frontend).

## Commands

```bash
# Start server (default port 8765)
uv run python -m opd.main serve
uv run opd serve                         # equivalent CLI entry point
uv run opd serve --reload                # dev mode with auto-reload

# Frontend dev server
cd web && npm run dev                    # Vite dev server (port 5173)
cd web && npm run build                  # production build

# Database
uv run alembic upgrade head              # run migrations
uv run alembic revision --autogenerate -m "description"  # create migration

# Tests
uv run pytest tests/                     # all tests
uv run pytest tests/test_state_machine.py                # single file
uv run pytest tests/test_state_machine.py::test_name     # single test
uv run pytest -x                         # stop on first failure

# Lint
uv run ruff check opd/                   # check
uv run ruff check --fix opd/             # auto-fix

# Install dependencies
uv sync --extra ai --extra dev           # backend
cd web && npm install                    # frontend
```

## Architecture

### Request Flow

HTTP requests → FastAPI routers (`opd/api/`) → `Orchestrator` (singleton via `opd/api/deps.py`) → Providers + DB. Frontend is a separate React SPA (`web/`) communicating via REST API + SSE.

### Core Engine (`opd/engine/`)

- **`orchestrator.py`** — The central file. Coordinates providers, state machine, and DB to drive a Story through its lifecycle. Long-running AI operations run as background `asyncio.Task`s tracked in `_running_tasks` dict. The `_run_ai_background()` method supports `pre_start` (clone/branch) and `post_complete` (commit/push/create PR) callbacks. Includes a pub/sub mechanism (`subscribe()`/`unsubscribe()`/`_publish()`) using `asyncio.Queue` for real-time SSE streaming of AI messages to the frontend.
- **`state_machine.py`** — Status transitions defined in `VALID_TRANSITIONS` dict. Flow: `preparing → clarifying → planning → designing → coding → verifying → done`. Supports rollback to any prior stage. `ROLLBACK_ACTIONS` dict maps specific transitions to action types (iterate/restart).
- **`context.py`** — Builds AI prompts (system prompt, coding prompt, plan prompt, revision prompt).
- **`workspace.py`** — Git workspace operations: branch management, document file I/O (PRD, plan, design docs stored in workspace).
- **`hashing.py`** — SHA-256 input change detection. Computes hashes of stage inputs to skip unchanged AI stages, avoiding redundant API calls.

### Provider System (`opd/providers/`)

All external dependencies are abstracted through `Provider` base class (`base.py`). `ProviderRegistry` (`registry.py`) uses lazy-import factory pattern — built-in providers are stored as dotted-path strings in `_BUILTIN_PROVIDERS` and only imported on first use. Supports project-level capability overrides and global configuration. To add a new provider: implement the base class, register in `_BUILTIN_PROVIDERS`, configure `type` in `opd.yaml`.

Current providers: `ai/claude_code`, `ai/ducc`, `scm/github`, `ci/github_actions`, `doc/local`, `doc/notion`, `sandbox/docker_local`, `notification/web`.

### Dependency Injection

The `Orchestrator` is a singleton initialized during app lifespan (`main.py:lifespan`). API routes get it via `Depends(get_orch)` and DB sessions via `Depends(get_db)` — both defined in `opd/api/deps.py`.

### Real-time SSE Streaming

The coding/revising phases use Server-Sent Events for live AI message streaming. Architecture: `Orchestrator._publish()` pushes events to `asyncio.Queue` subscribers → `GET /api/stories/{id}/stream` endpoint yields SSE data → browser `EventSource` renders messages in a terminal-style console. The `/stream` endpoint replays historical messages first, then streams live events with 15s heartbeat keepalive.

**Important**: Middleware (`opd/middleware.py`) is implemented as pure ASGI classes (not `BaseHTTPMiddleware`) to avoid buffering `StreamingResponse`. Streaming paths (`/stream`, `/logs`) are passed through without any wrapping.

### Logging

Centralized in `logs/` directory via `_setup_logging()` in `main.py`. Two rotating log files: `opd.log` (all levels) and `error.log` (ERROR+ only). Configuration via `LoggingConfig` in `opd/config.py` and `logging` section in `opd.yaml`.

### API Routes (`opd/api/`)

- **`stories.py`** — Story lifecycle: CRUD, confirm/rollback/iterate/restart actions, SSE streaming, chat for document refinement.
- **`projects.py`** — Project CRUD with workspace management.
- **`capabilities.py`** — Capability health checks and configuration.
- **`settings.py`** — Global capability configuration.
- **`users.py`** — User registration.
- **`webhooks.py`** — GitHub webhook handler.

### DB Session Pitfall

`get_db()` is an async generator that auto-commits after `yield`. **Using `return` inside `async for db in get_db()` skips the commit.** When you need to persist data (e.g., error messages) in error paths, use a separate `get_db()` session block.

### Frontend (`web/`)

Separate React 18 SPA with TypeScript + Ant Design + Vite. Communicates with backend via REST API and SSE for real-time streaming. Key pages: `StoryDetail` (stage stepper, doc editors, AI console), `ProjectDetail`, `GlobalSettings`. Components include `AIConsole` (terminal-style SSE display), `ChatPanel` (document refinement chat), `PrdEditor` (markdown editor).

### Testing

Tests use `pytest-asyncio` with `asyncio_mode = "auto"`. Fixtures in `tests/conftest.py` provide mock domain objects (`SimpleNamespace`-based) and FastAPI test clients (sync via `TestClient`, async via `httpx.AsyncClient`). No real DB required for unit tests.

## Configuration

- `opd.yaml` — Main config (server, providers, workspace, logging). Supports `${ENV_VAR}` interpolation.
- `.env` — Environment variables (GITHUB_TOKEN, ANTHROPIC_API_KEY). Loaded by `python-dotenv` at import time in `main.py`.
- Ruff: `line-length = 100`, `target-version = "py311"`.
