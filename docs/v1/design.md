# OPD (One Person Devs) 详细设计文档

## 1. 概述

基于调研文档（docs/research_competitive.md、docs/research_se_practices.md）的结论，OPD 需要作为一个轻量的工程迭代流程编排平台，核心价值是将 Claude Code 的编码能力融入完整的软件工程迭代流程。

**关键约束**：代码在外网（GitHub）开发发布，带到内网后替换对应组件实现。代码只能从外面进去，不能从里面出去。因此需要良好的抽象层设计。

---

## 2. Provider 抽象层设计

OPD 的核心设计理念：**所有外部依赖都通过 Provider 接口抽象**，外网和内网只是不同的 Provider 实现。

### 2.1 七大 Provider 总览

| Provider | 职责 | 外网实现 | 内网实现 |
|----------|------|---------|---------|
| RequirementProvider | 需求/Story 管理 | Notion | iCafe |
| DocumentProvider | 文档/知识库 | Notion / 本地 MD | 知识库 |
| SCMProvider | 代码管理 + Code Review | GitHub | iCode |
| SandboxProvider | 沙盒环境 | 本地 Docker | K8s / Docker |
| CIProvider | 持续集成 | GitHub Actions | Agile |
| AIProvider | AI 编码 | Claude Code | ducc |
| NotificationProvider | 通知消息 | Web 站内 / 飞书 | 如流 |

> 数据持久化不作为 Provider 抽象，统一使用 SQLAlchemy ORM，通过数据库连接串切换后端（MySQL / SQLite / PostgreSQL 等）。

### 2.2 Provider 目录结构

```
opd/providers/
├── base.py              # 所有 Provider 的基类
├── registry.py          # Provider 注册表（工厂模式）
├── requirement/         # 需求管理
│   ├── base.py          # RequirementProvider 抽象接口
│   ├── notion.py        # 外网实现：Notion
│   └── (icafe.py)       # 内网实现：iCafe（内网自行添加）
├── document/            # 文档/知识库
│   ├── base.py          # DocumentProvider 抽象接口
│   ├── notion.py        # 外网实现：Notion
│   ├── local.py         # 本地 Markdown 文件
│   └── (kb.py)          # 内网实现：知识库（内网自行添加）
├── scm/                 # 代码管理 + Code Review
│   ├── base.py          # SCMProvider 抽象接口
│   ├── github.py        # 外网实现：GitHub
│   └── (icode.py)       # 内网实现：iCode（内网自行添加）
├── sandbox/             # 沙盒环境
│   ├── base.py          # SandboxProvider 抽象接口
│   ├── docker_local.py  # 外网实现：本地 Docker
│   └── (k8s.py)         # 内网实现：K8s（内网自行添加）
├── ci/                  # 持续集成
│   ├── base.py          # CIProvider 抽象接口
│   ├── github_actions.py # 外网实现：GitHub Actions
│   └── (agile.py)       # 内网实现：Agile（内网自行添加）
├── ai/                  # AI 编码
│   ├── base.py          # AIProvider 抽象接口
│   ├── claude_code.py   # 外网实现：Claude Code（通过 Agent SDK）
│   └── (ducc.py)        # 内网实现：ducc（内网自行添加）
└── notification/        # 通知/消息
    ├── base.py          # NotificationProvider 抽象接口
    ├── web.py           # 默认实现：Web 站内通知
    ├── feishu.py        # 外网实现：飞书
    └── (ruliu.py)       # 内网实现：如流（内网自行添加）
```

> 括号 `()` 标注的文件为内网实现，不在外网仓库中，内网自行添加。

### 2.3 Provider 接口定义

#### 2.3.1 RequirementProvider（需求管理）

```python
class RequirementProvider(ABC):
    """需求/Story 的读取和管理"""

    @abstractmethod
    async def get_requirement(self, requirement_id: str) -> Requirement:
        """获取单个需求详情（标题、描述、验收标准等）"""

    @abstractmethod
    async def list_requirements(self, filters: dict) -> list[Requirement]:
        """列出需求（支持过滤）"""

    @abstractmethod
    async def update_status(self, requirement_id: str, status: str) -> None:
        """更新需求状态（如：开发中、已完成）"""
```

