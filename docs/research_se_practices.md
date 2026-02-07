# AI 辅助软件工程最佳实践调研

## 1. 背景

OPD 的核心定位是"工程迭代流程编排平台"，其设计应当契合软件工程的最佳实践。本文档调研当前业界在 AI 辅助开发领域的方法论和最佳实践，验证 OPD 的设计是否合理，并识别需要补充的部分。

---

## 2. Spec-Driven Development（规格驱动开发）

### 2.1 核心理念

2025-2026 年 AI 辅助开发领域最重要的方法论转变：**从 vibe coding 到 spec-driven development**。

> Vibe coding：直接用自然语言对话让 AI 写代码，随意、即兴、缺乏结构。
> Spec-driven：先写清楚规格文档（spec），再让 AI 按照 spec 编码。

**核心观点：Spec 的质量决定了 AI 产出的质量。**

### 2.2 Spec 应包含的内容

根据业界最佳实践，一份好的 AI coding spec 应包含：

| 要素 | 说明 | 重要性 |
|------|------|--------|
| 背景/动机 | 为什么要做这个功能 | 高 |
| 需求描述 | 具体要做什么 | 高 |
| 验收标准 | 怎样算做完了 | 高 |
| 技术约束 | 必须/不能使用的技术 | 高 |
| 接口定义 | 输入输出、API 格式 | 中 |
| 边界条件 | 异常情况如何处理 | 中 |
| 参考资料 | 相关文档、类似实现 | 中 |
| 测试策略 | 需要哪些测试 | 中 |

### 2.3 OPD 的契合度

| 最佳实践 | OPD 设计 | 状态 |
|----------|---------|------|
| 需求文档先行 | Story 以 Markdown 需求文档为输入 | ✅ 契合 |
| Spec 包含验收标准 | Story 模型有 `acceptance_criteria` | ✅ 契合 |
| AI 主动澄清模糊需求 | clarifying 状态 + Q&A 机制 | ✅ 契合 |
| 技术约束作为输入 | Project Rules (forbidden/architecture) | ✅ 契合 |
| 提供 Spec 模板 | 需补充 | ⚠️ 建议增加 |

### 2.4 建议：Story 需求文档模板

OPD 应提供标准的需求文档模板，引导研发人员写出高质量的 spec：

```markdown
# Story: [标题]

## 背景
为什么要做这个功能？解决什么问题？

## 需求描述
具体要做什么？期望的行为是什么？

## 验收标准
- [ ] 条件 1
- [ ] 条件 2
- [ ] 条件 3

## 技术约束
- 必须使用 xxx
- 不能修改 xxx
- 性能要求：xxx

## 测试要求
- 需要哪些单元测试
- 需要哪些集成测试

## 参考
- 相关文档链接
- 类似功能参考
```

---

## 3. Human-in-the-Loop（人在回路）

### 3.1 核心理念

业界共识：**AI 生成的代码必须经过人工审查才能进入生产环境。**

AI 不是替代开发者，而是团队中的一个"初级开发者"——能力强但需要 senior 把关。

### 3.2 关键实践

| 实践 | 说明 |
|------|------|
| Code Review 必须 | AI 代码和人写的代码一样，必须经过 Review |
| Review 反馈闭环 | Review 意见应能驱动 AI 修改，而非人工修改 |
| 人决定合并时机 | AI 不能自动合并到主干 |
| 多轮迭代 | 允许多轮 Review-修改循环 |
| 方案确认 | AI 编码前应先确认实现方案 |

### 3.3 OPD 的契合度

| 最佳实践 | OPD 设计 | 状态 |
|----------|---------|------|
| Code Review 必须 | 核心功能，PR + GitHub Review | ✅ 契合 |
| Review 反馈闭环 | 双通道（PR comments + 人工 prompt） | ✅ 契合 |
| 人决定合并时机 | 手动触发 merge | ✅ 契合 |
| 多轮迭代 | Round 模型（iterate/restart） | ✅ 契合 |
| 方案确认 | 需补充 planning 阶段 | ⚠️ 建议增加 |

### 3.4 建议：增加 Planning 阶段

当前状态机：`clarifying → coding`

建议增加 **planning** 阶段：

```
clarifying → planning → coding → pr_created → ...
```

Planning 阶段：
- AI 输出实现方案（改哪些文件、大致思路、技术选型）
- 研发人员确认方案后再进入编码
- 避免 AI 方向跑偏后浪费大量 token
- 类似 Claude Code 的 plan mode

---

## 4. Git 工作流

### 4.1 主流模型对比

| 模型 | 特点 | 适用场景 |
|------|------|---------|
| GitHub Flow | 简单，feature branch + PR | 持续部署的 Web 应用 |
| GitFlow | 复杂，多分支（develop/release/hotfix） | 有版本发布周期的产品 |
| Trunk-Based | 极简，直接提交到主干 + feature flags | 大型团队、高频部署 |

### 4.2 OPD 采用的模型

OPD 采用 **GitHub Flow** 变体：

```
main (受保护)
  └── opd/story-{id}/r{round}  (AI 创建的 feature branch)
       └── PR → Review → Merge
```

### 4.3 OPD 的契合度

