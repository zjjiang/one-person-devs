# OPD v2 技术方案

## 1. 设计原则

- 阶段即边界：每个阶段是独立的执行单元，有严格的输入校验、输出校验、前置条件检查
- 能力即插件：所有外部依赖通过 Capability → Provider 抽象，可配置、可替换、可健康检查
- 失败可感知：任何能力不可用时，在用户操作前就给出明确提示，而不是执行到一半才报错

## 2. 项目结构

```
opd/
├── main.py                     # FastAPI app + CLI entry point
├── config.py                   # 配置加载（opd.yaml + env）
├── middleware.py                # ASGI 中间件（日志、错误处理、SSE 透传）
│
├── engine/                     # 核心引擎
│   ├── orchestrator.py         # 编排器：协调阶段流转
│   ├── state_machine.py        # 状态机：转换规则 + 校验
│   ├── context.py              # AI 上下文构建
│   └── stages/                 # 阶段实现（核心新增）
│       ├── base.py             # Stage 基类：定义阶段契约
│       ├── preparing.py        # 需求准备
│       ├── clarifying.py       # 需求澄清
│       ├── planning.py         # 概要设计 + Task 拆分
│       ├── designing.py        # 详细设计
│       ├── coding.py           # AI 编码
│       └── verifying.py        # 验证（CR + CI + 沙盒）
│
├── capabilities/               # 能力层（核心新增）
│   ├── base.py                 # Capability 基类
│   ├── registry.py             # 能力注册表
│   └── health.py               # 健康检查引擎
│
├── providers/                  # Provider 实现
│   ├── base.py                 # Provider 基类
│   ├── ai/
│   │   ├── base.py
│   │   └── claude_code.py
│   ├── scm/
│   │   ├── base.py
│   │   └── github.py
│   ├── ci/
│   │   ├── base.py
│   │   └── github_actions.py
│   ├── doc/
│   │   ├── base.py
│   │   ├── local.py
│   │   └── notion.py
│   ├── sandbox/
│   │   ├── base.py
│   │   └── docker_local.py
│   └── notification/
│       ├── base.py
│       └── web.py
│
├── db/
│   ├── models.py               # SQLAlchemy ORM 模型
│   └── session.py              # 异步会话管理
│
├── api/                        # HTTP API
│   ├── deps.py                 # 依赖注入
│   ├── projects.py             # 项目 CRUD + 能力配置
│   ├── stories.py              # Story 生命周期
│   └── webhooks.py             # GitHub webhook
│
├── models/                     # Pydantic schemas
│   └── schemas.py
│
└── web/                        # Web UI（Jinja2 + vanilla JS）
    ├── routes.py
    ├── templates/
    └── static/
```

## 3. 阶段系统（Stage System）

### 3.1 Stage 基类

每个阶段是一个独立的类，实现统一的契约接口。阶段之间通过 StageContext 传递数据，不直接耦合。

```python
class StageContext:
    """阶段间传递的上下文数据"""
    story: Story              # 当前 Story（含 PRD、设计文档、Tasks 等）
    project: Project          # 项目配置（含 Rules、Skills）
    round: Round              # 当前 Round
    capabilities: dict        # 可用的能力实例

class StageResult:
    """阶段执行结果"""
    success: bool
    output: dict              # 阶段产出（存入 Story 对应字段）
    next_status: str | None   # 建议的下一个状态（None 表示等待人类操作）
    errors: list[str]

class Stage(ABC):
    """阶段基类"""

    # 声明本阶段依赖的能力
    required_capabilities: list[str] = []     # 必须可用，否则阶段无法执行
    optional_capabilities: list[str] = []     # 可选，不可用时降级处理

    @abstractmethod
    async def validate_preconditions(self, ctx: StageContext) -> list[str]:
        """前置条件校验，返回错误列表（空 = 通过）

        检查内容：
        - 上一阶段的产出是否完整
        - 必需的能力是否健康
        - 业务规则是否满足
        """

    @abstractmethod
    async def execute(self, ctx: StageContext) -> StageResult:
        """执行阶段逻辑"""

    @abstractmethod
    async def validate_output(self, result: StageResult) -> list[str]:
        """输出校验，确保产出符合下一阶段的输入要求"""
```

