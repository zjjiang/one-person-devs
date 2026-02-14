# OPD v2 业务模型框架

## 1. 概述

v1 完成了核心流程的可行性验证，但每个阶段更多是"API调用的wrapper"，缺乏对软件工程方法论的深度定义。

v2 的核心目标：
- 将每个状态从"技术实现细节"提升到"软件工程方法论"层面
- 严格定义每个阶段的输入、输出、人类参与点，让 human-in-the-loop 真正有意义
- 引入 Story → Task 两层模型，支持需求拆分和并行执行
- 基础设施分层：GitHub 是底座，Claude Code 是灵魂，贯穿每个工程步骤

## 2. 领域模型

### 2.1 核心层级：Project → Story → Task

```
Project（项目）= 一个代码仓库
├── Rules（编码规范、架构约束、禁止项...）
├── Skills（可复用的自动化能力）
└── Stories
      ├── Requirement（需求描述 + 验收标准）
      ├── Technical Design（技术方案，Planning 阶段产出）
      ├── feature_tag（可选标签，用于分组筛选，不参与状态流）
      └── Tasks
            ├── Detailed Design（详细设计）
            ├── Implementation Plan（实施计划）
            ├── Dependencies（依赖的其他 Task，形成 DAG）
            ├── Rounds（迭代轮次：iterate / restart）
            └── PR（1 Task = 1 PR）
```

### 2.2 关于 Feature

公司标准流程为 Epic → Feature → Story → Task。OPD v2 的处理：
- Epic：粒度太大，不纳入系统管理
- Feature：降级为 Story 上的轻量标签（`feature_tag` 字段），用于分组和筛选，不参与状态流
- Story → Task：核心两层模型，各自有独立的状态机

如果后续确实需要 Feature 级别的编排能力，再升级为独立实体。

## 3. 状态机

### 3.1 Story Level 状态流

```
Created ──→ Clarifying ──→ Planning ──→ Executing ──→ Regression ──→ Done
                │              │                          │
                │              ├─ Gate 1: 技术方案审批       │
                │              └─ Gate 2: Task拆分审批      │
                │                                         │
                └─ PM提需求，AI提问                         └─ 自动化测试 + 人工验证
                   人类回答澄清问题
```

状态说明：

| 状态 | 说明 | 进入条件 | 退出条件 |
|------|------|---------|---------|
| Created | Story 刚创建 | 用户提交需求 | 自动进入 Clarifying |
| Clarifying | AI 分析需求并提问，等待人类回答 | Story 创建后 | 人类回答完所有问题 |
| Planning | AI 做技术方案设计 + Task 拆分 | 需求澄清完成 | 人类审批通过方案和 Task 拆分 |
| Executing | 容器状态，Task 各自执行 | Planning 审批通过 | 所有 Task 状态为 Done |
| Regression | Story 级回归验证 | 所有 Task 完成 | 自动化测试通过 + 人工验证通过 |
| Done | Story 完成 | 回归验证通过 | - |

### 3.2 Task Level 状态流

```
Created ──→ Designing ──→ Coding ──→ PR Created ──→ Reviewing ──→ Testing ──→ Done
                │                                       │            │
                ├─ Gate 1: 详细设计审批                    │            │
                └─ Gate 2: 实施计划审批                    │            │
                                                         │            │
                              ┌── iterate ───────────────┘            │
                              └── restart ────────────────────────────┘
```

状态说明：

| 状态 | 说明 | 进入条件 | 退出条件 |
|------|------|---------|---------|
| Created | Task 刚创建（由 Planning 阶段产出） | Story Planning 完成 | 前置依赖 Task 全部 Done（或无依赖） |
| Designing | AI 做详细设计 + 实施计划 | 依赖满足 | 人类审批通过详细设计和实施计划 |
| Coding | AI 编码中 | 设计审批通过 | AI 编码完成 |
| PR Created | PR 已创建，等待 Review | AI 编码完成，自动提 PR | 人类开始 Review |
| Reviewing | 人工代码审查 | PR 创建后 | approve 或 request changes |
| Testing | 沙盒环境人工测试 | Code Review 通过 | 测试通过或失败 |
| Done | Task 完成 | 测试通过，PR 合并 | - |

### 3.3 回退模型（Round）

Task 保留 v1 的 iterate / restart 轮次机制：