| 最佳实践 | OPD 设计 | 状态 |
|----------|---------|------|
| Feature branch + PR | 每个 Story/Round 一个 branch | ✅ 契合 |
| 小批量频繁合并 | 一个 Story 一个 PR | ✅ 契合 |
| CI 自动化测试 | CIProvider + Skills (auto_before_pr) | ✅ 契合 |
| 主干保护 | 通过 PR 合并，不直接 push | ✅ 契合 |
| Branch 命名规范 | 可通过 Rules (git) 配置 | ✅ 契合 |

---

## 5. 上下文管理（AI 特有挑战）

### 5.1 问题

Vibe coding 最大的痛点：**上下文丢失**。

- 每次对话都是一次性的，AI 不知道项目历史
- 不知道之前做过什么决策、踩过什么坑
- 不了解项目的架构约束和编码规范
- 重复犯同样的错误

### 5.2 业界解决方案

| 方案 | 说明 | 代表 |
|------|------|------|
| CLAUDE.md / .cursorrules | 项目级指令文件 | Claude Code / Cursor |
| Memory 文件 | 持久化的记忆文件 | Windsurf / Cline |
| RAG | 检索增强生成，从知识库中检索相关上下文 | 各类 AI IDE |
| 结构化上下文 | 分层组织上下文（项目/任务/会话） | OPD 的方案 |

### 5.3 OPD 的方案

OPD 采用**三层结构化上下文**：

```
Project 级：技术栈、架构、Rules、历史 Story 摘要
    ↓
Story 级：需求文档、Q&A、相关文档
    ↓
Round 级：上轮失败原因、Review comments、当轮指令
```

### 5.4 OPD 的契合度

| 最佳实践 | OPD 设计 | 状态 |
|----------|---------|------|
| 项目级上下文持久化 | Project 模型（Rules、tech_stack 等） | ✅ 契合 |
| 编码规范作为 AI 输入 | Rules (coding) | ✅ 契合 |
| 历史决策记录 | decisions 字段 | ✅ 契合 |
| 避免上下文丢失 | 三层上下文传递 | ✅ 契合 |
| 智能记忆（自动摘要等） | 二期规划 | 📋 已规划 |

---

## 6. 测试策略

### 6.1 AI 生成代码的测试挑战

- AI 生成的代码可能"看起来对但逻辑有微妙错误"
- AI 倾向于生成 happy path 代码，忽略边界条件
- 测试代码本身也��能有问题

### 6.2 最佳实践

| 实践 | 说明 |
|------|------|
| AI 编码时同时写测试 | 在 spec 中明确测试要求 |
| 已有测试作为护栏 | AI 编码后跑已有测试，确保不破坏现有功能 |
| Review 时重点看测试 | 测试代码比实现代码更需要人工审查 |
| CI 自动跑测试 | PR 创建后自动触发 CI |

### 6.3 OPD 的契合度

| 最佳实践 | OPD 设计 | 状态 |
|----------|---------|------|
| AI 同时写测试 | Rules (testing) 可配置 | ✅ 契合 |
| 已有测试作为护栏 | Skills (run-tests, auto_after_coding) | ✅ 契合 |
| CI 自动跑测试 | CIProvider | ✅ 契合 |
| Spec 中包含测试要求 | 需求文档模板中有"测试要求"部分 | ✅ 契合 |

---

## 7. 总结：OPD 设计的契合度评估

### 7.1 高度契合的部分

- Spec-driven：以需求文档为核心输入
- Human-in-the-loop：完整的 Review 闭环
- Git 工作流：标准的 GitHub Flow
- 上下文管理：三层结构化上下文
- 规则系统：Rules + Skills

### 7.2 建议补充的部分

| 建议 | 优先级 | 说明 |
|------|--------|------|
| **Planning 阶段** | 高 | 在 clarifying 和 coding 之间增加方案确认步骤 |
| **需求文档模板** | 高 | 提供标准模板，引导写出高质量 spec |
| **测试作为 Spec 的一部分** | 中 | 需求文档中明确测试策略 |
| **AI 编码后自动跑测试** | 中 | Skills 的 auto_after_coding 触发 |
| **智能记忆模块** | 低（二期） | 自动摘要、决策提取、规范学习 |

### 7.3 参考资料

- [Spec-Driven Development is the Future of AI-Assisted SE](https://builtin.com/articles/spec-driven-development-ai-assisted-software-engineering)
- [Pro AI Coding Workflow: Spec-Driven & Agentic Development](https://vertu.com/lifestyle/ai-coding-workflow-for-2025-2026-a-guide-to-high-quality-software-engineering/)
- [How to Write a Good Spec for AI Agents](https://addyo.substack.com/p/how-to-write-a-good-spec-for-ai-agents)
- [AI-Assisted Development in 2026: Best Practices](https://binary.ph/2026/02/02/ai-assisted-development-in-2026-best-practices-risks-and-the-evolution-of-engineering/)
- [How to Get Coding Agents to Work Well](https://practicespace.substack.com/p/how-to-get-coding-agents-to-work)
- [Spec-Driven Development at AWS](https://completeaitraining.com/news/beyond-vibe-coding-how-spec-driven-development-at-aws/)
- [AI in the Trenches: Rewriting the Software Process](https://www.infoq.com/articles/ai-developers-rewriting-software-process/)