### 3.2 各阶段实现

#### Preparing

```python
class PreparingStage(Stage):
    required_capabilities = ["ai"]
    optional_capabilities = ["doc"]  # 读取外部文档是可选的

    async def validate_preconditions(self, ctx):
        errors = []
        if not ctx.story.raw_input:
            errors.append("缺少原始需求输入")
        return errors

    async def execute(self, ctx):
        # 1. 如果有外部文档链接，通过 Doc 能力读取
        # 2. 调用 AI 能力，基于原始输入生成/美化 PRD
        # 3. 返回 PRD 内容，等待人类确认

    async def validate_output(self, result):
        errors = []
        if not result.output.get("prd"):
            errors.append("PRD 未生成")
        return errors
```

#### Clarifying

```python
class ClarifyingStage(Stage):
    required_capabilities = ["ai"]
    optional_capabilities = ["scm"]  # 读代码库辅助理解是可选的

    async def validate_preconditions(self, ctx):
        errors = []
        if not ctx.story.prd:
            errors.append("PRD 未就绪，无法进入澄清阶段")
        return errors

    async def execute(self, ctx):
        # 1. 构建上下文：PRD + 项目信息 + 代码库结构（如果 SCM 可用）
        # 2. 调用 AI 分析需求，生成澄清问题
        # 3. 返回问题列表，等待人类回答
        # 4. 人类回答后，AI 复述需求，等待产研确认

    async def validate_output(self, result):
        errors = []
        if not result.output.get("confirmed_prd"):
            errors.append("PRD 未经确认")
        return errors
```

#### Planning

```python
class PlanningStage(Stage):
    required_capabilities = ["ai", "scm"]

    async def validate_preconditions(self, ctx):
        errors = []
        if not ctx.story.confirmed_prd:
            errors.append("PRD 未经确认，无法进入 Planning")
        return errors

    async def execute(self, ctx):
        # 1. 调用 AI 分析代码库 + PRD，生成概要设计
        # 2. 基于概要设计拆分 Task，标注依赖关系
        # 3. 返回概要设计 + Task 列表，等待产研确认

    async def validate_output(self, result):
        errors = []
        if not result.output.get("technical_design"):
            errors.append("概要设计未生成")
        if not result.output.get("tasks"):
            errors.append("Task 列表未生成")
        return errors
```

#### Designing

```python
class DesigningStage(Stage):
    required_capabilities = ["ai", "scm"]

    async def validate_preconditions(self, ctx):
        errors = []
        if not ctx.story.technical_design:
            errors.append("概要设计未就绪")
        if not ctx.story.tasks:
            errors.append("Task 列表未就绪")
        return errors

    async def execute(self, ctx):
        # 1. 调用 AI 基于概要设计 + Task 列表，生成详细设计文档
        # 2. 一份文档覆盖所有 Task 的实现细节
        # 3. 返回详细设计，等待产研确认

    async def validate_output(self, result):
        errors = []
        if not result.output.get("detailed_design"):
            errors.append("详细设计未生成")
        return errors
```

#### Coding

```python
class CodingStage(Stage):
    required_capabilities = ["ai", "scm"]

    async def validate_preconditions(self, ctx):
        errors = []
        if not ctx.story.detailed_design:
            errors.append("详细设计未就绪")
        return errors

    async def execute(self, ctx):
        # 1. SCM: clone 代码库，创建分支
        # 2. AI: 按 Task 依赖顺序编码（SSE 实时流式输出）
        # 3. SCM: commit + push + 创建 PR
        # 4. 返回 PR 信息

    async def validate_output(self, result):
        errors = []
        if not result.output.get("pull_requests"):
            errors.append("PR 未创建")
        return errors
```

#### Verifying

