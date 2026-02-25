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
opd/
├── api/                    # FastAPI 路由和端点
│   ├── stories.py          # Story 生命周期 CRUD、SSE 流式传输
│   ├── stories_tasks.py    # 带回调的后台 AI 任务函数
│   ├── stories_actions.py  # 状态转换动作
│   ├── stories_docs.py     # 文档 CRUD 端点
│   ├── projects.py         # 项目管理 + 同步端点
│   ├── capabilities.py     # Capability 健康检查
│   ├── settings.py         # 全局配置
│   ├── notifications.py    # 通知 API（站内信）
│   ├── logs.py             # 全局日志查看
│   ├── users.py            # 用户注册
│   └── webhooks.py         # GitHub webhook 处理器
├── engine/                 # 核心编排引擎
│   ├── orchestrator.py     # 中央协调器（112 行）
│   ├── state_machine.py    # 状态转换逻辑
│   ├── context.py          # AI 提示词构建器
│   ├── hashing.py          # 输入变更检测
│   ├── notify.py           # 通知服务（fan-out）
│   ├── workspace_lock.py   # 工作区互斥锁
│   ├── stages/             # 阶段实现
│   └── workspace/          # Git/文件操作
├── capabilities/           # Capability 系统
│   ├── base.py             # Provider 和 Capability 基类
│   ├── registry.py         # CapabilityRegistry
│   └── ...
├── providers/              # Provider 实现
│   ├── ai/                 # AI providers（claude_code、ducc）
│   ├── scm/                # SCM providers（github）
│   ├── doc/                # Doc providers（local）
│   └── notification/       # 通知 providers（inbox、feishu）
├── db/                     # 数据库层
│   ├── models.py           # SQLAlchemy 模型
│   └── session.py          # DB 会话管理
├── config.py               # 配置加载器
├── middleware.py           # ASGI 中间件
└── main.py                 # 应用入口点

web/
├── src/
│   ├── pages/              # 路由页面
│   │   ├── StoryDetail.tsx # 主 story 工作流 UI
│   │   ├── StoryForm.tsx   # Story 创建
│   │   ├── ProjectDetail.tsx
│   │   ├── ProjectList.tsx
│   │   ├── ProjectForm.tsx
│   │   ├── ProjectSettings.tsx
│   │   └── GlobalSettings.tsx
│   ├── components/         # 可复用组件
│   │   ├── AIConsole.tsx   # 终端风格 SSE 显示
│   │   ├── SyncConsole.tsx # 工作区同步流式传输
│   │   ├── ChatPanel.tsx   # 文档优化聊天
│   │   ├── PrdEditor.tsx   # Markdown 编辑器
│   │   ├── StageStepper.tsx
│   │   ├── ClarifyQA.tsx   # 澄清问答
│   │   └── AppLayout.tsx   # 主布局包装器
│   └── main.tsx            # React 入口点
└── public/                 # 静态资源

tests/                      # pytest 测试套件
docs/                       # Story 文档归档
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

## 常见陷阱

1. **DB 会话提交**: 在 `async for db in get_db()` 内使用 `return` 会跳过自动提交。对于错误路径，使用单独的会话块。
2. **中间件缓冲**: 使用纯 ASGI 中间件（而非 `BaseHTTPMiddleware`）以避免缓冲 `StreamingResponse`。
3. **Capability 懒加载**: Capabilities 在首次使用时懒加载。使用前在 `_BUILTIN_PROVIDERS` 中注册。
4. **SSE 保活**: 流式端点需要 15 秒心跳以防止超时。
5. **Capability vs Provider 混淆**: `opd/capabilities/` 包含注册表系统，`opd/providers/` 包含实现。不要混淆两者。

## 技术债务与改进领域

### 安全（关键）
- **命令注入风险**: `repo_url` 和分支名称在 git 命令前未验证（`opd/api/projects.py`、`opd/engine/workspace/git.py`）。验证 URL 格式（仅 https）和分支名称（字母数字 + 连字符）。
- **缺少认证**: API 端点上无认证/授权。任何人都可以访问/修改任何项目。添加认证中间件和每资源授权。
- **速率限制**: AI 端点上无速率限制。添加速率限制中间件以防止滥用和成本爆炸。

