# OPD v2 业务模型框架

## 1. 概述

v1 完成了核心流程的可行性验证，但每个阶段更多是"API调用的wrapper"，缺乏对软件工程方法论的深度定义。

v2 的核心目标：
- 将每个状态从"技术实现细节"提升到"软件工程方法论"层面
- 严格定义每个阶段的输入、输出、人类参与点，让 human-in-the-loop 真正有意义
- 基础设施分层：GitHub 是底座，Claude Code 是灵魂，贯穿每个工程步骤

## 2. 领域模型

### 2.1 核心层级：Project → Story → Task

```
Project（项目）= 一个代码仓库
├── Rules（编码规范、架构约束、禁止项...）
├── Skills（可复用的自动化能力）
└── Stories
      ├── PRD（需求文档，Preparing 阶段产出）
      ├── Technical Design（概要设计，Planning 阶段产出）
      ├── Detailed Design（详细设计，Designing 阶段产出，一份文档覆盖所有 Task）
      ├── feature_tag（可选标签，用于分组筛选，不参与状态流）
      ├── Tasks（设计层面的组织单元，不是独立执行实体）
      │     ├── 描述 + 范围
      │     ├── 依赖关系（DAG）
      │     └── 验收标准
      ├── Rounds（迭代轮次：iterate / restart）
      └── PR（单仓库 1 个 PR，多仓库每个仓库 1 个 PR）
```

### 2.2 Task 的定位

Task 是 Planning 阶段的产出物，是设计文档的组织单元，不是独立的执行实体：
- Task 在 Planning 阶段由 AI 建议、人类确认
- Task 有描述、范围、依赖关系，但没有自己的状态机
- Designing 阶段产出一份详细设计文档覆盖所有 Task
- Coding 阶段 AI 按 Task 依赖顺序编码，但对外是一个整体

### 2.3 多仓库场景

当 Story 涉及多个代码仓库时：
- Task 按仓库自然分组
- Coding 阶段按仓库分别编码，每个仓库产出独立的 PR
- Verifying 阶段需要验证所有仓库的 PR
- 1 Story = N PRs（N = 涉及的仓库数量）

### 2.3 关于 Feature

公司标准流程为 Epic → Feature → Story → Task。OPD v2 的处理：
- Epic：粒度太大，不纳入系统管理
- Feature：降级为 Story 上的轻量标签（`feature_tag` 字段），用于分组和筛选，不参与状态流
- Story：核心工作单元，有完整的状态机
- Task：设计层面的子单元，无独立状态机

如果后续确实需要 Feature 级别的编排能力，再升级为独立实体。

## 3. 状态机

### 3.1 Story 状态流（单层）

```
Preparing → Clarifying → Planning → Designing → Coding → Verifying → Done
    │           │            │           │          │          │
    │           │            │           │          │          ├─ Code Review
    │           │            │           │          │          ├─ 沙盒功能验证
    │           │            │           │          │          └─ 产研确认
    │           │            │           │          │
    │           │            │           │          └─ AI 一次性编码所有 Task
    │           │            │           │             按依赖顺序，产出 1 个 PR
    │           │            │           │
    │           │            │           └─ 所有 Task 的详细设计（一份文档）
    │           │            │              产研确认
    │           │            │
    │           │            ├─ 概要设计（整体怎么做）
    │           │            └─ Task 拆分 + 依赖关系
    │           │               产研确认
    │           │
    │           └─ AI 提问，人类回答
    │              复述需求，产研确认 PRD
    │
    └─ AI 读取外部文档（Notion / 如流）
       辅助生成 / 美化 PRD
```

### 3.2 状态说明

| 状态 | 说明 | 进入条件 | 退出条件 |
|------|------|---------|---------|
| Preparing | AI 辅助生成/美化 PRD | 用户创建 Story，提供原始输入 | PRD 生成完成 |
| Clarifying | AI 分析需求并提问，人类回答 | PRD 就绪 | 人类确认 PRD 无误 |
| Planning | AI 做概要设计 + Task 拆分 | 需求澄清完成 | 产研确认概要设计和 Task 拆分 |
| Designing | AI 做所有 Task 的详细设计 | Planning 确认通过 | 产研确认详细设计 |
| Coding | AI 按 Task 顺序编码，自动提 PR | 详细设计确认通过 | AI 编码完成，PR 已创建 |
| Verifying | Code Review + 沙盒功能验证 | 所有 PR 已创建 | 产研确认所有 PR 验证通过 |
| Done | Story 完成 | 验证通过 | - |

### 3.3 回退模型（Round）

Verifying 发现问题时，人类选择回退方式：

| 操作 | 触发时机 | 效果 |
|------|---------|------|
| iterate | 小问题，代码层面修改即可 | 回到 Coding，同分支同 PR，AI 带着 Review 意见继续改 |
| restart | 方案有根本问题 | 开新 Round，回到 Designing 或 Coding，新分支新 PR，关闭旧 PR |