```python
class VerifyingStage(Stage):
    required_capabilities = ["scm"]
    optional_capabilities = ["ci", "sandbox"]

    async def validate_preconditions(self, ctx):
        errors = []
        if not ctx.round.pull_requests:
            errors.append("PR 未就绪，无法进入验证")
        return errors

    async def execute(self, ctx):
        # 本阶段主要由人类驱动，系统提供辅助：
        # 1. 展示 PR diff + 设计文档对照
        # 2. 如果 CI 可用，人类可按需触发 CI 流程
        # 3. 如果 Sandbox 可用，人类可部署到沙盒环境测试
        # 4. 等待人类做出判定：通过 / iterate / restart

    async def validate_output(self, result):
        # 验证结果由人类决定，无需自动校验
        return []
```

### 3.3 阶段流转（Orchestrator）

Orchestrator 不再直接包含业务逻辑，而是负责：
1. 根据当前状态找到对应的 Stage 实例
2. 执行前置条件校验（含能力健康检查）
3. 调用 Stage.execute()
4. 执行输出校验
5. 驱动状态机转换

```python
class Orchestrator:
    def __init__(self, stages: dict[str, Stage], state_machine: StateMachine,
                 capability_registry: CapabilityRegistry):
        self._stages = stages
        self._sm = state_machine
        self._caps = capability_registry

    async def advance(self, story_id: str, action: str, payload: dict) -> StageResult:
        """推进 Story 到下一阶段"""
        story = await self._load_story(story_id)
        stage = self._stages[story.status]

        # 1. 能力健康检查
        health = await self._caps.check_health(stage.required_capabilities)
        if not health.all_healthy:
            return StageResult(success=False, errors=health.unhealthy_reasons)

        # 2. 前置条件校验
        ctx = await self._build_context(story)
        precondition_errors = await stage.validate_preconditions(ctx)
        if precondition_errors:
            return StageResult(success=False, errors=precondition_errors)

        # 3. 执行阶段逻辑
        result = await stage.execute(ctx)

        # 4. 输出校验
        if result.success:
            output_errors = await stage.validate_output(result)
            if output_errors:
                return StageResult(success=False, errors=output_errors)

        # 5. 状态转换
        if result.success and result.next_status:
            self._sm.transition(story, result.next_status)
            await self._save_story(story, result.output)

        return result
```

## 4. 能力系统（Capability System）

### 4.1 核心概念

```
Capability（能力声明）
    │
    ├── 定义：这个能力做什么（接口契约）
    ├── 健康检查：这个能力当前是否可用
    └── Provider（具体实现）
          ├── 配置：连接参数、认证信息
          └── 环境：外网 / 内网
```

### 4.2 Capability 基类

```python
class Capability(ABC):
    """能力基类"""
    name: str                          # 能力名称：ai, scm, ci, doc, sandbox, notify
    provider: Provider                 # 当前使用的 Provider 实现

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """健康检查，返回当前能力是否可用

        HealthStatus:
          - healthy: bool
          - message: str          # 人类可读的状态描述
          - latency_ms: int       # 响应延迟
          - checked_at: datetime  # 检查时间
        """

    @abstractmethod
    def is_configured(self) -> bool:
        """检查是否已配置（有 Provider 且配置完整）"""
```

### 4.3 各能力的健康检查策略

| 能力 | 健康检查方式 | 检查频率 | 失败影响 |
|------|------------|---------|---------|
| AI | 调用 API 发送 ping 请求 | 每 5 分钟 | Preparing/Clarifying/Planning/Designing/Coding 不可用 |
| SCM | 验证 token 有效性 + API 连通性 | 每 5 分钟 | Clarifying 以后的所有阶段不可用 |
| CI | 验证 pipeline 配置是否存在 | 每 10 分钟 | Verifying 中 CI 选项不可用（降级为纯人工） |
| Doc | 验证文档源连通性 | 每 10 分钟 | Preparing 中外部文档读取不可用（降级为手动输入） |
| Sandbox | 验证 Docker/K8s 连通性 | 每 10 分钟 | Verifying 中沙盒选项不可用（降级为本地测试） |
| Notify | 发送测试消息 | 每 10 分钟 | 通知不可用（不影响核心流程） |

