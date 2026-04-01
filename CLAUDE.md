# OPD (One Person Devs) 项目指南

AI 驱动的工程迭代流程编排平台。

## 快速开始

```bash
# 后端启动
uv run opd serve --reload

# 前端启动
cd web && npm run dev

# 同时启动两个服务
./restart.sh
```

## 项目结构

```
opd/                    # 后端主包
├── api/                # FastAPI 路由
├── engine/             # 核心编排引擎
│   ├── orchestrator.py # 中央协调器
│   ├── state_machine.py # 状态转换
│   ├── stages/         # 阶段实现
│   ├── context.py      # AI 上下文构建
│   └── workspace/      # 工作区管理
├── capabilities/       # 能力注册表
├── providers/          # Provider 实现
├── db/                 # SQLAlchemy 模型
└── main.py             # 应用入口

web/                    # React 前端
├── src/pages/          # 页面
├── src/components/     # 组件
└── src/api/            # API 调用

tests/                  # pytest 测试
migrations/             # Alembic 数据库迁移
```

## 核心概念

### Story 生命周期

轻量模式：`preparing → briefing → coding → verifying → done`
完整模式：`preparing → clarifying → planning → designing → coding → verifying → done`

### 关键组件

- **Orchestrator** (`opd/engine/orchestrator.py:25-112`) — 中央协调器，驱动 Story 完成生命周期
- **State Machine** (`opd/engine/state_machine.py`) — 定义状态转换规则
- **Stages** (`opd/engine/stages/`) — 各阶段实现（清晰��段、规划阶段、编码阶段等）
- **Workspace** (`opd/engine/workspace/`) — 项目工作区管理、git 操作、文档 I/O
- **Capability Registry** (`opd/capabilities/registry.py`) — 外部依赖管理（AI、SCM、通知）

## 常见任务

### 运行测试

```bash
# 所有测试
uv run pytest tests/ -v

# 单个文件
uv run pytest tests/test_state_machine.py -v

# 单个测试
uv run pytest tests/test_state_machine.py::test_valid_transition -v

# 显示覆盖率
uv run pytest tests/ --cov=opd
```

### 代码检查

```bash
# Lint 检查
uv run ruff check opd/

# 自动修复
uv run ruff check --fix opd/

# 格式化
uv run ruff format opd/
```

### 数据库迁移

```bash
# 查看当前状态
uv run alembic current

# 执行迁移
uv run alembic upgrade head

# 创建新迁移
uv run alembic revision --autogenerate -m "描述"
```

### 前端构建

```bash
# 开发模式（Vite）
cd web && npm run dev

# 生产构建
cd web && npm run build
```

## 关键文件路径

### 后端

- API 路由：`opd/api/stories.py` (Story CRUD)
- 编码阶段：`opd/engine/stages/coding.py` (AI 编码逻辑)
- GitHub Provider：`opd/providers/scm/github.py` (PR 创建)
- 数据库模型：`opd/db/models.py`
- 配置：`opd.yaml` 和 `.env`

### 前端

- Story 详情页：`web/src/pages/StoryDetail.tsx`
- AI 控制台：`web/src/components/AIConsole.tsx` (实时流显示)
- Stage 步进器：`web/src/components/StageStepper.tsx`

## 常见陷阱

### 1. DB 会话提交陷阱

在 `async for db in get_db():` 内使用 `return` 会跳过自动提交。解决：使用独立的会话块。

```python
# ❌ 错误
async for db in get_db():
    db.add(item)
    if error:
        return  # 跳过提交！

# ✅ 正确
async for db in get_db():
    db.add(item)
    if error:
        # 使用独立��话处理错误
        async for error_db in get_db():
            error_db.add(error_record)
```

### 2. Capability 覆盖陷阱

项目级 capability 配置优先于全局配置，但不能覆盖不存在的 capability。在应用前检查：

```python
registry = orch.capabilities
if project.capability_configs:
    overrides = build_capability_overrides(project.capability_configs)
    registry = await orch.capabilities.with_project_overrides(overrides)
```

### 3. 工作区锁定陷阱

同一项目同时只能有一个 Story 在 coding 阶段。确保 finally 块中释放锁：

```python
try:
    # coding work
finally:
    await release_workspace_lock()
```

### 4. CLAUDE.md 污染防护

`_read_claude_md()` 检测 AI 对话痕迹并跳过注入。不要修改 context.py 中的 `_CORRUPTED_PATTERNS`。

## 开发工作流

1. **功能开发**：创建 Story → AI 生成方案 → 审查 → AI 编码 → 人工验证 → 合并
2. **迭代**：使用回退动作从 verifying 回到 coding（iterate）或 designing（restart）
3. **测试**：编写测试确保覆盖率 ≥ 80%
4. **提交**：使用 conventional commits（feat/fix/refactor/docs/test/chore）

## 环境变量

```bash
# .env 文件
DATABASE_URL=mysql+aiomysql://root:password@localhost:3306/one_person_devs
GITHUB_TOKEN=ghp_xxxxxxxxxxxx  # 可选，GitHub capability 优先使用数据库配置
ANTHROPIC_API_KEY=sk-ant-xxx   # 可选，AI capability 优先使用数��库配置
```

## 调试技巧

### 查看 AI 消息流

```bash
# 实时日志
curl http://localhost:8765/api/logs/stream

# Story 的 AI 消息历史
curl http://localhost:8765/api/stories/{id}/stream
```

### 数据库查询

```bash
mysql -uroot -ppassword one_person_devs

# 查看最近的 Story
SELECT id, title, status, mode FROM stories ORDER BY created_at DESC LIMIT 5;

# 查看某个 Story 的轮次
SELECT id, status, branch_name FROM rounds WHERE story_id = ? ORDER BY created_at;

# 查看 AI 消息
SELECT role, content FROM ai_messages WHERE round_id = ? ORDER BY created_at;
```

## 性能优化

### 大项目 CLAUDE.md 处理

OPD 项目的 CLAUDE.md 可能很大。如果超过 10MB：
- 使用 `opd/engine/memory/` 的分块读取
- 或者通过 `/api/projects/{id}/sync-context` 重新生成（自动截断）

### Context Window 管理

当前没有对 prompt 做 token 预算控制，如果上下文太长可能超出模型限制。解决：
- 减少工作区文件数量
- 手动删除不相关的代码注释
- 或者等待 harness engineering 改进（自动截断 context）

## 有用的链接

- [项目 GitHub](https://github.com/zjjiang/one-person-devs)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [React 18 文档](https://react.dev/)
- [Alembic 迁移指南](https://alembic.sqlalchemy.org/)
