# OPD (One Person Devs)

AI-driven engineering workflow orchestration platform integrating Claude Code into complete software iteration lifecycle.

## Project Overview

OPD orchestrates AI-powered software development workflows: requirement clarification → plan design → AI coding → code review → manual verification → merge. Built to streamline solo developer productivity with intelligent automation.

**Tech Stack**: FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 + MySQL (aiomysql) + Alembic + React 18 + TypeScript + Ant Design + Vite + claude-code-sdk + PyGithub/GitPython. Managed with `uv` (Python >= 3.11) + npm (frontend).

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

- **`orchestrator.py`** — The central coordinator (112 lines). Coordinates capabilities, state machine, and stage execution to drive a Story through its lifecycle. Delegates to stage implementations for actual work. Includes a pub/sub mechanism (`subscribe()`/`unsubscribe()`/`publish()`) using `asyncio.Queue` for real-time SSE streaming of AI messages to the frontend. Background task tracking via `_running_tasks` dict with `register_task()`/`unregister_task()` methods.
- **`state_machine.py`** — Status transitions defined in `VALID_TRANSITIONS` dict. Flow: `preparing → clarifying → planning → designing → coding → verifying → done`. Supports rollback to any prior stage. `ROLLBACK_ACTIONS` dict defines specific rollback action types: `verifying → coding` = "iterate", `verifying → designing` = "restart".
- **`context.py`** — Builds AI prompts (system prompt, coding prompt, plan prompt, revision prompt).
- **`workspace/`** — Package with 3 modules: `paths.py` (directory resolution, doc I/O), `scanner.py` (source code scanning), `git.py` (clone, branch management, pull_main, discard_branch). Re-exports all public functions via `__init__.py` including `story_slug()` for branch naming.
- **`hashing.py`** — SHA-256 input change detection. Computes hashes of stage inputs to skip unchanged AI stages, avoiding redundant API calls.

### Capability System (`opd/capabilities/` + `opd/providers/`)

All external dependencies are abstracted through `Provider` base class (`opd/capabilities/base.py`). `CapabilityRegistry` (`opd/capabilities/registry.py`) uses lazy-import factory pattern — built-in providers are stored as dotted-path strings in `_BUILTIN_PROVIDERS` and only imported on first use. Supports project-level capability overrides and global configuration.

**Architecture**: `opd/capabilities/` contains the registry and base classes, while `opd/providers/` contains actual provider implementations (ai/, scm/, doc/).

Current providers: `ai/claude_code`, `ai/ducc`, `scm/github`, `doc/local`.

### Dependency Injection

The `Orchestrator` is a singleton initialized during app lifespan (`main.py:lifespan`). API routes get it via `Depends(get_orch)` and DB sessions via `Depends(get_db)` — both defined in `opd/api/deps.py`.

### Real-time SSE Streaming

The coding/revising phases use Server-Sent Events for live AI message streaming. Architecture: `Orchestrator._publish()` pushes events to `asyncio.Queue` subscribers → `GET /api/stories/{id}/stream` endpoint yields SSE data → browser `EventSource` renders messages in a terminal-style console. The `/stream` endpoint replays historical messages first, then streams live events with 15s heartbeat keepalive.

**Important**: Middleware (`opd/middleware.py`) is implemented as pure ASGI classes (not `BaseHTTPMiddleware`) to avoid buffering `StreamingResponse`. Streaming paths (`/stream`, `/logs`) are passed through without any wrapping.

### Logging

Centralized in `logs/` directory via `_setup_logging()` in `main.py`. Two rotating log files: `opd.log` (all levels) and `error.log` (ERROR+ only). Configuration via `LoggingConfig` in `opd/config.py` and `logging` section in `opd.yaml`.

### API Routes (`opd/api/`)

- **`stories.py`** — Story core lifecycle: CRUD, confirm/reject, chat, SSE streaming, preflight.
- **`stories_tasks.py`** — Background AI task functions (`_start_ai_stage`, `_start_chat_ai`) with `pre_start` (clone/branch) and `post_complete` (commit/push/create PR) callbacks.
- **`stories_actions.py`** — State transition actions: rollback, iterate, restart, stop.
- **`stories_docs.py`** — Story document CRUD: `GET /api/stories/{id}/docs` (list), `GET /api/stories/{id}/docs/{filename}` (read), `PUT /api/stories/{id}/docs/{filename}` (write).
- **`projects.py`** — Project CRUD with workspace management. Includes sync endpoints: `POST /api/projects/{id}/sync-context` (trigger sync), `GET /api/projects/{id}/sync-stream` (SSE stream).
- **`capabilities.py`** — Capability health checks and configuration.
- **`capability_utils.py`** — Shared helpers for config masking/unmasking across capability endpoints.
- **`settings.py`** — Global capability configuration.
- **`users.py`** — User registration.
- **`webhooks.py`** — GitHub webhook handler.