每个 Round 记录：
- 轮次编号、类型（initial / iterate / restart）
- 分支名、PR 信息
- AI 消息记录
- 结束原因（restart 时记录，作为下一轮的上下文）

## 4. 阶段定义（Input / Output / Human Gate）

#### Preparing（需求准备）

- 输入：产品提供的原始输入（文档链接、口述、Notion 页面、如流文档等）
- 输出：PRD 或简易 PRD（结构化需求文档）
- AI 角色：产品助理 — 读取外部文档，辅助生成/美化 PRD
- 人类参与：提供原始输入，确认 PRD 内容
- 依赖能力：AI + Doc（读取外部文档）

#### Clarifying（需求澄清）

- 输入：PRD + 项目上下文（tech stack, architecture, rules）
- 输出：确认后的 PRD（scope、边界条件、验收标准完全明确）
- AI 角色：需求分析师 — 基于当前系统实现和技术认知提问
- 人类参与：回答 AI 的澄清问题；AI 复述需求，产研确认 PRD
- 依赖能力：AI + SCM（读代码库，理解当前系统）

#### Planning（概要设计 + Task 拆分）

- 输入：确认后的 PRD + 代码库现状
- 输出：概要设计文档（整体怎么做）+ Task 列表（含依赖 DAG）
- AI 角色：架构师 / Tech Lead — 分析代码库，设计整体方案，拆分 Task
- 人类参与：产研确认概要设计和 Task 拆分
- 依赖能力：AI + SCM（读代码库）

#### Designing（详细设计）

- 输入：确认后的概要设计 + Task 列表 + 代码库现状
- 输出：详细设计文档（一份文档覆盖所有 Task 的实现细节）
- AI 角色：高级开发者 — 细化每个 Task 的实现方案
- 人类参与：产研确认详细设计
- 依赖能力：AI + SCM（读代码库）

#### Coding（AI 编码）

- 输入：确认后的详细设计 + 代码库
- 输出：代码变更 + PR
- AI 角色：开发者 — 按 Task 依赖顺序编码，完成后自动提 PR
- 人类参与：可选的中间检查点（通过 SSE 实时观察编码过程）
- 依赖能力：AI + SCM（分支 / 提交 / 创建 PR）

#### Verifying（验证）

- 输入：PR diff + PRD + 设计文档 + 验收标准
- 输出：验证通过 / 不通过（触发 iterate 或 restart）
- 人类参与：
  - Code Review：人工静态代码审查
  - CI（可选）：按需选择 CI 流程（GitHub Actions / 内部 Agile 平台），跑自动化测试
  - 沙盒测试：在沙盒环境中人工验证功能
  - 产研确认：整体确认代码改动符合预期
- AI 角色：不参与独立判断，验证完全由人类主导
- 依赖能力：SCM（PR Review）+ CI（可选）+ Sandbox

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
| Preparing | ✓ | | | ✓(读) | | |
| Clarifying | ✓ | ✓(读) | | | | |
| Planning | ✓ | ✓(读) | | | | |
| Designing | ✓ | ✓(读) | | | | |
| Coding | ✓ | ✓(写) | | | | |
| Verifying | ✓ | ✓(PR) | ✓(可选) | | ✓ | |
| 全局 | | | | | | ✓ |

### 5.3 核心设计原则

- 阶段定义是稳定的（软件工程方法论不变）
- 能力是抽象的（不绑定具体工具）
- Provider 是可替换的（外网 GitHub 换成内网 iCode，只换 Provider 层）
- 环境是配置化的（同一套系统部署在不同网络环境，只改配置）

## 6. v1 → v2 关键变化总结

| 维度 | v1 | v2 |
|------|----|----|
| 状态机 | 单层 Round 级，阶段定义模糊 | 单层 Story 级，每个阶段严格定义 I/O/Gate |
| 需求准备 | 无 | Preparing 阶段，AI 辅助生成 PRD |
| 需求澄清 | AI 提问质量不稳定 | AI 基于代码库理解提问，需复述需求确认 |
| Planning | 一次性产出方案，一键确认 | 概要设计 + Task 拆分，产研确认 |
| 详细设计 | 无独立阶段 | Designing 阶段，一份文档覆盖所有 Task |
| Task 模型 | 无 | 设计层面的组织单元（非独立状态机） |
| 编码 | 黑盒 | AI 按 Task 依赖顺序编码，SSE 实时可观察 |
| 验证 | Review 和 Testing 分离 | Verifying 合并 Code Review + 沙盒验证 |
| 合并/上线 | 系统内操作 | 暂由人工完成，不纳入 v2 范围 |
| 基础设施 | Provider 抽象（2层） | 能力 → Provider → 环境（3层） |
| 人类门禁 | 部分阶段 | 所有阶段均需产研确认 |