### 4.4 项目级能力配置

能力分为两层配置：全局配置（opd.yaml）和项目级配置。

```yaml
# opd.yaml — 全局配置：定义有哪些 Provider 可用
capabilities:
  ai:
    provider: claude_code
    config:
      model: opus
      permission_mode: bypassPermissions
  scm:
    provider: github
    config:
      token: ${GITHUB_TOKEN}
  ci:
    provider: github_actions    # 全局默认 CI Provider
  doc:
    provider: local
    config:
      base_dir: ./docs
  sandbox:
    provider: docker_local
  notification:
    provider: web
```

项目级配置存储在数据库中，控制每个项目启用哪些能力：

```python
class ProjectCapabilityConfig(Base):
    """项目级能力配置"""
    project_id: str
    capability: str           # ai, scm, ci, doc, sandbox, notify
    enabled: bool             # 是否启用
    provider_override: str    # 覆盖全局 Provider（可选）
    config_override: dict     # 覆盖全局配置（可选）
```

示例场景：
- 项目 A：启用 AI + SCM + CI（GitHub Actions），不需要 Sandbox
- 项目 B：启用 AI + SCM，CI 用内部 Agile 平台，启用 Sandbox
- 项目 C：只启用 AI + SCM（最小配置）

### 4.5 阶段执行前的能力预检

当用户触发阶段推进时，系统自动执行预检：

```python
async def preflight_check(stage: Stage, project: Project) -> PreflightResult:
    """阶段执行前的能力预检"""
    result = PreflightResult()

    for cap_name in stage.required_capabilities:
        cap = registry.get(cap_name, project)
        if not cap:
            result.add_error(f"能力 [{cap_name}] 未配置")
            continue
        if not cap.is_configured():
            result.add_error(f"能力 [{cap_name}] 配置不完整")
            continue
        health = await cap.health_check()
        if not health.healthy:
            result.add_error(f"能力 [{cap_name}] 不可用: {health.message}")

    for cap_name in stage.optional_capabilities:
        cap = registry.get(cap_name, project)
        if cap and cap.is_configured():
            health = await cap.health_check()
            if not health.healthy:
                result.add_warning(f"能力 [{cap_name}] 不可用，将降级处理: {health.message}")

    return result
```

用户在 Web UI 上看到的效果：
- 进入某个阶段前，页面显示能力状态面板
- 绿色 ✓：能力健康可用
- 黄色 ⚠：可选能力不可用，会降级
- 红色 ✗：必需能力不可用，无法继续，显示具体原因和修复建议

## 5. 数据模型

### 5.1 核心表

```python
class Project(Base):
    id: int
    name: str
    repo_url: str
    description: str
    tech_stack: str
    architecture: str
    # 关联
    rules: list[Rule]
    skills: list[Skill]
    stories: list[Story]
    capability_configs: list[ProjectCapabilityConfig]

class Story(Base):
    id: int
    project_id: int
    title: str
    feature_tag: str | None           # 可选的 Feature 标签
    status: StoryStatus               # preparing/clarifying/planning/designing/coding/verifying/done
    current_round: int
    # 阶段产出（每个阶段写入对应字段）
    raw_input: str                    # 原始需求输入
    prd: str | None                   # Preparing 产出
    confirmed_prd: str | None         # Clarifying 产出
    technical_design: str | None      # Planning 产出
    detailed_design: str | None       # Designing 产出
    # 关联
    tasks: list[Task]
    rounds: list[Round]
    clarifications: list[Clarification]

class Task(Base):
    id: int
    story_id: int
    title: str
    description: str
    scope: str                        # 改动范围
    acceptance_criteria: str
    order: int                        # 执行顺序
    repo_url: str | None              # 多仓库场景下指定仓库
    # 依赖
    depends_on: list[int]             # 依赖的 Task ID 列表

class Round(Base):
    id: int
    story_id: int
    round_number: int
    type: RoundType                   # initial / iterate / restart
    branch_name: str
    close_reason: str | None
    status: RoundStatus
    # PR 信息（可能多个，多仓库场景）
    pull_requests: list[PullRequest]
    ai_messages: list[AIMessage]

class PullRequest(Base):
    id: int
    round_id: int
    repo_url: str
    pr_number: int
    pr_url: str
    status: PRStatus                  # open / closed / merged

class Rule(Base):
    id: int
    project_id: int
    category: str                     # coding / architecture / testing / git / forbidden
    content: str
    enabled: bool

class Skill(Base):
    id: int
    project_id: int
    name: str
    description: str
    command: str
    trigger: str                      # auto_after_coding / auto_before_pr / manual
```