### 架构
- **SSE Pub/Sub 可扩展性**: `Orchestrator` 中当前的内存 pub/sub 无法跨多个实例扩展。考虑使用 Redis pub/sub 进行多实例部署。
- **后台任务跟踪**: `_running_tasks` 字典仅在内存中。对于水平扩展，移至 Redis 或基于数据库的任务队列。
- **循环依赖**: `opd/api/projects.py` 第 96 行从 `opd.main` 导入，存在循环依赖风险。将 orchestrator 作为参数传递或使用依赖注入。
- **缺少任务管理器**: 无后台任务生命周期管理的抽象。创建具有适当生命周期钩子的 `TaskManager` 类。
- **紧耦合**: 后台任务直接操作 DB 模型。引入服务层以抽象 DB 操作。
- **阻塞子进程调用**: `opd/providers/scm/github.py` 使用阻塞的 `subprocess.run()` 调用。包装在 `asyncio.create_subprocess_exec()` 中。

### 代码质量
- **重复的 DB 会话模式**: 在 `opd/api/stories_tasks.py` 和 `opd/api/projects.py` 中重复 7+ 次创建 session_factory 和查询 Story/Project 的模式。提取为可复用的辅助函数。
- **过长函数**: `_start_ai_stage`（135 行）、`_launch_clone`（60 行）、`_launch_sync_context`（80 行）违反 SRP。拆分为更小的函数。
- **重复的错误处理**: Git 操作错误处理重复 3+ 次。包装在具有一致错误处理的辅助函数中。
- **不一致的异常处理**: 有些地方静默吞噬异常，其他地方记录。标准化：始终记录异常，永不使用裸 `except Exception: pass`。
- **缺少文档字符串**: 许多辅助函数缺少文档字符串（`opd/api/capability_utils.py`、`opd/engine/workspace/git.py` 中的复杂算法）。

### API 与性能
- **N+1 查询风险**: Story 列表迭代计数 stories 而非使用 SQL COUNT（`opd/api/projects.py` 第 147-160 行）。
- **低效的活动轮次查找**: 线性 O(n) 搜索所有轮次。添加 `story.active_round_id` 外键或使用带过滤器的 DB 查询。
- **无界文件读取**: `claude_md.read_text()` 将整个文件读入内存（`opd/engine/context.py` 第 75 行）。添加大小限制或流式读取。
- **缺少索引**: 验证索引：`stories.project_id`、`stories.status`、`rounds.story_id`、`rounds.status`、`ai_messages.round_id`、`clarifications.story_id`。
- **API 文档**: 某些端点缺少 OpenAPI 文档（stories_docs、project sync）。
- **错误响应一致性**: 某些端点返回 `{"error": "..."}`，其他端点引发 `HTTPException`。标准化为 HTTPException。

### 前端
- **状态管理**: 某些组件中的 prop drilling（StoryDetail、ProjectDetail）。考虑 React Context 或状态管理库。
- **组件可复用性**: 某些组件有重复逻辑。提取共享钩子和工具。
- **类型安全**: TypeScript 中的一些 `any` 类型。改进类型覆盖率。

### 测试
- **E2E 测试覆盖率**: 缺少关键工作流的 E2E 测试（story 创建 → 编码 → 合并）。
- **集成测试**: 使用真实 DB 的 API 端点集成测试有限。无 SSE 流式传输的集成测试。
- **前端测试**: 无前端组件测试。添加 React Testing Library 测试。
- **错误恢复测试**: 无后台任务错误恢复测试（DB 错误、git 错误、AI 错误）。
- **并发测试**: 无并发 story 执行测试。可能存在竞态条件。
- **边缘情况测试**: 无工作区冲突测试（分支创建期间脏工作区）。

