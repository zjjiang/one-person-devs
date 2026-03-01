# 工作历史 (2026-02-01 ~ 2026-03-01)

**总提交数**: 112

---

## 2026-02-28

**提交**: 1 | **文件**: 12 | **+815** / **-180**


### 🔧 其他

- docs: 添加 Git 工作流规则 - push 前需用户确认 (`a8a69d6`)



## 2026-02-24

**提交**: 1 | **文件**: 45 | **+1776** / **-694**


### 🔧 其他

- refactor: ruflow → infoflow（如流） (`c027619`)



## 

**提交**: 110 | **文件**: 18 | **+898** / **-190**


### ✨ 新功能

- **feat: 添加工作日报生成工具** (`27d2d5a`)

- **feat: 在 AI prompt 中添加工作区路径信息** (`a270464`)

  - 修改 build_project_context() 添加 include_work_dir 参数
- 当 include_work_dir=True 时，在 prompt 中包含工作区目录路径
- 所有阶段的 prompt 构建函数都启用工作区路径注入
- 让 AI 明确知道自己在哪个目录工作，提升上下文理解

- **feat: 全局配置导入导出功能** (`0ef0ec9`)

- **feat: AI 消息混合存储 - 阶段 2（集成 + 简化）** (`c7a091d`)

- **feat: AI 消息混合存储 - 阶段 1（基础设施）** (`fda4c84`)

- **feat: 优化需求澄清问题生成策略** (`51acdbd`)

- **feat: 飞书文档附件发送 + CLAUDE.md 污染防护** (`78dcb7f`)

  阶段完成时通过飞书文件上传 API 将生成的文档（PRD、技术方案等）作为附件发送。
增加 CLAUDE.md 读取校验，检测 AI 对话痕迹等异常内容时自动跳过，防止污染 AI prompt。
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **feat: workspace lock 集成 — preflight 检查 + stop 释放锁 + DB 模型** (`311f84a`)

  将 workspace lock 逻辑集成到 story 生命周期中：preflight 端点检查锁状态，
stop 操作自动释放锁，coding 阶段自动获取/释放锁。
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **feat: 通知系统（站内信 + 飞书）+ UI 布局重构** (`e8aa8a3`)

- **feat: 多 Story 并行支持 — 项目级 coding 锁 + workspace 互斥** (`56acbf9`)

- **feat: 全局日志查看页面 + 布局重构（统一顶栏）** (`70b6acd`)

  - 新增日志页面：实时 SSE 流 + 分页历史查看，支持级别过滤/搜索/暂停
- 后端 logs API：SSE stream 端点 + 分页 history 端点
- 布局重构：统一顶栏（Logo + 用户），左侧可收起导航 Sidebar
- 日志测试 13 个用例

- **feat: Story 文档上传/下载** (`e970ccd`)

  - 后端新增 download 端点（Content-Disposition attachment，文件名带 story ID）
- 后端新增 upload 端点（校验 .md 扩展名 + UTF-8 编码，写入磁盘并更新 DB）
- 前端文档 Tab 栏右侧添加下载/上传按钮
- 上传后立即用 file.text() 渲染内容，再同步 getStory 刷新状态

- **feat: 全局能力配置批量验证、健康状态展示** (`e7e728e`)

  新增"验证全部"按钮，并发检测所有已配置能力的连接状态，
表格增加"健康"列显示正常/异常标签，hover 可查看详情。

- **feat: 能力多实例架构、ID-based API、stub providers 框架** (`2b5252f`)

- **feat: merge 后增量更新 CLAUDE.md、项目编辑字段锁定、补充测试** (`c6ca006`)

- **feat: CLAUDE.md 自动生成、编码后自动创建 PR、Merge PR、统一消息组件** (`c5b70bc`)

- **feat: 面包屑导航，Story/Project 页面支持层级返回** (`8770afc`)

  - Story API 响应新增 project_id、project_name 字段
- StoryDetail 页面添加面包屑：首页 > 项目名 > Story标题
- ProjectDetail 页面添加面包屑：首页 > 项目名

- **feat: 编码报告、测试指南、分支管理、输入哈希变更检测、用户注册** (`654199d`)