### 5.2 枚举定义

```python
class StoryStatus(str, Enum):
    preparing = "preparing"
    clarifying = "clarifying"
    planning = "planning"
    designing = "designing"
    coding = "coding"
    verifying = "verifying"
    done = "done"

class RoundType(str, Enum):
    initial = "initial"
    iterate = "iterate"
    restart = "restart"

class RoundStatus(str, Enum):
    active = "active"
    closed = "closed"                 # restart 时关闭

class PRStatus(str, Enum):
    open = "open"
    closed = "closed"
    merged = "merged"
```

## 6. 状态机

### 6.1 转换规则

```python
VALID_TRANSITIONS = {
    "preparing":  ["clarifying"],
    "clarifying": ["planning"],
    "planning":   ["designing"],
    "designing":  ["coding"],
    "coding":     ["verifying"],
    "verifying":  ["done", "coding", "designing"],  # done / iterate / restart
}
```

### 6.2 回退处理

```python
ROLLBACK_ACTIONS = {
    # (from_status, to_status): action
    ("verifying", "coding"):    "iterate",    # 同分支同 PR，继续改
    ("verifying", "designing"): "restart",    # 新 Round，新分支，关闭旧 PR
}
```

## 7. API 设计

### 7.1 项目管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/projects | 创建项目 |
| GET | /api/projects | 项目列表 |
| GET | /api/projects/{id} | 项目详情 |
| PUT | /api/projects/{id} | 更新项目 |
| GET | /api/projects/{id}/capabilities | 项目能力配置 + 健康状态 |
| PUT | /api/projects/{id}/capabilities | 更新项目能力配置 |
| POST | /api/projects/{id}/capabilities/check | 手动触发能力健康检查 |

### 7.2 Story 生命周期

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/projects/{pid}/stories | 创建 Story（进入 Preparing） |
| GET | /api/stories/{id} | Story 详情（含当前阶段、产出、能力状态） |
| POST | /api/stories/{id}/confirm | 确认当前阶段产出，推进到下一阶段 |
| POST | /api/stories/{id}/reject | 打回当前阶段产出，要求重新生成 |
| POST | /api/stories/{id}/answer | 回答澄清问题（Clarifying 阶段） |
| POST | /api/stories/{id}/iterate | 触发 iterate（Verifying → Coding） |
| POST | /api/stories/{id}/restart | 触发 restart（Verifying → Designing） |
| POST | /api/stories/{id}/trigger-ci | 触发 CI 流程（Verifying 阶段） |
| POST | /api/stories/{id}/stop | 紧急停止当前 AI 任务 |
| GET | /api/stories/{id}/stream | SSE 实时流（AI 编码过程） |
| GET | /api/stories/{id}/preflight | 下一阶段的能力预检结果 |

### 7.3 系统管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/health | 系统健康检查（所有能力状态） |
| GET | /api/capabilities | 全局能力配置 + 健康状态 |
| POST | /api/webhooks/github | GitHub webhook |

## 8. 配置体系

### 8.1 配置层级

```
opd.yaml（全局默认）
    ↓ 被覆盖
ProjectCapabilityConfig（项目级覆盖）
    ↓ 被覆盖
环境变量（运行时覆盖）
```

### 8.2 opd.yaml 完整示例

