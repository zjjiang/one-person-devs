# OPD - One Person Devs

AI 驱动的工程迭代流程编排平台。将 AI 编码能力（Claude Code）融入完整的软件工程迭代流程：需求准备 → 需求澄清 → 方案规划 → 详细设计 → AI 编码 → 验证 → 完成。

## 核心理念

**一个人 + AI = 一个团队。**

OPD 编排整个开发流程，让开发者专注于决策（审查方案、Review 代码、验证功能），AI 负责执行（分析需求、生成方案、编写代码、响应反馈）。

## Story 状态机

```
Preparing → Clarifying → Planning → Designing → Coding → Verifying → Done
                                        ↑                    |
                                        └── restart ─────────┤
                                                  ↑          |
                                        Coding ←─ iterate ──┘
```

每个阶段都有人工门禁（Human Gate），确保 human-in-the-loop。

## 架构

### 三层基础设施

| 层级 | 说明 | 示例 |
|------|------|------|
| Capability | 能力抽象（AI、SCM、CI 等） | ai, scm, ci, doc, sandbox |
| Provider | 能力的具体实现 | claude_code, github, github_actions |
| Environment | 外部依赖（外网/内网） | GitHub API, Docker |

### Capability 系统

每个 Stage 声明所需的 `required_capabilities` 和 `optional_capabilities`。执行前自动进行 Preflight 健康检查，required 不可用则阻断，optional 不可用则降级。

### 项目结构

```
opd/
├── main.py                # FastAPI 应用入口 + CLI
├── config.py              # 配置加载 (opd.yaml + env interpolation)
├── middleware.py           # Pure ASGI 中间件 (SSE passthrough)
├── api/                   # HTTP API 路由
│   ├── projects.py        # 项目 CRUD
│   ├── stories.py         # Story 生命周期 + SSE 流式
│   └── webhooks.py        # GitHub webhook
├── db/                    # 数据库
│   ├── models.py          # SQLAlchemy 2.0 async 模型
│   └── session.py         # 异步会话管理
├── engine/                # 编排引擎
│   ├── orchestrator.py    # 核心编排器 + SSE pub/sub
│   ├── state_machine.py   # 状态机
│   ├── context.py         # AI prompt 构建
│   └── stages/            # 6 个阶段实现
│       ├── base.py        # Stage 基类 (validate/execute/validate_output)
│       ├── preparing.py   # 需求 → PRD
│       ├── clarifying.py  # 需求澄清
│       ├── planning.py    # 技术方案
│       ├── designing.py   # 详细设计
│       ├── coding.py      # AI 编码
│       └── verifying.py   # 验证
├── capabilities/          # 能力系统
│   ├── base.py            # Provider/Capability 基类 + HealthStatus
│   └── registry.py        # 注册表 + Preflight + 懒加载
├── providers/             # Provider 实现
│   ├── ai/claude_code.py  # Claude Code SDK
│   ├── scm/github.py      # GitHub (PyGithub + GitPython)
│   ├── ci/                # CI (GitHub Actions)
│   ├── doc/               # 文档 (Local, Notion)
│   ├── sandbox/           # 沙盒 (Docker)
│   └── notification/      # 通知 (Web)
├── models/schemas.py      # Pydantic 请求/响应模型
└── web/                   # Web UI (Jinja2 + vanilla JS)
    ├── routes.py
    ├── templates/
    └── static/
```

## 快速开始

### 环境要求

- Python >= 3.11
- uv (包管理)
- GitHub Token (`repo` scope)
- Anthropic API Key

### 安装

```bash
git clone https://github.com/zjjiang/one-person-devs.git
cd one-person-devs

# 安装依赖
uv sync --extra ai --extra dev

# 复制配置
cp opd.yaml.example opd.yaml
```

### 配置

编辑 `.env`：

```bash
GITHUB_TOKEN=ghp_your_token_here
ANTHROPIC_API_KEY=sk-ant-your_key_here
```

编辑 `opd.yaml` 配置 capabilities（参考 `opd.yaml.example`）。

### 初始化数据库

```bash
# SQLite（本地开发，默认）
uv run alembic upgrade head

# MySQL（生产环境）
# 修改 alembic.ini 和 opd.yaml 中的数据库 URL
```

### 启动

```bash
uv run opd serve
# 或
uv run opd serve --reload  # 开发模式
```

访问 http://localhost:8765

## 使用流程

1. **创建项目** — 填写项目名称、GitHub 仓库地址
2. **创建 Story** — 描述需求
3. **Preparing** — AI 生成 PRD，人工确认
4. **Clarifying** — AI 提问澄清需求，人工回答后确认
5. **Planning** — AI 生成技术方案，人工确认
6. **Designing** — AI 生成详细设计（任务拆分），人工确认
7. **Coding** — AI 编码，自动创建 PR
8. **Verifying** — Code Review + CI + 沙盒验证，通过则完成；不通过可 iterate（回到 Coding）或 restart（回到 Designing）

## 扩展 Provider

实现 `Provider` 基类，在 `_BUILTIN_PROVIDERS` 中注册，修改 `opd.yaml` 切换：

```python
# opd/providers/scm/my_scm.py
from opd.providers.scm.base import SCMProvider

class MySCMProvider(SCMProvider):
    async def clone_repo(self, repo_url, target_dir):
        ...
```

```yaml
# opd.yaml
capabilities:
  scm:
    provider: my_scm
```

## 开发

```bash
# 测试
uv run pytest tests/ -v

# Lint
uv run ruff check opd/ tests/

# 创建迁移
uv run alembic revision --autogenerate -m "description"
```

## License

MIT
