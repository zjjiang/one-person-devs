# OPD (One Person Devs) 技术调研报告

## 1. 背景与动机

团队中有大量研发人员，但多数不熟悉 AI 编码工具（如 Claude Code）的使用方式。我们希望将 AI 编码能力平台化，让研发人员通过简单的 Web 界面提交需求文档，AI 自动完成编码并融入现有的软件工程迭代流程。

**核心诉求不是造一个 AI coding agent，而是构建一个轻量的、以软件工程迭代流程为核心的编排平台。**

### 1.1 目标流程

```
需求文档(Markdown)
    ↓
AI 澄清提问 ←→ 研发人员异步回答
    ↓
AI 编码 → 创建 branch → 提 PR
    ↓
研发人员在 GitHub 上 Code Review
    ↓
触发 AI 修改（两种方式）：
  a. 读取 GitHub PR comments → AI 根据 review 意见修改
  b. 研发人员在 Web 上写 prompt → AI 根据指令修改
    ↓  (循环直到 Accept)
沙盒验证 (Docker)
    ↓
合并 master → 上线
```

### 1.2 核心原则

- **人在回路 (Human-in-the-loop)**：AI 是团队中的一个开发者，但人来把关
- **异步协作**：研发人员不需要实时等待，提交任务后可以去做其他事
- **流程驱动**：重点是工程迭代流程的编排，而非 AI agent 本身的能力
- **轻量化**：不重复造轮子，直接复用 Claude Code 的编码能力

---

## 2. 竞品分析

### 2.1 OpenHands (原 OpenDevin)

