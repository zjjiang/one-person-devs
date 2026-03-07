# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# OPD (One Person Devs)

AI 驱动的工程迭代流程编排平台，将 Claude Code 集成到完整的软件迭代生命周期中。

## 项目概述

OPD 编排 AI 驱动的软件开发工作流：需求澄清 → 方案规划 → AI 编码 → 代码审查 → 人工验证 → 合并。旨在通过智能自动化提升独立开发者的生产力。

**技术栈**: FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 + MySQL (aiomysql) + Alembic + React 18 + TypeScript + Ant Design + Vite + claude-code-sdk + PyGithub/GitPython。使用 `uv` (Python >= 3.11) + npm 管理依赖。

## 常用命令

```bash
# 启动服务器（默认端口 8765）
uv run python -m opd.main serve
uv run opd serve                         # 等效的 CLI 入口
uv run opd serve --reload                # 开发模式，自动重载

# 前端开发服务器
cd web && npm run dev                    # Vite 开发服务器（端口 5173）
cd web && npm run build                  # 生产构建

# 数据库
uv run alembic upgrade head              # 运行迁移
uv run alembic revision --autogenerate -m "description"  # 创建迁移

# 测试
uv run pytest tests/                     # 所有测试
uv run pytest tests/test_state_machine.py                # 单个文件
uv run pytest tests/test_state_machine.py::test_name     # 单个测试
uv run pytest -x                         # 遇到第一个失败即停止

# Lint
uv run ruff check opd/                   # 检查
uv run ruff check --fix opd/             # 自动修复

# 安装依赖
uv sync --extra ai --extra dev           # 后端
cd web && npm install                    # 前端
```

## 项目架构

### 请求流

HTTP 请求 → FastAPI 路由 (`opd/api/`) → `Orchestrator`（通过 `opd/api/deps.py` 单例注入）→ Providers + DB。前端是独立的 React SPA (`web/`)，通过 REST API + SSE 通信。

### 核心引擎 (`opd/engine/`)

- **`orchestrator.py`** — 中央协调器（112 行）。协调 capabilities、状态机和阶段执行，驱动 Story 完成生命周期。委托给阶段实现执行实际工作。包含发布/订阅机制（`subscribe()`/`unsubscribe()`/`publish()`），使用 `asyncio.Queue` 实现 AI 消息的实时 SSE 流式传输到前端。通过 `_running_tasks` 字典跟踪后台任务，提供 `register_task()`/`unregister_task()` 方法。
- **`state_machine.py`** — 状态转换定义在 `VALID_TRANSITIONS` 字典中。流程：`preparing → clarifying → planning → designing → coding → verifying → done`。支持回退到任意前置阶段。`ROLLBACK_ACTIONS` 字典定义特定回退动作类型：`verifying → coding` = "iterate"，`verifying → designing` = "restart"。
- **`context.py`** — 构建 AI 提示词（系统提示、编码提示、规划提示、修订提示）。
- **`workspace/`** — 包含 3 个模块的包：`paths.py`（目录解析、文档 I/O）、`scanner.py`（源代码扫描）、`git.py`（克隆、分支管理、pull_main、discard_branch）。通过 `__init__.py` 重新导出所有公共函数，包括用于分支命名的 `story_slug()`。
- **`hashing.py`** — SHA-256 输入变更检测。计算阶段输入的哈希值以跳过未变更的 AI 阶段，避免冗余 API 调用。
- **`notify.py`** — 通知服务。`send_notification()` 函数负责 fan-out：写入 DB（站内信）+ 调用外部 providers（飞书等）。支持 `doc_content`/`doc_filename` 参数，有文档时通过飞书文件上传 API 发送附件。
- **`workspace_lock.py`** — 工作区互斥锁。确保同一项目同时只有一个 Story 在 coding 阶段。`acquire_workspace_lock()`/`release_workspace_lock()`/`check_workspace_lock()` 操作 Project 表的 `locked_by_story_id` 字段。
- **`memory/`** — CLAUDE.md 自动生成管道。包含 3 个模块：`extractor.py`（AST 解析 Python 文件提取类/函数定义，非 Python 文件取前 N 行，按目录重要性排序）、`generator.py`（按模块类别分组 snippets，调用 AI 生成 2-3 段描述）、`assembler.py`（将 AI 描述 + snippets + 项目元数据组装为完整 CLAUDE.md）。在 `opd/api/projects.py` 中通过 `sync-context` 端点触发，支持全量生成和增量更新。