- 外网实现：Notion（读取 Notion database 中的 story）
- 内网实现：iCafe（读取 iCafe 中的 story）

#### 2.3.2 DocumentProvider（文档/知识库）

```python
class DocumentProvider(ABC):
    """文档和知识库的读取"""

    @abstractmethod
    async def get_document(self, doc_id: str) -> Document:
        """获取文档内容（Markdown）"""

    @abstractmethod
    async def search_documents(self, query: str) -> list[Document]:
        """搜索相关文档（用于给 AI 提供上下文）"""
```

- 外网实现：Notion / 本地 Markdown
- 内网实现：知识库

#### 2.3.3 SCMProvider（代码管理 + Code Review）

```python
class SCMProvider(ABC):
    """代码仓库管理 + Code Review"""

    # 仓库操作
    @abstractmethod
    async def clone_repo(self, repo_url: str, target_dir: str) -> None: ...
    @abstractmethod
    async def create_branch(self, repo_dir: str, branch_name: str) -> None: ...
    @abstractmethod
    async def push_branch(self, repo_dir: str, branch_name: str) -> None: ...

    # PR / Code Review
    @abstractmethod
    async def create_pull_request(self, repo: str, branch: str,
                                   title: str, body: str) -> PullRequest: ...
    @abstractmethod
    async def get_review_comments(self, repo: str, pr_id: str) -> list[ReviewComment]: ...
    @abstractmethod
    async def update_pull_request(self, repo: str, pr_id: str, **kwargs) -> None: ...
    @abstractmethod
    async def merge_pull_request(self, repo: str, pr_id: str) -> None: ...
    @abstractmethod
    async def get_pr_status(self, repo: str, pr_id: str) -> PRStatus: ...
```

- 外网实现：GitHub（PyGithub + GitPython）
- 内网实现：iCode

#### 2.3.4 SandboxProvider（沙盒）

```python
class SandboxProvider(ABC):
    """沙盒环境管理"""

    @abstractmethod
    async def create_sandbox(self, config: SandboxConfig) -> Sandbox: ...
    @abstractmethod
    async def run_command(self, sandbox_id: str, command: str) -> CommandResult: ...
    @abstractmethod
    async def destroy_sandbox(self, sandbox_id: str) -> None: ...
    @abstractmethod
    async def get_logs(self, sandbox_id: str) -> str: ...
```

- 外网实现：本地 Docker
- 内网实现：K8s / Docker

#### 2.3.5 CIProvider（持续集成）

```python
class CIProvider(ABC):
    """CI/CD 集成"""

    @abstractmethod
    async def trigger_pipeline(self, repo: str, branch: str,
                                config: CIConfig) -> Pipeline: ...
    @abstractmethod
    async def get_pipeline_status(self, pipeline_id: str) -> PipelineStatus: ...
    @abstractmethod
    async def get_pipeline_logs(self, pipeline_id: str) -> str: ...
```

- 外网实现：GitHub Actions
- 内网实现：Agile

#### 2.3.6 AIProvider（AI 编码）

```python
class AIProvider(ABC):
    """AI 编码能力"""

    @abstractmethod
    async def clarify(self, task: ClarifyTask) -> list[Question]:
        """分析需求，返回需要澄清的问题"""

    @abstractmethod
    async def plan(self, task: PlanTask) -> Plan:
        """生成实现方案（改哪些文件、大致思路）"""

    @abstractmethod
    async def code(self, task: CodingTask) -> AsyncIterator[AIMessage]:
        """执行编码任务，流式返回消息"""

    @abstractmethod
    async def revise(self, task: RevisionTask) -> AsyncIterator[AIMessage]:
        """根据 review 意见修改代码"""
```

- 外网实现：Claude Code（通过 claude-agent-sdk）
- 内网实现：ducc

