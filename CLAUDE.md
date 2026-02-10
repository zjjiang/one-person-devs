# CLAUDE.md

## 项目概述

OPD (One Person Devs) — AI 驱动的工程迭代流程编排平台。将 Claude Code 的编码能力融入完整的软件工程迭代流程。

## 技术栈

- **后端**: FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2
- **数据库**: MySQL (aiomysql), 迁移用 Alembic
- **前端**: Jinja2 模板 + 原生 JS（无前端框架）
- **AI**: claude-agent-sdk (Claude Code)
- **SCM**: PyGithub + GitPython
- **运行**: uv 管理依赖, Python >= 3.11

## 常用命令

```bash
# 启动服务
uv run python -m opd.main serve          # 端口 8765

# 数据库
mysql -uroot -pjzj one_person_devs       # 连接数据库
uv run alembic upgrade head              # 运行迁移

# 测试
uv run pytest tests/

# 代码检查
uv run ruff check opd/
```

## 项目结构要点

- `opd/main.py` — FastAPI 应用入口 + CLI (`opd serve`)
- `opd/config.py` — 从 `opd.yaml` 加载配置
- `opd/engine/orchestrator.py` — **核心文件**，编排所有流程
- `opd/engine/state_machine.py` — Round 状态转换规则
- `opd/engine/context.py` — 构建 AI prompt
- `opd/db/models.py` — 数据模型 (Project, Story, Round, AIMessage 等)
- `opd/db/session.py` — 异步 DB session (`get_db()` generator)
- `opd/api/stories.py` — Story 生命周期 API
- `opd/api/projects.py` — 项目 CRUD API
- `opd/web/routes.py` — Web 页面路由，构建模板上下文
- `opd/web/templates/story_detail.html` — **最复杂的模板**，Story 详情页
- `opd/providers/` — Provider 抽象层，所有外部依赖通过接口隔离

## 关键设计模式

### Provider 抽象

所有外部依赖通过 `Provider` 基类抽象，通过 `ProviderRegistry` 工厂加载。配置在 `opd.yaml` 中切换 `type` 即可替换实现。已实现: ai/claude_code, scm/github, notification/web, requirement/local, document/local。

### 后台任务

AI 编码/修改等耗时操作通过 `asyncio.create_task()` 在后台运行，用 `_running_tasks` dict 跟踪。`_run_ai_background()` 是核心方法，支持 `pre_start`（clone/branch）和 `post_complete`（commit/push/create PR）回调。

### DB Session 注意事项

`get_db()` 是 async generator，`yield session` 后自动 commit。**在 `async for db in get_db()` 内部 `return` 会导致 commit 被跳过**，需要保存错误消息时必须用独立的 `get_db()` session。

### 状态机

Round 状态流转: `created → clarifying → planning → coding → pr_created → reviewing ↔ revising → testing → done`。转换规则在 `state_machine.py` 的 `VALID_TRANSITIONS` dict 中定义。

## 配置文件

- `opd.yaml` — 主配置（服务器、Provider、workspace）
- `.env` — 环境变量（GITHUB_TOKEN, ANTHROPIC_API_KEY）
- `opd.yaml.example` / `.env.example` — 配置模板