- **feat: 两阶段交互、阶段回退、文档聊天优化、多轮续写** (`50fb45d`)

- **feat: 工作区初始化、全局能力配置、UI 重构** (`a67a130`)

- **feat: 项目增加 workspace_dir 属性，AI 编码时代码存放到指定目录** (`bae9aa3`)

  Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

- **feat: 完善能力测试连接功能** (`d1a7387`)

- **feat: 支持 ducc AI provider + Claude Code 增加 base_url/auth_token 配置** (`ab848a0`)

- **feat: 前后端分离，React + Vite + Ant Design SPA 替代 Jinja2 模板** (`02d2f95`)

- **feat: add Alembic migrations, tests, config example, and README** (`e8d2c4b`)

- **feat: implement complete v2 codebase** (`8dad203`)

- **feat: add real-time SSE streaming for AI coding/revising and centralize logging** (`c647648`)

- **feat: improve task lifecycle, error visibility, and manual verification** (`03a3ef2`)

- **feat: enhance GitHub integration with auto PR creation and improved config** (`8554ce0`)

- **feat: implement OPD platform with provider abstraction and web UI** (`55d9d3f`)


### 🐛 问题修复

- **fix: 修复 CapabilityRegistry 实例共享问题** (`a46c2d4`)

  问题：
- with_project_overrides() 直接赋值 _external_providers
- 导致多个项目共享同一个 dict 引用
- 理论上可能导致状态泄露
解决方案：
- 深拷贝 _external_providers 字典
- 确保每个项目的 registry 完全独立
- 添加注释说明 _capabilities 浅拷贝的安全性

- **fix: 修复高优先级并发安全问题** (`40fde12`)

- **fix: 修复 ClaudeCodeProvider 的并发安全问题** (`8057c91`)

- **fix: 增强 CLAUDE.md 生成的项目隔离性** (`77a2c0b`)

  - 在 system prompt 中明确说明只关注当前项目
- 在 user prompt 中添加项目名称标识
- 防止 AI 混淆不同项目的上下文
- 避免跨项目的记忆问题

- **fix: 所有 AI 阶段传递 work_dir 参数，修复非编码阶段工作目录错误** (`5819768`)

  非编码阶段（preparing/clarifying/planning/designing）之前未传递 work_dir
给 Claude Code SDK，导致 AI 在 OPD 服务器目录而非项目工作区运行。
现在所有阶段和聊天功能统一通过 resolve_work_dir() 解析并传递 work_dir。


### 🔧 其他

- chore: 隐藏项目详情页的规则和技能标签页 (`446f04c`)

- perf: CLAUDE.md 大文件分块读取，避免内存溢出 (`2816834`)

- refactor: 拆分 _start_ai_stage 过长函数，提取工作区锁管理逻辑 (`2377b0b`)

- perf: 数据库性能优化 - 索引 + active_round_id (`f5ed082`)

- docs: 更新 README.md 和 CLAUDE.md (`8552479`)

- docs: OpenClaw → OPD API 操作指南 (`04fcbd8`)

- test: 文档上传/下载端点测试 + 更新 CLAUDE.md (`0a476ff`)

- refactor: 清理 6 个死列（tasks/pull_requests/skills） (`0584d3e`)

- refactor: 架构重构、清理死代码、产品更名 SoloForge (`5f101a3`)

- refactor: 精简 AI provider 配置，移除 permission_mode 和 api_key (`fcc9dd1`)

- docs: add v2 technical design (`79edc99`)

- docs: update v2 business model and archive v1 docs (`1d1e526`)

- chore: clean codebase for v2 rewrite (`ff0cd99`)

- docs: add v2 business model framework (`8eadb03`)

- docs: update CLAUDE.md with SSE streaming, middleware, and logging sections (`d0299fd`)

- docs: add CLAUDE.md project context (`38e1b31`)

- docs: add project README (`35288f0`)

- docs: add SE practices research, update design with rules/skills/planning (`d96ce42`)

- docs: add detailed design and update research report (`403c4dc`)

- docs: add technical research report (`1fec71e`)


### 📝 其他

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)

- jiangzhijian (``)