```yaml
server:
  host: 0.0.0.0
  port: 8765

database:
  url: ${DATABASE_URL}

workspace:
  base_dir: ./workspace

logging:
  level: INFO
  dir: ./logs

capabilities:
  ai:
    provider: claude_code
    config:
      model: opus
      permission_mode: bypassPermissions
      max_tokens: 200000
    health_check:
      interval: 300            # 秒
      timeout: 10

  scm:
    provider: github
    config:
      token: ${GITHUB_TOKEN}
    health_check:
      interval: 300
      timeout: 10

  ci:
    provider: github_actions
    config: {}
    health_check:
      interval: 600
      timeout: 15

  doc:
    provider: local
    config:
      base_dir: ./docs
    health_check:
      interval: 600
      timeout: 5

  sandbox:
    provider: docker_local
    config:
      docker_host: unix:///var/run/docker.sock
    health_check:
      interval: 600
      timeout: 10

  notification:
    provider: web
    config: {}
    health_check:
      interval: 600
      timeout: 5
```

## 9. SSE 流式架构

AI 交互（Preparing/Clarifying/Planning/Designing/Coding 阶段）全部通过 SSE 实时流式输出，这是 v1 验证过的核心体验，v2 必须保留并增强。

### 9.1 整体流程

```
Claude Code SDK                Orchestrator              SSE Endpoint           Browser
     │                              │                        │                    │
     │  query() async iterator      │                        │                    │
     │ ◄────────────────────────────│ _run_ai_background()   │                    │
     │                              │                        │                    │
     │  yield AssistantMessage      │                        │                    │
     │ ────────────────────────────►│                        │                    │
     │                              │  save to DB            │                    │
     │                              │  _publish(event)       │                    │
     │                              │ ──────────────────────►│                    │
     │                              │   asyncio.Queue        │  data: {json}\n\n  │
     │                              │                        │ ──────────────────►│
     │                              │                        │                    │  render
     │  yield ResultMessage         │                        │                    │
     │ ────────────────────────────►│                        │                    │
     │                              │  _publish(done)        │                    │
     │                              │ ──────────────────────►│                    │
     │                              │                        │  data: {done}\n\n  │
     │                              │                        │ ──────────────────►│
```

### 9.2 核心组件

#### Pub/Sub 机制（保留 v1 模式）

```python
class Orchestrator:
    _message_subscribers: dict[str, list[asyncio.Queue]]  # round_id → queues

    def subscribe(self, round_id: str) -> asyncio.Queue:
        """订阅某个 Round 的实时消息"""
        queue = asyncio.Queue()
        self._message_subscribers.setdefault(round_id, []).append(queue)
        return queue

    def unsubscribe(self, round_id: str, queue: asyncio.Queue):
        """取消订阅，防止内存泄漏"""
        if round_id in self._message_subscribers:
            self._message_subscribers[round_id].remove(queue)

    async def _publish(self, round_id: str, event: dict):
        """广播事件给所有订阅者"""
        for queue in self._message_subscribers.get(round_id, []):
            queue.put_nowait(event)
```

#### 后台任务管理（保留 v1 模式）

```python
class Orchestrator:
    _running_tasks: dict[str, asyncio.Task]  # round_id → asyncio.Task

    async def _run_ai_background(self, round_id: str, stage: Stage,
                                  ctx: StageContext,
                                  pre_start: Callable = None,
                                  post_complete: Callable = None):
        """在后台运行 AI 阶段，支持 SSE 流式输出

        - pre_start: 编码前的准备（clone repo, create branch）
        - post_complete: 编码后的收尾（commit, push, create PR）
        """
        async def _task():
            try:
                if pre_start:
                    await pre_start()

                # Stage.execute() 内部通过 AI Provider 的 async iterator 流式产出
                # 每条消息同时：1) 存入 DB  2) publish 给 SSE 订阅者
                result = await stage.execute(ctx)

                if post_complete and result.success:
                    await post_complete()

                await self._publish(round_id, {"type": "done"})
            except Exception as e:
                await self._publish(round_id, {"type": "error", "message": str(e)})
                # 用独立 DB session 保存错误状态，避免跳过 commit
            finally:
                self._running_tasks.pop(round_id, None)

        task = asyncio.create_task(_task())
        self._running_tasks[round_id] = task
        task.add_done_callback(lambda t: self._running_tasks.pop(round_id, None))
```