| 操作 | 触发时机 | 效果 |
|------|---------|------|
| iterate | Review 发现小问题 | 回到 Coding，同分支同 PR 继续改 |
| restart | 方案有根本问题 | 开新 Round，从 Designing 重新开始，新分支，关闭旧 PR |

每个 Round 记录：
- 轮次编号、类型（initial / iterate / restart）
- 分支名、PR 信息
- AI 消息记录
- 结束原因（restart 时记录，作为下一轮的上下文）

## 4. 阶段定义（Input / Output / Human Gate）

### 4.1 Story Level 阶段

#### Clarifying（需求澄清）

- 角色映射：PM 提需求，RD（AI辅助）做需求分析
- 输入：原始需求描述 + 项目上下文（tech stack, architecture, rules）
- 输出：结构化需求规格（明确的 scope、边界条件、验收标准）
- AI 角色：需求分析师 — 分析需求，提出澄清问题
- 人类参与：回答 AI 的澄清问题，确认需求理解无误
- 依赖能力：AI

#### Planning（技术方案设计 + Task 拆分）

这是 v2 相比 v1 变化最大的阶段。包含两个子步骤，各有独立门禁：

**子步骤 1：Technical Design（技术方案设计）**
- 输入：结构化需求 + 代码库现状
- 输出：技术方案文档（自由格式）— 包含架构变更、数据模型变更、接口变更、备选方案对比、风险评估
- AI 角色：架构师 — 分析代码库，设计实现方案
- 人类门禁：审批技术方案（通过 / 打回修改）
- 依赖能力：AI + SCM（读代码库）

**子步骤 2：Task Breakdown（任务拆分）**
- 输入：已确认的技术方案
- 输出：Task 列表，每个 Task 包含：描述、范围、依赖关系、验收标准
- AI 角色：Tech Lead — 将方案拆分为可执行的 Task
- 人类门禁：审批 Task 拆分（调整粒度、修改依赖、增删 Task）
- 依赖能力：AI

#### Executing（执行中）

- 容器状态，本身无逻辑
- 进入条件：Planning 的两个门禁都通过
- 退出条件：所有 Task 状态为 Done
- Task 按 DAG 依赖关系调度执行

#### Regression（回归验证）

- 输入：所有 PR 已合并的代码 + Story 验收标准
- 输出：回归测试结果（pass / fail）
- 人类参与：自动化测试 + 沙盒环境人工验证
- 依赖能力：CI + Sandbox

### 4.2 Task Level 阶段

#### Designing（详细设计）

同样包含两个子步骤，各有独立门禁：

**子步骤 1：Detailed Design（详细设计）**
- 输入：Task 描述 + Story 级技术方案 + 代码库现状
- 输出：详细设计文档 — 做什么、怎么做、技术方案细节
- AI 角色：高级开发者 — 基于整体方案，细化当前 Task 的实现方案
- 人类门禁：审批详细设计
- 依赖能力：AI + SCM（读代码库）

**子步骤 2：Implementation Plan（实施计划）**
- 输入：已确认的详细设计
- 输出：具体实施计划 — 改哪些文件、每个文件的改动说明
- AI 角色：开发者 — 将设计转化为具体的代码变更计划
- 人类门禁：审批实施计划
- 依赖能力：AI + SCM（读代码库）

#### Coding（AI 编码）

- 输入：确认的实施计划 + 代码库
- 输出：代码变更（diff）
- AI 角色：开发者 — 按照实施计划编写代码
- 人类参与：可选的中间检查点（通过 SSE 实时观察编码过程）
- 依赖能力：AI + SCM（分支 / 提交）

#### PR Created（提交 PR）

- 输入：代码变更
- 输出：PR 链接
- 自动阶段，无人类门禁
- 依赖能力：SCM（创建 PR）

#### Reviewing（代码审查）

- 输入：PR diff + 需求 + 技术方案
- 输出：approve / request changes
- 人类参与：人工静态代码审查（这是人类的核心价值所在）
- AI 角色：不参与独立判断，Review 完全由人类主导
- 依赖能力：SCM（PR Review）

#### Testing（测试验证）

- 输入：PR 代码 + Task 验收标准
- 输出：测试通过 / 失败
- 人类参与：沙盒环境人工测试
- 依赖能力：Sandbox