### DevOps
- **Docker 支持**: 无 Dockerfile 或 docker-compose.yml 用于容器化部署。
- **CI/CD 管道**: 无 GitHub Actions 或 CI/CD 配置。
- **环境管理**: `.env` 文件未记录。添加 `.env.example`。

### 文档
- **API 端点文档**: 缺少详细的 API 文档。考虑添加 OpenAPI/Swagger UI。
- **Provider 开发指南**: 无添加新 providers 的指南。
- **部署指南**: 缺少生产部署说明。
- **函数文档字符串**: 许多辅助函数缺少文档字符串，特别是 `opd/api/capability_utils.py` 和 `opd/engine/workspace/git.py` 中的复杂算法。

## 优先级建议

### 立即（安全 - 关键）
1. 为 `repo_url` 和分支名称添加输入验证以防止命令注入
2. 为所有 API 端点添加认证/授权
3. 修复 `GitHubProvider` 中的阻塞子进程调用
4. 为 AI 端点添加速率限制中间件

### 高优先级（架构与质量）
5. 将后台任务 DB 会话模式提取为可复用辅助函数
6. 拆分过长函数（`_start_ai_stage`、`_launch_clone`、`_launch_sync_context`）
7. 为后台任务生命周期创建 `TaskManager` 抽象
8. 修复 `opd/api/projects.py` 中的循环依赖
9. 标准化错误处理（无静默异常）
10. 为所有公共函数添加文档字符串

### 中优先级（测试与性能）
11. 为 SSE 流式传输添加集成测试
12. 添加并发和错误恢复测试
13. 优化 N+1 查询和活动轮次查找
14. 为文件读取操作添加大小限制
15. 验证数据库索引存在

### 低优先级（清理）
16. 合并重复的文档解析逻辑
17. 标准化错误响应格式
18. 为完整工作流添加 E2E 测试
19. 改进前端状态管理
20. 添加 Docker 和 CI/CD 配置

## 开发工作流

1. **功能开发**: 创建 Story → AI 生成 PRD → 审查/确认 → AI 规划 → AI 设计 → AI 编码 → 人工验证 → 合并
2. **迭代**: 使用回退动作（从 verifying→coding 迭代，从 verifying→designing 重启）在任何阶段优化
3. **实时监控**: SSE 流式传输在终端风格控制台中显示实时 AI 进度
4. **多轮支持**: 每次迭代创建新的 Round，带有单独的分支和 PR
5. **工作区同步**: 使用项目同步端点从仓库变更更新上下文

## 已知问题与解决方法

### DB 会话提交陷阱
在 `async for db in get_db()` 内使用 `return` 会跳过自动提交。在错误路径中持久化数据时，使用单独的 `get_db()` 会话块。

### 中间件缓冲
使用纯 ASGI 中间件（而非 `BaseHTTPMiddleware`）以避免缓冲 `StreamingResponse`。流式路径（`/stream`、`/logs`）必须无需包装即可通过。

### Capability 懒加载
Capabilities 在首次使用时懒加载。使用前在 `_BUILTIN_PROVIDERS` 中注册以避免导入错误。

### SSE 保活
流式端点需要 15 秒心跳以防止超时。已在 `/stream` 端点中实现。

### Capability vs Provider 混淆
`opd/capabilities/` 包含注册表系统，`opd/providers/` 包含实现。添加新 capabilities 时不要混淆两者。

### 工作区互斥锁
同一项目同时只能有一个 Story 在 coding 阶段。`workspace_lock.py` 通过 Project 表的 `locked_by_story_id` 字段实现。coding 阶段自动获取锁，完成/失败/停止时自动释放。Preflight 检查会提示锁冲突。

### CLAUDE.md 污染防护
`context.py` 中的 `_read_claude_md()` 会校验工作区 CLAUDE.md 内容：必须以 markdown 标题开头，且不包含 AI 对话痕迹（如 "I'll analyze"、"完成！我已经" 等）。检测到异常内容时自动跳过注入，防止污染 AI prompt。