**权限模式：** OPD 调用 Claude Code 时默认使用 `bypassPermissions` 模式，跳过所有权限确认（文件读写、命令执行等）。安全性通过以下方式保障：

- AI 操作的是 clone 下来的副本，不是用户主工作区
- 每个任务有独立的工作目录，互不影响
- 所有改动最终要经过人工 Review 才能合并
- 后续可通过 Docker 沙盒进一步隔离

```python
# Claude Code SDK 调用示例
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    permission_mode="bypassPermissions",
    allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
    cwd="/workspace/tasks/{task_id}/repo",
    system_prompt="你是一个资深开发者，根据需求文档修改代码..."
)

async for message in query(prompt=requirement_text, options=options):
    # 处理 AI 的输出、提问、编码进度等
    pass
```

#### 2.3.7 NotificationProvider（通知/消息）

```python
class NotificationProvider(ABC):
    """任务状态变更通知"""

    @abstractmethod
    async def notify(self, user_id: str, event: TaskEvent) -> None:
        """发送通知（任务状态变更、AI 提问、Review 完成等）"""

    @abstractmethod
    async def notify_batch(self, user_ids: list[str], event: TaskEvent) -> None:
        """批量通知"""
```

- 外网实现：Web 站内通知（默认）/ 飞书
- 内网实现：如流

### 2.4 Provider 注册与配置

通过配置文件选择使用哪些 Provider 实现：

```yaml
# opd.yaml
providers:
  requirement:
    type: notion              # 或 icafe
    config:
      api_key: xxx
      database_id: xxx
  document:
    type: local               # 或 notion / kb
    config:
      base_dir: ./docs
  scm:
    type: github              # 或 icode
    config:
      token: xxx
  sandbox:
    type: docker_local        # 或 k8s
  ci:
    type: github_actions      # 或 agile
  ai:
    type: claude_code         # 或 ducc
    config:
      model: opus
  notification:
    type: web                 # 或 feishu / ruliu
    config: {}

# 数据库配置（SQLAlchemy 连接串）
database:
  url: "mysql://user:pass@host:3306/opd"  # 或 sqlite:///opd.db
```

Provider 通过工厂模式加载：

```python
class ProviderRegistry:
    """Provider 注册表，支持插件式扩展"""

    def register(self, category: str, name: str, cls: type) -> None:
        """注册一个 Provider 实现"""

    def create(self, category: str, name: str, config: dict) -> Provider:
        """根据 category + name 创建 Provider 实例"""
```

**内网适配只需要：**

1. 实现对应的 Provider 类（如 `IcafeRequirementProvider`、`DuccAIProvider`、`RuliuNotificationProvider`）
2. 在配置文件中切换 `type`
3. 不需要改动任何核心代码

---

## 3. 业务模型

### 3.1 三层结构：Project → Story → Round

```
Project（项目）= 一个代码仓库
├── 项目级上下文（架构、规范、技术栈、历史决策...）
│
├── Story #1（需求/功能）
│   ├── Story 级上下文（需求文档、Q&A、相关文档...）
│   ├── Round 1 (initial) → 编码 → PR#1 → Review → 废弃
│   ├── Round 2 (restart) → 编码 → PR#2 → Review → 通过
│   └── Round 3 (iterate) → 修改 → PR#2 更新 → 合并 ✓
│
├── Story #2
│   └── Round 1 (initial) → 编码 → PR#3 → 合并 ✓
│
└── Story #3（进行中）
    └── Round 1 (initial) → 编码中...
```

### 3.2 数据模型

#### Project（项目）

一个 Project 对应一个代码仓库，是**上下文的根**。

```python
class Project:
    id: str
    name: str
    repo_url: str
    description: str

    # 项目级上下文（AI 每次编码都会带上）
    tech_stack: str              # 技术栈描述
    architecture: str            # 架构说明
    context_docs: list[str]      # 关联的知识库文档 ID

    # Rules（项目规则，AI 编码时必须遵守）
    rules: list[Rule]

    # Skills（Claude Code 自定义技能）
    skills: list[Skill]

    # 历史积累
    stories: list[Story]
    decisions: list[Decision]    # 重要技术决策记录
```

