# OPD - One Person Devs

AI 驱动的工程迭代流程编排平台。将 AI 编码能力（Claude Code）融入完整的软件工程迭代流程：需求澄清 → 方案规划 → AI 编码 → Code Review → 人工验证 → 合并上线。

## 核心理念

**一个人 + AI = 一个团队。**

OPD 编排整个开发流程，让开发者专注于决策（审查方案、Review 代码、验证功能），AI 负责执行（分析需求、生成方案、编写代码、响应反馈）。

## 架构

### Provider 抽象层

所有外部依赖通过 Provider 接口抽象，外网和内网只需切换不同实现：

| Provider | 职责 | 已实现 |
|----------|------|--------|
| AIProvider | AI 编码 | Claude Code (claude-agent-sdk) |
| SCMProvider | 代码管理 + PR | GitHub (PyGithub + GitPython) |
| RequirementProvider | 需求管理 | 本地文件 |
| DocumentProvider | 文档/知识库 | 本地 Markdown |
| NotificationProvider | 通知消息 | Web 站内通知 |
| CIProvider | 持续集成 | (待实现) |
| SandboxProvider | 沙盒环境 | (待实现) |

### 任务状态机

```
created → clarifying → planning → coding → pr_created → reviewing → testing → done
                                              ↑    ↓         ↑
                                              └ revising ←───┘
```

### 项目结构

```
opd/
├── main.py              # FastAPI 应用入口 + CLI
├── config.py            # 配置加载 (opd.yaml)
├── api/                 # HTTP API 路由
│   ├── projects.py      # 项目 CRUD
│   ├── stories.py       # Story 生命周期管理
│   └── webhooks.py      # GitHub webhook
├── db/                  # 数据库
│   ├── models.py        # SQLAlchemy 模型
│   └── session.py       # 异步会话管理
├── engine/              # 编排引擎
│   ├── orchestrator.py  # 核心编排器
│   ├── state_machine.py # 状态机
│   └── context.py       # AI prompt 构建
├── providers/           # Provider 抽象层
│   ├── base.py          # 基类
│   ├── registry.py      # 注册表
│   ├── ai/              # AI 编码
│   ├── scm/             # 代码管理
│   ├── requirement/     # 需求管理
│   ├── document/        # 文档管理
│   ├── notification/    # 通知
│   ├── ci/              # 持续集成
│   └── sandbox/         # 沙盒环境
└── web/                 # Web UI (Jinja2)
    ├── routes.py
    ├── templates/
    └── static/
```

## 快速开始

### 环境要求

- Python >= 3.11
- MySQL
- GitHub Token (需要 `repo` scope)
- Claude API Key (用于 AI 编码)

### 安装

```bash
git clone https://github.com/zjjiang/one-person-devs.git
cd one-person-devs

# 安装依赖
uv sync --extra ai --extra dev

# 复制配置文件
cp opd.yaml.example opd.yaml
cp .env.example .env
```

### 配置

编辑 `opd.yaml`：

```yaml
server:
  host: 0.0.0.0
  port: 8765

workspace:
  base_dir: ./workspace

providers:
  ai:
    type: claude_code
    config:
      model: sonnet
      max_turns: 50
  scm:
    type: github
    config:
      token: ${GITHUB_TOKEN}
```

编辑 `.env`：

```bash
GITHUB_TOKEN=ghp_your_token_here
ANTHROPIC_API_KEY=sk-ant-your_key_here
```

### 初始化数据库

```bash
# 确保 MySQL 已启动，创建数据库
mysql -u root -e "CREATE DATABASE IF NOT EXISTS one_person_devs;"

# 运行迁移
uv run alembic upgrade head
```

### 启动

```bash
uv run opd serve
# 或
uv run python -m opd.main serve
```

访问 http://localhost:8765

## 使用流程

1. **创建项目** — 填写项目名称、GitHub 仓库地址
2. **创建需求 (Story)** — 描述需求和验收标准
3. **AI 澄清** — AI 分析需求并提问，你回答后继续
4. **方案规划** — AI 生成实施方案，你审阅确认或驳回
5. **AI 编码** — AI 在后台编码，自动创建 PR
6. **Code Review** — 查看 PR，可要求 AI 修改（基于评论或自定义指令）
7. **人工验证** — 拉取分支本地验证，通过后合并 PR

## 扩展 Provider

实现对应的 Provider 基类，在 `registry.py` 中注册，修改 `opd.yaml` 切换即可：

```python
# opd/providers/scm/my_scm.py
from opd.providers.scm.base import SCMProvider

class MySCMProvider(SCMProvider):
    async def clone_repo(self, repo_url, target_dir):
        ...
```

```python
# opd/providers/registry.py
registry.register("scm", "my_scm", MySCMProvider)
```

```yaml
# opd.yaml
providers:
  scm:
    type: my_scm
```

## License

MIT