### DB Session Pitfall

`get_db()` is an async generator that auto-commits after `yield`. **Using `return` inside `async for db in get_db()` skips the commit.** When you need to persist data (e.g., error messages) in error paths, use a separate `get_db()` session block.

### Frontend (`web/`)

Separate React 18 SPA with TypeScript + Ant Design + Vite. Communicates with backend via REST API and SSE for real-time streaming.

**Key Pages**:
- `StoryDetail.tsx` — Main story workflow UI (stage stepper, doc editors, AI console)
- `StoryForm.tsx` — Story creation form
- `ProjectDetail.tsx` — Project overview and story list
- `ProjectList.tsx` — Project listing
- `ProjectForm.tsx` — Project creation/edit form
- `ProjectSettings.tsx` — Project-level settings
- `GlobalSettings.tsx` — Global capability configuration

**Key Components**:
- `AIConsole.tsx` — Terminal-style SSE display for AI messages
- `SyncConsole.tsx` — Workspace sync streaming console
- `ChatPanel.tsx` — Document refinement chat
- `PrdEditor.tsx` — Markdown editor
- `StageStepper.tsx` — Visual workflow progress indicator
- `ClarifyQA.tsx` — Clarification Q&A component
- `AppLayout.tsx` — Main layout wrapper

### Testing

Tests use `pytest-asyncio` with `asyncio_mode = "auto"`. Fixtures in `tests/conftest.py` provide mock domain objects (`SimpleNamespace`-based) and FastAPI test clients (sync via `TestClient`, async via `httpx.AsyncClient`). No real DB required for unit tests.

## Configuration

- `opd.yaml` — Main config (server, providers, workspace, logging). Supports `${ENV_VAR}` interpolation.
- `.env` — Environment variables (GITHUB_TOKEN, ANTHROPIC_API_KEY). Loaded by `python-dotenv` at import time in `main.py`.
- Ruff: `line-length = 100`, `target-version = "py311"`.

## Key Directories

```
opd/
├── api/                    # FastAPI routers and endpoints
│   ├── stories.py          # Story lifecycle CRUD, SSE streaming
│   ├── stories_tasks.py    # Background AI task functions with callbacks
│   ├── stories_actions.py  # State transition actions
│   ├── stories_docs.py     # Document CRUD endpoints
│   ├── projects.py         # Project management + sync endpoints
│   ├── capabilities.py     # Capability health checks
│   ├── settings.py         # Global configuration
│   ├── users.py            # User registration
│   └── webhooks.py         # GitHub webhook handler
├── engine/                 # Core orchestration engine
│   ├── orchestrator.py     # Central coordinator (112 lines)
│   ├── state_machine.py    # Status transition logic
│   ├── context.py          # AI prompt builder
│   ├── hashing.py          # Input change detection
│   ├── stages/             # Stage implementations
│   └── workspace/          # Git/file operations
├── capabilities/           # Capability system
│   ├── base.py             # Provider and Capability base classes
│   ├── registry.py         # CapabilityRegistry
│   └── ...
├── providers/              # Provider implementations
│   ├── ai/                 # AI providers (claude_code, ducc)
│   ├── scm/                # SCM providers (github)
│   └── doc/                # Doc providers (local)
├── db/                     # Database layer
│   ├── models.py           # SQLAlchemy models
│   └── session.py          # DB session management
├── config.py               # Configuration loader
├── middleware.py           # ASGI middleware
└── main.py                 # Application entry point

web/
├── src/
│   ├── pages/              # Route pages
│   │   ├── StoryDetail.tsx # Main story workflow UI
│   │   ├── StoryForm.tsx   # Story creation
│   │   ├── ProjectDetail.tsx
│   │   ├── ProjectList.tsx
│   │   ├── ProjectForm.tsx
│   │   ├── ProjectSettings.tsx
│   │   └── GlobalSettings.tsx
│   ├── components/         # Reusable components
│   │   ├── AIConsole.tsx   # Terminal-style SSE display
│   │   ├── SyncConsole.tsx # Workspace sync streaming
│   │   ├── ChatPanel.tsx   # Document refinement chat
│   │   ├── PrdEditor.tsx   # Markdown editor
│   │   ├── StageStepper.tsx
│   │   ├── ClarifyQA.tsx   # Clarification Q&A
│   │   └── AppLayout.tsx   # Main layout wrapper
│   └── main.tsx            # React entry point
└── public/                 # Static assets

tests/                      # pytest test suite
docs/                       # Story documentation archives
```

## Data Model

### Core Entities