#### Rule（项目规则）

研发人员在 Web 上为项目配置的规则，AI 编码时自动注入。

```python
class Rule:
    id: str
    category: str        # coding / architecture / testing / git / forbidden
    content: str         # 规则内容（自然语言）
    enabled: bool        # 是否启用
```

**规则分类：**

| 类别 | 示例 |
|------|------|
| coding | "使用 type hints"、"函数不超过 50 行"、"使用 f-string 而非 format" |
| architecture | "所有 API 必须经过鉴权中间件"、"数据库操作必须走 Repository 层" |
| testing | "新增函数必须有单元测试"、"覆盖率不低于 80%" |
| git | "branch 命名: feature/xxx"、"commit message 使用 conventional commits" |
| forbidden | "不要修改 xxx 模块"、"不要引入新的第三方依赖" |

Rules 在调用 Claude Code 时会被拼入 system prompt，或生成为 `CLAUDE.md` 放到工作目录中。

#### Skill（项目技能）

为项目配置的 Claude Code 自定义技能，本质是预定义的命令 + 触发时机。

```python
class Skill:
    id: str
    name: str            # skill 名称（如 run-tests）
    description: str     # 描述（给 AI 看的）
    command: str         # 要执行的命令（如 pytest -x tests/）
    trigger: str         # auto_after_coding / auto_before_pr / manual
```

**触发时机：**

| trigger | 说明 |
|---------|------|
| auto_after_coding | AI 编码完成后自动执行（如跑测试、lint 检查） |
| auto_before_pr | 创建 PR 前自动执行（如构建验证） |
| manual | 手动触发（如数据库迁移） |

Skills 通过 Claude Code SDK 的 MCP 机制注入：

```python
options = ClaudeAgentOptions(
    permission_mode="bypassPermissions",
    cwd=work_dir,
    system_prompt=build_system_prompt(project),  # 包含 rules
    mcp_servers={"project-tools": build_project_skills(project)}
)
```

#### Story（需求/功能）

一个 Story 对应一个需求或功能点。

```python
class Story:
    id: str
    project_id: str
    title: str
    requirement: str             # 需求文档（Markdown）
    requirement_source: str      # 来源（Notion/iCafe/手动上传）
    requirement_id: str | None   # 外部需求系统的 ID

    # Story 级上下文
    related_docs: list[str]      # 相关文档
    clarifications: list[QA]     # 澄清问答记录
    acceptance_criteria: str     # 验收标准

    # 迭代历史
    rounds: list[Round]
    current_round: int
    status: StoryStatus          # pending / in_progress / done / cancelled
```

#### Round（迭代轮次）

一个 Round 是一次完整的"编码 → Review"循环。

```python
class Round:
    id: str
    story_id: str
    round_number: int
    type: "initial" | "iterate" | "restart"

    # 当轮快照
    requirement_snapshot: str    # 当轮的需求理解
    context_summary: str         # AI 对上下文的总结

    # Git / PR
    branch_name: str
    pr_id: str | None
    pr_status: "open" | "closed" | "merged"

    # 过程记录
    ai_messages: list[AIMessage]
    review_comments: list[Comment]
    close_reason: str | None     # 结束原因（restart 时记录）

    status: RoundStatus
```

### 3.3 上下文传递机制

AI 每次编码时收到的 prompt 由三层上下文组合而成：

```
AI prompt =
    项目级上下文（Project）
    ├── 技术栈、架构、编码规范
    ├── 历史 Story 摘要（之前做过什么、踩过什么坑）
    │
    + Story 级上下文
    ├── 需求文档
    ├── 相关知识库文档
    ├── 澄清问答记录
    │
    + Round 级上下文
    ├── 上一轮的失败原因（如果是 iterate/restart）
    ├── 上一轮的 Review comments
    └── 当轮的具体指令
```