| 维度 | 详情 |
|------|------|
| GitHub | [All-Hands-AI/OpenHands](https://github.com/All-Hands-AI/OpenHands) |
| Stars | 67,500+ |
| 语言 | Python |
| 许可证 | MIT (核心部分) |
| 定位 | AI-Driven Development 平台 |

**产品形态：**

OpenHands 提供四种使用方式：
- **Software Agent SDK**：Python 库，可编程定义和运行 agent
- **CLI**：命令行工具，类似 Claude Code / Codex 的体验
- **Local GUI**：本地 Web 界面 + REST API，类似 Devin / Jules
- **Cloud**：托管云服务，带 Slack/Jira/Linear 集成、多用户、RBAC

**核心能力：**

- 自研 agent 框架（CodeAct Agent），SWE-Bench 得分 77.6%
- Docker 沙盒隔离执行环境
- 支持多种 LLM 后端（Claude、GPT、开源模型等）
- GitHub/GitLab 集成
- 企业版支持 Kubernetes 自托管

**优势：**

- 社区活跃，迭代快，功能全面
- Agent 编码能力经过 SWE-Bench 验证，质量有保障
- 从 CLI 到 Cloud 的完整产品矩阵

**局限性（相对于我们的需求）：**

- **重**：整体架构复杂，自研 agent 框架、沙盒系统、运行时等，部署和维护成本高
- **流程弱**：核心关注点是"AI 怎么写代码"，而非"需求 → 编码 → Review → 验证 → ���线"的完整工程迭代流
- **Review 循环缺失**：没有内置"读取 PR comments → AI 修改 → 更新 PR"的闭环流程
- **定制成本高**：如果要在 OpenHands 上加我们需要的流程编排，需要深入理解其架构，改动量不小

### 2.2 MetaGPT

| 维度 | 详情 |
|------|------|
| GitHub | [geekan/MetaGPT](https://github.com/geekan/MetaGPT) |
| Stars | 64,000+ |
| 语言 | Python |
| 许可证 | MIT |
| 定位 | 多 Agent 协作框架，模拟软件公司 |

**核心理念：**

`Code = SOP(Team)` —— 将标准作业流程（SOP）应用于由 LLM 组成的团队。

**产品形态：**

- **开源框架**：Python 库，CLI 调用 `metagpt "Create a 2048 game"`
- **MGX (MetaGPT X)**：商业化产品 [mgx.dev](https://mgx.dev)，2025 年 Product Hunt 周榜第一

**核心能力：**

- 多 Agent 角色分工：产品经理、架构师、项目经理、工程师、QA
- 一句话需求 → 输出完整项目（用户故事、竞品分析、需求文档、数据结构、API、代码）
- 内置 SOP 流程编排
- Data Interpreter：数据分析能力

**优势���**

- 理念先进，用软件工程方法论指导 AI 协作
- 从需求到代码的全流程自动化
- 学术背景扎实（ICLR 2024 oral）

**局限性（相对于我们的需求）：**

- **面向从零开始的项目**：擅长生成新项目，不擅长在已有大型代码库上做增量开发
- **人参与度低**：设计理念是 AI 自己走完全流程，人只提需求和看结果，缺少 Review 环节
- **多 Agent 开销大**：多个 Agent 之间的通信和协调增加了复杂度和 token 消耗
- **无 Git 工作流集成**：没有内置 branch/PR/Review 的工程流程
- **不适合迭代开发**：更适合一次性生成，不适合"改 → Review → 再改"的循环

### 2.3 其他相关项目

| 项目 | 定位 | 与 OPD 的差异 |
|------|------|---------------|
| [SWE-agent](https://github.com/princeton-nlp/SWE-agent) | 自动解决 GitHub Issue | 偏学术研究，无 Web UI，无 Review 流程 |
| [Sweep AI](https://sweep.dev) | Issue → PR 自动化 | SaaS 产品，不可自托管，流程不可定制 |
| [Devin](https://cognition.ai) | 商业 AI 开发者 | 闭源商业产品，价格高，不可定制 |
| [Goose](https://github.com/block/goose) | 开源 AI coding agent（Block 出品，30k stars） | 本地 CLI agent，类似 Claude Code，无工程流程编排 |
| [OpenCode](https://opencode.ai) | 开源 Claude Code 替代 | 纯 CLI 工具，无流程编排 |
| Claude Code | Anthropic 官方 CLI | 编码能力强，但无任务管理和流程编排 |

> **注**：Goose、OpenCode、Claude Code 都属于 AI coding agent 层，解决的是"AI 怎么写代码"的问题。OPD 是上面一层，解决的是"AI 写的代码怎么融入工程流程"。OPD 可以将这些 agent 作为 AIProvider 的不同实现来调度。

---

## 3. 对比总结

### 3.1 核心维度对比

| 维度 | OpenHands | MetaGPT | OPD (我们要做的) |
|------|-----------|---------|-----------------|
| **核心定位** | AI coding agent 平台 | 多 Agent 模拟软件公司 | 工程迭代流程编排 |
| **AI 编码** | 自研 agent | 多 Agent 协作 | 复用 Claude Code |
| **适用场景** | 通用编码任务 | 从零生成项目 | 已有代码库的迭代开发 |
| **人的角色** | 提需求 + 看结果 | 提需求 + 看结果 | 全程参与（Review/验证/上线） |
| **Git 工作流** | 基础支持 | 无 | 核心功能（branch/PR/Review 循环） |
| **Review 闭环** | 无 | 无 | 核心功能（PR comments + 人工 prompt 双通道） |
| **部署复杂度** | 高 | 中 | 低 |
| **可定制性** | 需深入框架 | 需深入框架 | 流程可配置 |

### 3.2 关键差异

**OpenHands 和 MetaGPT 解决的问题是"AI 怎么写代码"，OPD 解决的问题是"AI 写的代码怎么融入工程流程"。**

这是两个不同层面的问题：

```
┌─────────────────────────────────────────┐
│          OPD 关注的层面                   │
│   需求管理 → 任务编排 → Review → 验证 → 上线  │
└──────────────────┬──────────────────────┘
                   │ 调用
┌──────────────────▼──────────────────────┐
│        Claude Code 关注的层面             │
│   读代码 → 理解上下文 → 写代码 → 跑测试     │
└─────────────────────────────────────────┘
```

OPD 不需要重新实现 AI 编码能力，而是站在 Claude Code 的肩膀上，专注于流程编排。

---

## 4. 为什么要自己做 OPD

### 4.1 现有方案无法满足的核心需求

**1. 完整的工程迭代闭环**

现有工具都停留在"AI 写完代码"这一步。但在真实的软件工程中，写代码只是其中一环：

```
需求澄清 → 编码 → Code Review → 根据反馈修改 → 再 Review → 验证 → 上线
```

没有任何现有开源工具覆盖了这个完整闭环，尤其是 **Review → 修改 → 再 Review** 的循环。

**2. 人在回路的异步协作模式**

- OpenHands/MetaGPT 倾向于让 AI 自主完成所有工作
- 但在企业环境中，代码必须经过人工 Review 才能合并
- 研发人员需要异步参与（提需求、回答问题、Review、验证），而不是实时盯着 AI 写代码

**3. 降低 AI 工具的使用门槛**

- Claude Code 本身很强大，但需要研发人员熟悉 CLI 操作、理解 prompt 工程
- OPD 将这些复杂性封装在 Web 界面背后，研发人员只需要：上传需求文档 → 回答 AI 的问题 → Review 代码 → 验证 → 合并

**4. 与现有 Git 工作流的深度集成**

- 自动创建 feature branch（遵循团队命名规范）
- 自动创建 PR（带有结构化的描述）
- 读取 PR 上的 line comments 作为修改指令
- 支持研发人员在 Web 上直接写 prompt 指导 AI 修改（适合整体性、方向性的调整指令）
- 支持多轮 Review-修改循环（comments 和 prompt 两种触发方式可混合使用）
- 最终由人决定合并时机

### 4.2 为什么不基于 OpenHands 二次开发

| 考量 | 说明 |
|------|------|
| 架构复杂度 | OpenHands 自研了完整的 agent 框架、沙盒系统、运行时，我们不需要这些 |
| AI 编码能力 | OpenHands 自己实现 agent，我们直接用 Claude Code，效果更好且零维护成本 |
| 定制方向不同 | OpenHands 的扩展点在 agent 能力，我们需要的扩展点在工程流程 |
| 维护成本 | 跟随上游更新的成本高，且上游的演进方向未必与我们一致 |

### 4.3 为什么不用 MetaGPT

| 考量 | 说明 |
|------|------|
| 场景不匹配 | MetaGPT 擅长从零生成项目，我们是在已有代码库上迭代 |
| 多 Agent 不必要 | 我们只需要一个 AI 开发者（Claude Code），不需要模拟整个软件公司 |
| 无 Git 集成 | MetaGPT 输出的是本地文件，没有 branch/PR/Review 流程 |
| Token 效率 | 多 Agent 之间的通信消耗大量 token，单 Agent + 人工 Review 更经济 |

### 4.4 OPD 的独特价值

```
OPD = Claude Code (AI 编码能力) + 工程迭代流程编排 + Web 界面
```

- **不造 AI agent 的轮子**：直接调用 Claude Code SDK，编码质量 = Claude Code 的水平
- **专注流程价值**：任务状态机、Review 闭环、异步协作、沙盒验证
- **代码量小**：预计核心代码 < 3000 行，易于维护和定制
- **SCM 抽象**：GitHub 先行，后续可扩展到 icode 等内部平台

---

## 5. 技术方案概要

### 5.1 架构

```
┌─────────────────────────────────────┐
│           Web 界面 (前端)             │
│  任务提交 / 状态查看 / 问答交互 / 触发修改  │
└──────────────┬──────────────────────┘
               │ HTTP API
┌──────────────▼──────────────────────┐
│        编排引擎 (FastAPI)             │
│  ┌──────────┐  ┌──────────────────┐ │
│  │ 任务状态机 │  │ GitHub 集成 (SCM) │ │
│  └──────────┘  └──────────────────┘ │
│  ┌──────────┐  ┌──────────────────┐ │
│  │ 任务持久化 │  │ Docker 沙盒管理   │ │
│  │ (SQLite)  │  │                  │ │
│  └──────────┘  └──────────────────┘ │
└──────────────┬──────────────────────┘
               │ Claude Agent SDK (Python)
┌──────────────▼──────────────────────┐
│          Claude Code                 │
│  读代码 / 写代码 / 执行命令 / 跑测试    │
└─────────────────────────────────────┘
```

### 5.2 任务状态机

```
created → clarifying → coding → reviewing → revising → testing → done
            ↑                      │           │
            └──────────────────────┘           │
                  (AI 有新问题)                  │
                                    ┌──────────┘
                                    ↓
                                reviewing (再次 Review)
```

### 5.3 关键技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 后端框架 | FastAPI | 异步支持好，Python 生态 |
| AI 调用 | Claude Agent SDK (Python) | 官方 Python SDK，直接调用 Claude Code 能力 |
| 数据库 | SQLite | 本地部署，轻量，无需额外服务 |
| 前端 | 待定（Jinja2 模板 或 React） | 先用模板快速出 MVP |
| SCM 集成 | PyGithub + GitPython | GitHub API + 本地 Git 操作 |
| 沙盒 | Docker SDK for Python | 本地 Docker 容器管理 |

### 5.4 Claude Agent SDK 调用方式

OPD 通过官方 [Claude Agent SDK for Python](https://github.com/anthropics/claude-code-sdk-python) 调用 Claude Code：

```python
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    system_prompt="你是一个资深开发者，根据需求文档修改代码...",
    allowed_tools=["Bash", "Read", "Write", "Edit"],
    permission_mode="acceptEdits",
    cwd="/path/to/cloned/repo"
)

async for message in query(prompt=requirement_text, options=options):
    # 处理 AI 的输出、提问、编码进度等
    pass
```

这样 OPD 不需要自己实现任何 agent 逻辑，Claude Code 的所有能力（代码理解、文件操作、命令执行、测试运行）都可以直接使用。

---

## 6. 总结

| 维度 | 结论 |
|------|------|
| 是否有现成方案 | 没有完全匹配的。OpenHands 最接近但太重且缺少流程编排 |
| 是否值得自己做 | 值得。核心代码量不大，且解决的是现有工具都没覆盖的流程问题 |
| 技术风险 | 低。AI 编码能力直接复用 Claude Code，OPD 只做流程编排 |
| 核心差异化 | 工程迭代闭环 + 人在回路 + 异步协作 + 低使用门槛 |