### Capability 系统 (`opd/capabilities/` + `opd/providers/`)

所有外部依赖通过 `Provider` 基类抽象（`opd/capabilities/base.py`）。`CapabilityRegistry`（`opd/capabilities/registry.py`）使用懒加载工厂模式 — 内置 providers 以点分路径字符串存储在 `_BUILTIN_PROVIDERS` 中，仅在首次使用时导入。支持项目级 capability 覆盖和全局配置。

**架构**: `opd/capabilities/` 包含注册表和基类，`opd/providers/` 包含实际 provider 实现（ai/、scm/、doc/）。

当前 providers: `ai/claude_code`、`ai/ducc`、`scm/github`、`doc/local`、`notification/inbox`、`notification/feishu`。

### 依赖注入

`Orchestrator` 是在应用生命周期期间初始化的单例（`main.py:lifespan`）。API 路由通过 `Depends(get_orch)` 获取它，通过 `Depends(get_db)` 获取 DB 会话 — 两者都在 `opd/api/deps.py` 中定义。

### 实时 SSE 流式传输

编码/修订阶段使用服务器发送事件（SSE）进行实时 AI 消息流式传输。架构：`Orchestrator._publish()` 将事件推送到 `asyncio.Queue` 订阅者 → `GET /api/stories/{id}/stream` 端点生成 SSE 数据 → 浏览器 `EventSource` 在终端风格控制台中渲染消息。`/stream` 端点首先重放历史消息，然后流式传输实时事件，带有 15 秒心跳保活。

**重要**: 中间件（`opd/middleware.py`）实现为纯 ASGI 类（而非 `BaseHTTPMiddleware`），以避免缓冲 `StreamingResponse`。流式路径（`/stream`、`/logs`）无需任何包装即可通过。

### 日志

通过 `main.py` 中的 `_setup_logging()` 集中在 `logs/` 目录。两个轮转日志文件：`opd.log`（所有级别）和 `error.log`（仅 ERROR+）。通过 `opd/config.py` 中的 `LoggingConfig` 和 `opd.yaml` 中的 `logging` 部分配置。

### API 路由 (`opd/api/`)

- **`stories.py`** — Story 核心生命周期：CRUD、确认/拒绝、聊天、SSE 流式传输、预检。
- **`stories_tasks.py`** — 后台 AI 任务函数（`_start_ai_stage`、`_start_chat_ai`），带有 `pre_start`（克隆/分支）和 `post_complete`（提交/推送/创建 PR）回调。
- **`stories_actions.py`** — 状态转换动作：回退、迭代、重启、停止。
- **`stories_docs.py`** — Story 文档 CRUD：`GET /api/stories/{id}/docs`（列表）、`GET /api/stories/{id}/docs/{filename}`（读取）、`PUT /api/stories/{id}/docs/{filename}`（写入）、`GET /api/stories/{id}/docs/{filename}/download`（下载 .md 文件）、`POST /api/stories/{id}/docs/upload`（上传 .md 文件替换文档）。
- **`projects.py`** — 项目 CRUD 及工作区管理。包含同步端点：`POST /api/projects/{id}/sync-context`（触发同步）、`GET /api/projects/{id}/sync-stream`（SSE 流）。
- **`capabilities.py`** — Capability 健康检查和配置。
- **`capability_utils.py`** — 跨 capability 端点的配置掩码/解掩码共享辅助函数。
- **`settings.py`** — 全局 capability 配置。
- **`notifications.py`** — 通知 API：`GET /api/notifications`（列表）、`GET /api/notifications/unread-count`（未读数）、`POST /api/notifications/{id}/read`（标记已读）、`POST /api/notifications/read-all`（全部已读）。
- **`logs.py`** — 全局日志查看：`GET /api/logs/stream`（SSE 实时日志流）、`GET /api/logs/files`（日志文件列表）。
- **`users.py`** — 用户注册。
- **`webhooks.py`** — GitHub webhook 处理器。