- **User** — Authentication and ownership
- **Project** — Repository, workspace, rules, skills, capability configs
- **Story** — Feature request with status, rounds, documents (PRD, designs, reports)
- **Round** — Iteration cycle with branch, PRs, AI messages
- **Task** — Decomposed work items from planning stage
- **Clarification** — Q&A pairs during clarifying stage
- **Rule** — Project-specific coding rules (coding, architecture, testing, git, forbidden)
- **Skill** — Custom commands with triggers (auto_after_coding, auto_before_pr, manual)

### Story Lifecycle States

```
preparing → clarifying → planning → designing → coding → verifying → done
```

Each state has a corresponding stage handler in `opd/engine/stages/`. Rollback supported to any prior stage.

## Coding Standards

### Immutability

ALWAYS create new objects, NEVER mutate existing ones. Use immutable patterns for data updates.

### Error Handling

- Handle errors explicitly at every level
- Provide user-friendly messages in UI-facing code
- Log detailed context on server side
- Never silently swallow errors

### Async Patterns

- Use `async`/`await` consistently
- Background tasks tracked in `Orchestrator._running_tasks`
- DB sessions via `async for db in get_db()` — avoid `return` inside loop (skips commit)

### File Organization

- Many small files > few large files
- 200-400 lines typical, 800 max
- High cohesion, low coupling
- Organize by feature/domain, not by type

### Testing

- Use `pytest-asyncio` with `asyncio_mode = "auto"`
- Mock domain objects with `SimpleNamespace`
- No real DB required for unit tests
- Fixtures in `tests/conftest.py`

## Common Pitfalls

1. **DB Session Commit**: Using `return` inside `async for db in get_db()` skips auto-commit. Use separate session block for error paths.
2. **Middleware Buffering**: Use pure ASGI middleware (not `BaseHTTPMiddleware`) to avoid buffering `StreamingResponse`.
3. **Capability Lazy Loading**: Capabilities are lazy-loaded on first use. Register in `_BUILTIN_PROVIDERS` before use.
4. **SSE Keepalive**: Stream endpoints need 15s heartbeat to prevent timeout.
5. **Capability vs Provider Confusion**: `opd/capabilities/` contains the registry system, `opd/providers/` contains implementations. Don't confuse the two.

## Technical Debt & Improvement Areas

### Security (CRITICAL)
- **Command Injection Risk**: `repo_url` and branch names not validated before git commands (`opd/api/projects.py`, `opd/engine/workspace/git.py`). Validate URL format (https only) and branch names (alphanumeric + hyphens).
- **Missing Authentication**: No authentication/authorization on API endpoints. Anyone can access/modify any project. Add auth middleware and per-resource authorization.
- **Rate Limiting**: No rate limiting on AI endpoints. Add rate limiting middleware to prevent abuse and cost explosion.

### Architecture
- **SSE Pub/Sub Scalability**: Current in-memory pub/sub in `Orchestrator` won't scale across multiple instances. Consider Redis pub/sub for multi-instance deployments.
- **Background Task Tracking**: `_running_tasks` dict is in-memory only. For horizontal scaling, move to Redis or database-backed task queue.
- **Circular Dependencies**: `opd/api/projects.py` line 96 imports from `opd.main`, creating circular dependency risk. Pass orchestrator as parameter or use dependency injection.
- **Missing Task Manager**: No abstraction for background task lifecycle management. Create `TaskManager` class with proper lifecycle hooks.
- **Tight Coupling**: Background tasks directly manipulate DB models. Introduce service layer to abstract DB operations.
- **Blocking Subprocess Calls**: `opd/providers/scm/github.py` uses blocking `subprocess.run()` calls. Wrap in `asyncio.create_subprocess_exec()`.

### Code Quality
- **Duplicated DB Session Pattern**: Pattern of creating session_factory and querying Story/Project repeated 7+ times in `opd/api/stories_tasks.py` and `opd/api/projects.py`. Extract into reusable helper function.
- **Overly Long Functions**: `_start_ai_stage` (135 lines), `_launch_clone` (60 lines), `_launch_sync_context` (80 lines) violate SRP. Break into smaller functions.
- **Duplicated Error Handling**: Git operation error handling repeated 3+ times. Wrap in helper with consistent error handling.
- **Inconsistent Exception Handling**: Some places silently swallow exceptions, others log. Standardize: always log exceptions, never use bare `except Exception: pass`.
- **Missing Docstrings**: Many helper functions lack docstrings (`opd/api/capability_utils.py`, complex algorithms in `opd/engine/workspace/git.py`).