```python
def build_ai_prompt(project: Project, story: Story, round: Round) -> str:
    """构建给 AI 的完整 prompt"""
    sections = []

    # 项目级
    sections.append(f"## 项目背景\n{project.description}")
    sections.append(f"## 技术栈\n{project.tech_stack}")
    sections.append(f"## 编码规范\n{project.coding_conventions}")

    # 历史 Story 摘要（避免 token 爆炸，只给摘要）
    completed = [s for s in project.stories if s.status == "done"]
    if completed:
        summaries = [f"- {s.title}: {s.summary}" for s in completed[-10:]]
        sections.append(f"## 近期完成的功能\n" + "\n".join(summaries))

    # Story 级
    sections.append(f"## 当前需求\n{story.requirement}")
    if story.clarifications:
        qa_text = "\n".join(f"Q: {qa.q}\nA: {qa.a}" for qa in story.clarifications)
        sections.append(f"## 需求澄清\n{qa_text}")

    # Round 级
    if round.type == "restart":
        prev = story.rounds[round.round_number - 2]
        sections.append(f"## 上一轮失败原因\n{prev.close_reason}")
        sections.append("请避免重蹈覆辙。")
    elif round.type == "iterate":
        prev = story.rounds[round.round_number - 2]
        comments = "\n".join(c.body for c in prev.review_comments)
        sections.append(f"## Review 意见\n{comments}")

    return "\n\n".join(sections)
```

---

## 4. 核心编排引擎

### 4.1 任务状态机

任务采用 **Round（轮次）** 模型。每个任务可以有多轮迭代，每轮内部走一个线性状态流，轮次之间可以选择"迭代"或"废弃重来"。

#### Round 内部状态流

```
clarifying → planning → coding → pr_created → reviewing → revising → testing → done
                                                  ↑            │
                                                  └────────────┘
                                                  (Review 后修改)
```

#### Round 之间的关系

```
Round N (reviewing / revising / testing)
    │
    ├── iterate（迭代）  → Round N+1 (planning, 同 branch, 在已有代码上继续改)
    └── restart（重来）  → Round N+1 (clarifying, 新 branch, 关闭旧 PR)
```

**状态说明：**

| 状态 | 说明 | 触发条件 |
|------|------|---------|
| created | 任务刚创建（仅首轮） | 用户提交任务 |
| clarifying | AI 分析需求并提问，等待人回答 | AI 发现需求有歧义 / restart 新轮次 |
| planning | AI 输出实现方案，等待人确认 | 需求澄清完成 |
| coding | AI 正在编码 | 用户确认方案 / iterate 新轮次 |
| pr_created | PR 已创建，等待 Review | AI 编码完成 |
| reviewing | 研发人员正在 Review | PR 创建后自动进入 |
| revising | AI 根据反馈修改中 | 用户触发（PR comments 或人工 prompt） |
| testing | 沙盒测试中 | 用户触发测试 |
| done | 完成 | PR 合并 |

#### Round 数据模型

```python
class Round:
    round_number: int              # 轮次编号
    type: "initial" | "iterate" | "restart"
    requirement_snapshot: str      # 当轮的需求理解
    branch_name: str               # Git branch
    pr_id: str | None              # PR 编号
    pr_status: "open" | "closed" | "merged"
    close_reason: str | None       # 废弃原因（restart 时记录）
    ai_messages: list[AIMessage]   # AI 编码过程记录
    status: TaskStatus             # 当轮状态
```

#### 用户操作

| 操作 | 效果 |
|------|------|
| **迭代修改（iterate）** | 在当前 branch/PR 上继续改，AI 带着上下文 |
| **废弃重来（restart）** | 关闭当前 PR，从 main 新拉 branch，AI 知道上轮失败原因以避免重蹈覆辙 |
| **更新需求** | 修改需求文档后，可选择 iterate 或 restart |

### 4.2 核心流程（Orchestrator）