#### SSE Endpoint（保留 v1 模式 + 增强）

```python
@router.get("/api/stories/{story_id}/stream")
async def stream_messages(story_id: str, orchestrator: Orchestrator):
    """SSE 实时流：先回放历史，再接实时"""

    async def event_generator():
        round = get_active_round(story_id)

        # 1. 回放历史消息（从 DB 读取）
        for msg in await get_ai_messages(round.id):
            yield f"data: {json.dumps(msg)}\n\n"

        # 2. 订阅实时消息
        queue = orchestrator.subscribe(round.id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"  # 15s 心跳保活
        finally:
            orchestrator.unsubscribe(round.id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

#### 中间件 SSE 透传（保留 v1 模式）

```python
class LoggingMiddleware:
    """纯 ASGI 中间件，不使用 BaseHTTPMiddleware 避免缓冲 StreamingResponse"""

    async def __call__(self, scope, receive, send):
        if self._is_streaming_path(scope.get("path", "")):
            # 流式路径直接透传，不做任何包装
            await self.app(scope, receive, send)
        else:
            # 非流式路径正常处理
            ...

    def _is_streaming_path(self, path: str) -> bool:
        return path.endswith("/stream") or path.endswith("/logs")
```

### 9.3 Claude Code SDK 调用方式

```python
class ClaudeCodeAIProvider(AIProvider):
    """Claude Code SDK 集成，所有 AI 方法都返回 async iterator 支持 SSE"""

    async def execute_streaming(self, prompt: str, system_prompt: str,
                                 work_dir: str) -> AsyncIterator[dict]:
        """调用 Claude Code SDK，流式返回消息"""
        from claude_code_sdk import query, ClaudeCodeOptions

        options = ClaudeCodeOptions(
            permission_mode="bypassPermissions",
            cwd=work_dir,
            system_prompt=system_prompt,
        )

        async for message in query(prompt=prompt, options=options):
            # 标准化消息格式
            if hasattr(message, "content"):
                yield {"type": "assistant", "content": message.content}
            elif hasattr(message, "tool_name"):
                yield {"type": "tool_use", "name": message.tool_name,
                       "input": message.tool_input}
```

### 9.4 哪些阶段需要 SSE

| 阶段 | SSE | 说明 |
|------|:---:|------|
| Preparing | ✓ | AI 生成 PRD 过程实时可见 |
| Clarifying | ✓ | AI 分析需求、生成问题过程实时可见 |
| Planning | ✓ | AI 生成概要设计过程实时可见 |
| Designing | ✓ | AI 生成详细设计过程实时可见 |
| Coding | ✓ | AI 编码过程实时可见（最核心的 SSE 场景） |
| Verifying | ✗ | 人类主导，无需 SSE |

## 10. 实施计划

### Phase 1：骨架 + 能力系统
- 项目初始化（pyproject.toml、目录结构）
- 配置加载（opd.yaml）
- 数据库模型 + Alembic 迁移
- Capability 基类 + Registry + 健康检查引擎
- Stage 基类 + 状态机
- Orchestrator 骨架（阶段流转 + 预检）

### Phase 2：核心阶段实现
- AI Provider（Claude Code SDK）
- SCM Provider（GitHub）
- Preparing / Clarifying / Planning / Designing / Coding / Verifying 阶段实现
- SSE 实时流

### Phase 3：Web UI
- 项目管理页（含能力配置面板）
- Story 详情页（阶段进度 + 产出展示 + 操作按钮）
- 能力健康状态面板
- AI 编码实时控制台

### Phase 4：补全能力
- CI Provider（GitHub Actions）
- Sandbox Provider（Docker）
- Doc Provider（Notion）
- Notification Provider

### Phase 5：测试 + 完善
- 单元测试（状态机、阶段校验）
- 集成测试（Mock Provider + Orchestrator）
- API 测试
- 错误处理和重试机制