### DB 会话陷阱

`get_db()` 是一个异步生成器，在 `yield` 后自动提交。**在 `async for db in get_db()` 内使用 `return` 会跳过提交。** 当需要在错误路径中持久化数据（例如错误消息）时，使用单独的 `get_db()` 会话块。

### 前端 (`web/`)

独立的 React 18 SPA，使用 TypeScript + Ant Design + Vite。通过 REST API 和 SSE 与后端通信以实现实时流式传输。

**关键页面**:
- `StoryDetail.tsx` — 主 story 工作流 UI（阶段步进器、文档编辑器、AI 控制台）
- `StoryForm.tsx` — Story 创建表单
- `ProjectDetail.tsx` — 项目概览和 story 列表
- `ProjectList.tsx` — 项目列表
- `ProjectForm.tsx` — 项目创建/编辑表单
- `ProjectSettings.tsx` — 项目级设置
- `GlobalSettings.tsx` — 全局 capability 配置

**关键组件**:
- `AIConsole.tsx` — 终端风格的 SSE 显示，用于 AI 消息
- `SyncConsole.tsx` — 工作区同步流式控制台
- `ChatPanel.tsx` — 文档优化聊天
- `PrdEditor.tsx` — Markdown 编辑器
- `StageStepper.tsx` — 可视化工作流进度指示器
- `ClarifyQA.tsx` — 澄清问答组件
- `AppLayout.tsx` — 主布局包装器

### 测试

测试使用 `pytest-asyncio`，`asyncio_mode = "auto"`。`tests/conftest.py` 中的 fixtures 提供模拟域对象（基于 `SimpleNamespace`）和 FastAPI 测试客户端（通过 `TestClient` 同步，通过 `httpx.AsyncClient` 异步）。单元测试不需要真实 DB。

## 配置

- `opd.yaml` — 主配置（服务器、providers、工作区、日志）。支持 `${ENV_VAR}` 插值。
- `.env` — 环境变量（GITHUB_TOKEN、ANTHROPIC_API_KEY）。在 `main.py` 导入时由 `python-dotenv` 加载。
- Ruff: `line-length = 100`，`target-version = "py311"`。

## 关键目录

```
opd/                        # 后端主包
├── api/                    # FastAPI 路由和端点
├── engine/                 # 核心编排引擎（orchestrator、状态机、阶段、workspace、memory）
├── capabilities/           # Capability 注册表和基类
├── providers/              # Provider 实现（ai/、scm/、doc/、notification/）
├── db/                     # SQLAlchemy 模型和会话管理
├── config.py               # 配置加载器
├── middleware.py           # ASGI 中间件
└── main.py                 # 应用入口点

web/src/                    # React 18 SPA（TypeScript + Ant Design + Vite）
├── pages/                  # 路由页面（StoryDetail、ProjectDetail 等）
└── components/             # 可复用组件（AIConsole、ChatPanel 等）

tests/                      # pytest 测试套件
migrations/                 # Alembic 数据库迁移
```

## 数据模型

### 核心实体

- **User** — 认证和所有权
- **Project** — 仓库、工作区、规则、技能、capability 配置
- **Story** — 功能请求，包含状态、轮次、文档（PRD、设计、报告）
- **Round** — 迭代周期，包含分支、PR、AI 消息
- **Task** — 从规划阶段分解的工作项
- **Clarification** — 澄清阶段的问答对
- **Rule** — 项目特定编码规则（编码、架构、测试、git、禁止）
- **Skill** — 自定义命令，带触发器（auto_after_coding、auto_before_pr、manual）
- **Notification** — 通知记录（站内信），包含 type、title、message、link、read 状态