### API & Performance
- **N+1 Query Risk**: Story listing iterates to count stories instead of using SQL COUNT (`opd/api/projects.py` lines 147-160).
- **Inefficient Active Round Lookup**: Linear O(n) search through all rounds. Add `story.active_round_id` foreign key or use DB query with filter.
- **Unbounded File Reading**: `claude_md.read_text()` reads entire file into memory (`opd/engine/context.py` line 75). Add size limit or streaming read.
- **Missing Indexes**: Verify indexes on: `stories.project_id`, `stories.status`, `rounds.story_id`, `rounds.status`, `ai_messages.round_id`, `clarifications.story_id`.
- **API Documentation**: Missing OpenAPI documentation for some endpoints (stories_docs, project sync).
- **Error Response Consistency**: Some endpoints return `{"error": "..."}`, others raise `HTTPException`. Standardize on HTTPException.

### Frontend
- **State Management**: Prop drilling in some components (StoryDetail, ProjectDetail). Consider React Context or state management library.
- **Component Reusability**: Some components have duplicated logic. Extract shared hooks and utilities.
- **Type Safety**: Some `any` types in TypeScript. Improve type coverage.

### Testing
- **E2E Test Coverage**: Missing E2E tests for critical workflows (story creation → coding → merge).
- **Integration Tests**: Limited integration tests for API endpoints with real DB. No integration tests for SSE streaming.
- **Frontend Tests**: No frontend component tests. Add React Testing Library tests.
- **Error Recovery Tests**: No tests for error recovery in background tasks (DB errors, git errors, AI errors).
- **Concurrency Tests**: No tests for concurrent story execution. Race conditions possible.
- **Edge Case Tests**: No tests for workspace conflicts (dirty workspace during branch creation).

### DevOps
- **Docker Support**: No Dockerfile or docker-compose.yml for containerized deployment.
- **CI/CD Pipeline**: No GitHub Actions or CI/CD configuration.
- **Environment Management**: `.env` file not documented. Add `.env.example`.

### Documentation
- **API Endpoint Documentation**: Missing detailed API documentation. Consider adding OpenAPI/Swagger UI.
- **Provider Development Guide**: No guide for adding new providers.
- **Deployment Guide**: Missing production deployment instructions.
- **Function Docstrings**: Many helper functions lack docstrings, especially in `opd/api/capability_utils.py` and complex algorithms in `opd/engine/workspace/git.py`.

## Priority Recommendations

### Immediate (Security - CRITICAL)
1. Add input validation for `repo_url` and branch names to prevent command injection
2. Add authentication/authorization to all API endpoints
3. Fix blocking subprocess calls in `GitHubProvider`
4. Add rate limiting middleware for AI endpoints

### High Priority (Architecture & Quality)
5. Extract background task DB session pattern into reusable helper
6. Break up overly long functions (`_start_ai_stage`, `_launch_clone`, `_launch_sync_context`)
7. Create `TaskManager` abstraction for background task lifecycle
8. Fix circular dependency in `opd/api/projects.py`
9. Standardize error handling (no silent exceptions)
10. Add docstrings to all public functions

### Medium Priority (Testing & Performance)
11. Add integration tests for SSE streaming
12. Add concurrency and error recovery tests
13. Optimize N+1 queries and active round lookup
14. Add size limits for file reading operations
15. Verify database indexes exist

### Low Priority (Cleanup)
16. Consolidate duplicated document resolution logic
17. Standardize error response formats
18. Add E2E tests for full workflows
19. Improve frontend state management
20. Add Docker and CI/CD configuration

## Development Workflow

1. **Feature Development**: Create Story → AI generates PRD → Review/confirm → AI plans → AI designs → AI codes → Manual verification → Merge
2. **Iteration**: Use rollback actions (iterate from verifying→coding, restart from verifying→designing) to refine at any stage
3. **Real-time Monitoring**: SSE streaming shows live AI progress in terminal-style console
4. **Multi-round Support**: Each iteration creates new Round with separate branch and PR
5. **Workspace Sync**: Use project sync endpoints to update context from repository changes

## Known Issues & Workarounds

### DB Session Commit Pitfall
Using `return` inside `async for db in get_db()` skips auto-commit. When persisting data in error paths, use a separate `get_db()` session block.

### Middleware Buffering
Use pure ASGI middleware (not `BaseHTTPMiddleware`) to avoid buffering `StreamingResponse`. Streaming paths (`/stream`, `/logs`) must be passed through without wrapping.

### Capability Lazy Loading
Capabilities are lazy-loaded on first use. Register in `_BUILTIN_PROVIDERS` before use to avoid import errors.

### SSE Keepalive
Stream endpoints need 15s heartbeat to prevent timeout. Already implemented in `/stream` endpoints.

### Capability vs Provider Confusion
`opd/capabilities/` contains the registry system, `opd/providers/` contains implementations. Don't confuse the two when adding new capabilities.