```python
class Orchestrator:
    """核心编排器，串联各 Provider 完成完整流程"""

    async def handle_create_task(self, req: CreateTaskRequest):
        # 1. 从 RequirementProvider 获取需求（或直接使用上传的 MD）
        # 2. 从 DocumentProvider 获取相关文档（可选，作为 AI 上下文）
        # 3. 创建 Task 记录
        # 4. 调用 AIProvider.clarify() 分析需求
        # 5. 如果有问题 → 状态转为 clarifying
        # 6. 如果无问题 → 状态转为 planning

    async def handle_answer_questions(self, task_id, answers):
        # 1. 记录回答
        # 2. 调用 AIProvider.plan() 生成实现方案
        # 3. 状态转为 planning

    async def handle_confirm_plan(self, task_id, approved, feedback=None):
        # 1. 如果 approved:
        #      调用 AIProvider.code() 开始编码
        #      状态转为 coding
        # 2. 如果不 approved:
        #      将 feedback 传给 AI 重新规划
        #      保持 planning 状态

    async def handle_coding_complete(self, task_id):
        # 1. SCMProvider.create_branch()
        # 2. SCMProvider.push_branch()
        # 3. SCMProvider.create_pull_request()
        # 4. NotificationProvider.notify() 通知研发人员
        # 5. 状态转为 pr_created

    async def handle_trigger_revision(self, task_id, mode, prompt=None):
        # mode = "comments" | "prompt"
        # 1. 如果 mode == "comments":
        #      从 SCMProvider.get_review_comments() 获取 comments
        # 2. 如果 mode == "prompt":
        #      使用人工输入的 prompt
        # 3. 调用 AIProvider.revise()
        # 4. push 更新到 PR
        # 5. NotificationProvider.notify() 通知修改完成
        # 6. 状态转为 reviewing

    async def handle_new_round(self, task_id, round_type, reason=None, new_requirement=None):
        # round_type = "iterate" | "restart"
        # 1. 记录当前 round 的结束原因
        # 2. 如果 round_type == "restart":
        #      关闭当前 PR
        #      从 main 新拉 branch
        #      状态转为 clarifying
        # 3. 如果 round_type == "iterate":
        #      保持当前 branch
        #      状态转为 coding
        # 4. 如果有 new_requirement，更新需求文档
        # 5. 创建新 Round 记录，携带上轮失败原因作为 AI 上下文

    async def handle_trigger_test(self, task_id):
        # 1. SandboxProvider.create_sandbox()
        # 2. CIProvider.trigger_pipeline() 或直接在沙盒中跑测试
        # 3. 状态转为 testing

    async def handle_merge(self, task_id):
        # 1. SCMProvider.merge_pull_request()
        # 2. RequirementProvider.update_status() 更新需求状态
        # 3. 状态转为 done
```

---

## 5. 项目结构

```
one-person-devs/
├── docs/
│   ├── research_competitive.md  # 竞品调研
│   ├── research_se_practices.md # 软件工程最佳实践调研
│   └── design.md                # 详细设计文档（本文件）
├── opd/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 应用入口 + opd serve 命令
│   ├── config.py                # 配置加载（opd.yaml）
│   ├── models/                  # 数据模型
│   │   ├── project.py           # Project
│   │   ├── story.py             # Story, StoryStatus
│   │   ├── round.py             # Round, RoundStatus, RoundType
│   │   ├── requirement.py       # Requirement
│   │   ├── document.py          # Document
│   │   └── review.py            # ReviewComment, PullRequest
│   ├── providers/               # Provider 抽象层（见第 2 章）
│   │   └── ...
│   ├── engine/                  # 编排引擎
│   │   ├── task_manager.py      # 任务生命周期管理
│   │   ├── state_machine.py     # 状态机定义与转换
│   │   └── orchestrator.py      # 流程编排（串联各 Provider）
│   ├── api/                     # HTTP API
│   │   ├── tasks.py             # 任务 CRUD + 状态操作
│   │   ├── questions.py         # AI 提问 / 人工回答
│   │   └── webhooks.py          # GitHub webhook 接收
│   ├── db/                      # 数据库（SQLAlchemy）
│   │   ├── models.py            # ORM 模型定义
│   │   └── session.py           # 数据库连接管理
│   └── web/                     # 前端（Jinja2 模板，MVP 阶段）
│       ├── templates/
│       └── static/
├── tests/
├── opd.yaml.example             # 配置示例
├── pyproject.toml
└── README.md
```