### Story 生命周期状态

```
preparing → clarifying → planning → designing → coding → verifying → done
```

每个状态在 `opd/engine/stages/` 中都有相应的阶段处理器。支持回退到任意前置阶段。

## 编码规范

### 不可变性

始终创建新对象，永不修改现有对象。使用不可变模式进行数据更新。

### 错误处理

- 在每个级别显式处理错误
- 在面向 UI 的代码中提供用户友好的消息
- 在服务器端记录详细上下文
- 永不静默吞噬错误

### 异步模式

- 一致使用 `async`/`await`
- 在 `Orchestrator._running_tasks` 中跟踪后台任务
- 通过 `async for db in get_db()` 获取 DB 会话 — 避免在循环内使用 `return`（会跳过提交）

### 文件组织

- 多个小文件 > 少数大文件
- 典型 200-400 行，最多 800 行
- 高内聚、低耦合
- 按功能/领域组织，而非按类型

### 测试

- 使用 `pytest-asyncio`，`asyncio_mode = "auto"`
- 使用 `SimpleNamespace` 模拟域对象
- 单元测试不需要真实 DB
- Fixtures 在 `tests/conftest.py` 中

### Git 工作流

- **提交前确认**: 完成代码修改和测试后，先 `git add` 和 `git commit`，但**不要立即 push**
- **等待用户确认**: 告知用户已提交的内容，等待用户确认后再执行 `git push`
- **提交信息**: 使用清晰的 commit message，遵循 conventional commits 格式（feat/fix/refactor/docs 等）

## 常见陷阱

1. **DB 会话提交**: 在 `async for db in get_db()` 内使用 `return` 会跳过自动提交。对于错误路径，使用单独的会话块。
2. **中间件缓冲**: 使用纯 ASGI 中间件（而非 `BaseHTTPMiddleware`）以避免缓冲 `StreamingResponse`。
3. **Capability 懒加载**: Capabilities 在首次使用时懒加载。使用前在 `_BUILTIN_PROVIDERS` 中注册。
4. **SSE 保活**: 流式端点需要 15 秒心跳以防止超时。
5. **Capability vs Provider 混淆**: `opd/capabilities/` 包含注册表系统，`opd/providers/` 包含实现。不要混淆两者。
6. **工作区互斥锁**: 同一项目同时只能有一个 Story 在 coding 阶段。`workspace_lock.py` 通过 Project 表的 `locked_by_story_id` 字段实现。
7. **CLAUDE.md 污染防护**: `context.py` 中的 `_read_claude_md()` 校验工作区 CLAUDE.md 内容：必须以 markdown 标题开头，且不包含 AI 对话痕迹。检测到异常内容时自动跳过注入。

## 技术债务（关键）

- **命令注入风险**: `repo_url` 和分支名称在 git 命令前未验证（`opd/api/projects.py`、`opd/engine/workspace/git.py`）
- **缺少认证**: API 端点上无认证/授权
- **循环依赖**: `opd/api/projects.py` 从 `opd.main` 导入，存在循环依赖风险
- **阻塞子进程**: `opd/providers/scm/github.py` 使用阻塞的 `subprocess.run()`，应使用 `asyncio.create_subprocess_exec()`
- **重复 DB 会话模式**: `stories_tasks.py` 和 `projects.py` 中 session_factory + 查询模式重复 7+ 次

## 开发工作流

1. **功能开发**: 创建 Story → AI 生成 PRD → 审查/确认 → AI 规划 → AI 设计 → AI 编码 → 人工验证 → 合并
2. **迭代**: 使用回退动作（从 verifying→coding 迭代，从 verifying→designing 重启）在任何阶段优化
3. **实时监控**: SSE 流式传输在终端风格控制台中显示实时 AI 进度
4. **多轮支持**: 每次迭代创建新的 Round，带有单独的分支和 PR
5. **工作区同步**: 使用项目同步端点从仓库变更更新上下文，自动生成/更新 CLAUDE.md