## 5. 基础设施分层

阶段定义（纵向）和基础设施能力（横向）是两个独立维度。阶段消费能力，能力有不同的实现（外网/内网）。

### 5.1 三层架构

```
Layer 1 - Capabilities（能力声明）
┌────────┬────────┬────────┬────────┬─────────┬─────────┐
│   AI   │  SCM   │   CI   │  Doc   │ Sandbox │ Notify  │
└────────┴────────┴────────┴────────┴─────────┴─────────┘
    ↑          ↑        ↑        ↑        ↑         ↑
Layer 2 - Providers（可插拔实现）
┌──────────┬──────────┬──────────┬────────┬────────┬───────┐
│Claude    │GitHub    │GH Actions│Local   │Docker  │Slack  │
│Code      │iCode     │Jenkins   │Notion  │K8s     │Web    │
└──────────┴──────────┴──────────┴────────┴────────┴───────┘
    ↑          ↑        ↑        ↑        ↑         ↑
Layer 3 - Environment（网络环境）
┌─────────────────────┬─────────────────────┐
│  External（外网）     │  Internal（内网）     │
│  github.com          │  icode.xxx.com      │
│  anthropic API       │  internal LLM       │
└─────────────────────┴─────────────────────┘
```

### 5.2 阶段 → 能力依赖矩阵

| 阶段 | AI | SCM | CI | Doc | Sandbox | Notify |
|------|:--:|:---:|:--:|:---:|:-------:|:------:|
| Clarifying | ✓ | | | | | |
| Planning | ✓ | ✓(读) | | | | |
| Designing | ✓ | ✓(读) | | | | |
| Coding | ✓ | ✓(写) | | | | |
| PR Created | | ✓ | | | | ✓ |
| Reviewing | | ✓ | | | | |
| Testing | | | | | ✓ | |
| Regression | | | ✓ | | ✓ | |
| 全局 | | | | | | ✓ |

### 5.3 核心设计原则

- 阶段定义是稳定的（软件工程方法论不变）
- 能力是抽象的（不绑定具体工具）
- Provider 是可替换的（外网 GitHub 换成内网 iCode，只换 Provider 层）
- 环境是配置化的（同一套系统部署在不同网络环境，只改配置）

## 6. Task 并行模型

### 6.1 DAG 调度

Task 之间的依赖关系在 Planning 阶段由 AI 建议、人类确认，形成有向无环图（DAG）。

示例：

```
Story: "给商品详情页添加评论功能"

Planning 产出的 Task DAG:

  Task A (数据库迁移：评论表)
       │
       ├──→ Task B (后端API：评论 CRUD)
       │         │
       │         └──→ Task D (前后端集成联调)
       │                ↑
       └──→ Task C (前端页面：评论组件) ──┘
```

### 6.2 执行策略

- 无依赖的 Task 可并行执行（上例中 A 先执行，B 和 C 可并行）
- 有依赖的 Task 等前置 Task Done 后自动触发
- 人类可手动调整执行顺序和并行度
- 每个 Task 独立走自己的状态流（Designing → Coding → ... → Done）

### 6.3 Story 完成条件

所有 Task Done ≠ Story Done。还需要：
1. 所有 Task 的 PR 已合并
2. Story 级回归验证通过（自动化测试 + 人工验证）
3. 人类确认 Story 完成

## 7. v1 → v2 关键变化总结

| 维度 | v1 | v2 |
|------|----|----|
| 工作单元 | Story → Round（1 Story = 1 PR） | Story → Task → Round（1 Story = N PR） |
| 状态机 | 单层（Round 级） | 两层（Story 级 + Task 级） |
| Planning | 一次性产出方案，一键确认 | 技术方案 + Task 拆分，两次门禁 |
| Task 设计 | 无 | Detailed Design + Implementation Plan，两次门禁 |
| 并行 | 不支持 | Task DAG 并行调度 |
| Review | AI 可参与 | 人工主导，AI 不做独立判断 |
| 回归 | 无 | Story 级回归验证（自动化 + 人工） |
| 基础设施 | Provider 抽象（2层） | 能力 → Provider → 环境（3层） |
| Feature | 无 | 轻量标签（不参与状态流） |
| 人类门禁 | 部分阶段 | 所有阶段均需人类确认 |