---

## 6. Web API 设计

### Project

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/projects | 创建项目 |
| GET | /api/projects | 项目列表 |
| GET | /api/projects/{id} | 项目详情 |
| PUT | /api/projects/{id} | 更新项目（技术栈、规范等） |

### Story

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/projects/{pid}/stories | 创建 Story |
| GET | /api/projects/{pid}/stories | Story 列表 |
| GET | /api/stories/{id} | Story 详情 |
| POST | /api/stories/{id}/answer | 回答 AI 的问题 |
| GET | /api/stories/{id}/plan | 查看 AI 的实现方案 |
| POST | /api/stories/{id}/confirm-plan | 确认/拒绝实现方案 |
| POST | /api/stories/{id}/revise | 触发 AI 修改（mode: comments / prompt） |
| POST | /api/stories/{id}/new-round | 开启新轮次（type: iterate / restart） |
| POST | /api/stories/{id}/test | 触发沙盒测试 |
| POST | /api/stories/{id}/merge | 合并 PR |
| GET | /api/stories/{id}/logs | 查看 AI 编码日志（支持流式） |

### Webhook

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/webhooks/github | GitHub webhook（PR 事件） |

---

## 7. 实施计划

### Phase 1: 骨架 + Provider 抽象

- [ ] 项目初始化（pyproject.toml, 目录结构）
- [ ] Provider 基类和注册机制
- [ ] 配置加载（opd.yaml）
- [ ] 数据模型定义
- [ ] 数据库层（SQLAlchemy ORM + Alembic 迁移）

### Phase 2: 核心流程（最小可用）

- [ ] 任务状态机
- [ ] Orchestrator 编排逻辑
- [ ] AIProvider (Claude Code SDK) 实现
- [ ] SCMProvider (GitHub) 实现
- [ ] FastAPI 路由

### Phase 3: Web 界面（MVP）

- [ ] 任务列表页
- [ ] 创建任务页（上传 Markdown 需求文档）
- [ ] 任务详情页（状态、日志、问答、触发修改）

### Phase 4: 补全 Provider

- [ ] RequirementProvider (Notion) 实现
- [ ] DocumentProvider (Notion / Local) 实现
- [ ] SandboxProvider (Docker) 实现
- [ ] CIProvider (GitHub Actions) 实现
- [ ] NotificationProvider (飞书) 实现

### Phase 5: 完善

- [ ] 错误处理和重试
- [ ] 日志和监控
- [ ] 配置校验
- [ ] 使用文档

### 二期规划：记忆模块

一期的上下文传递是基于结构化数据的拼接（Project/Story/Round 的字段）。二期计划引入更智能的记忆模块：

- [ ] **自动摘要**：每个 Story 完成后，AI 自动生成摘要（做了什么、关键决策、踩过的坑），存入 Project 级上下文
- [ ] **决策记录自动提取**：从 Review comments 和修改历史中自动提取技术决策（如"选择了方案 A 而非方案 B，因为..."）
- [ ] **编码规范自动学习**：从 Review 反馈中提取编码规范偏好（如"团队偏好组合优于继承"），自动更新 Project 的 coding_conventions
- [ ] **相关 Story 检索**：新 Story 开始时，基于语义相似度检索历史上相关的 Story，作为参考上下文
- [ ] **上下文压缩**：当项目历史过长时，智能压缩历史上下文，保留关键信息，控制 token 用量
- [ ] **知识图谱**：构建项目的代码结构、模块依赖、API 关系的知识图谱，辅助 AI 理解项目全貌

---

## 8. 验证方式

1. 启动 `opd serve`，打开 Web 界面
2. 创建一个任务：指定 GitHub repo + 上传 Markdown 需求文档
3. AI 分析需求并提问 → 在 Web 上回答
4. AI 编码完成 → 自动创建 GitHub PR
5. 在 GitHub 上 Review，添加 comments
6. 回到 Web 上点"根据 Review 修改"或直接写 prompt → AI 修改并更新 PR
7. Accept → 触发测试 → 合并

---

## 9. 测试策略

### 8.1 测试分层

```
┌─────────────────────────────────────┐
│  E2E 测试（可选，需要真实环境）        │  ← 真实 GitHub API / Docker
├─────────────────────────────────────┤
│  API 测试（FastAPI TestClient）       │  ← HTTP 接口层
├─────────────────────────────────────┤
│  集成测试（Mock Provider）            │  ← Orchestrator 编排逻辑
├─────────────────────────────────────┤
│  单元测试（纯逻辑）                   │  ← 状态机、配置、模型
└─────────────────────────────────────┘
```

### 8.2 各层详细说明

#### 第 1 层：单元测试（核心，必须有）

测试不依赖外部服务的纯逻辑部分：

- 状态机的每个转换路径（合法转换 + 非法转换抛异常）
- 配置加载和校验
- 数据模型的序列化/反序列化

```python
# 示例：状态机测试
def test_state_transition_coding_to_pr_created():
    sm = StateMachine()
    task = Task(status=TaskStatus.CODING)
    sm.transition(task, TaskStatus.PR_CREATED)
    assert task.status == TaskStatus.PR_CREATED

def test_invalid_transition_raises():
    sm = StateMachine()
    task = Task(status=TaskStatus.CREATED)
    with pytest.raises(InvalidTransitionError):
        sm.transition(task, TaskStatus.REVIEWING)
```

#### 第 2 层：集成测试（Mock Provider）

每个 Provider 写一个 Mock 实现，用于测试 Orchestrator 的编排逻辑：

```python
# 示例：Mock SCM Provider
class MockSCMProvider(SCMProvider):
    def __init__(self):
        self.branches = []
        self.pull_requests = []
        self.comments = []

    async def create_branch(self, repo_dir, branch_name):
        self.branches.append(branch_name)

    async def create_pull_request(self, repo, branch, title, body):
        pr = PullRequest(id="mock-1", title=title)
        self.pull_requests.append(pr)
        return pr

    async def get_review_comments(self, repo, pr_id):
        return self.comments
```

用 Mock Provider 可以测试完整流程而不依赖任何外部服务。

#### 第 3 层：API 测试

用 FastAPI 的 TestClient 测试 HTTP 接口：

```python
def test_create_task(client: TestClient, mock_providers):
    resp = client.post("/api/tasks", json={
        "repo_url": "https://github.com/test/repo",
        "requirement": "# 需求\n添加登录功能"
    })
    assert resp.status_code == 201
    assert resp.json()["status"] == "created"
```

#### 第 4 层：E2E 测试（可选）

针对真实 GitHub API、Docker 等做端到端测试：

- 使用专门的测试 repo
- 通过环境变量控制是否执行（`INTEGRATION_TEST=1`）
- 不在本地开发时默认运行，仅在 CI 中执行

### 8.3 测试目录结构

```
tests/
├── unit/
│   ├── test_state_machine.py
│   ├── test_config.py
│   └── test_models.py
├── integration/
│   ├── conftest.py              # Mock Provider fixtures
│   ├── test_orchestrator.py
│   └── test_api.py
├── e2e/                         # 可选，需要真实环境
│   ├── test_github_provider.py
│   └── test_docker_sandbox.py
└── mocks/
    ├── mock_scm.py
    ├── mock_ai.py
    ├── mock_sandbox.py
    └── mock_notification.py
```

### 8.4 工具选型

| 工具 | 用途 |
|------|------|
| pytest | 测试框架 |
| pytest-asyncio | 异步测试支持 |
| pytest-cov | 覆盖率统计 |
| httpx | FastAPI 异步测试客户端 |

### 8.5 覆盖率目标

| 模块 | 目标覆盖率 |
|------|-----------|
| 核心引擎（状态机、Orchestrator） | > 90% |
| Provider 实现 | > 70% |
| API 层 | > 80% |
