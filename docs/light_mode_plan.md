# 轻量模式（Light Mode）实现计划

## Context

当前 OPD 的 7 阶段流程（preparing → clarifying → planning → designing → coding → verifying → done）对于 bug 修复、配置变更等小任务过重。新增轻量模式，流程精简为 4 个阶段：

```
preparing → coding → verifying → done
```

- 迭代：verifying → coding（带反馈重新编码）
- 无 restart（没有 designing 阶段可回退）
- UI：Segmented 分段器选择模式

---

## Phase 1: 后端数据模型

### `opd/db/models.py`
- 新增 `StoryMode` 枚举：`full = "full"`, `light = "light"`
- Story 模型新增 `mode` 字段：`mapped_column(Enum(StoryMode), default=StoryMode.full, server_default="full")`

### Alembic 迁移
- `uv run alembic revision --autogenerate -m "add_story_mode_field"`
- 添加 `mode` 列，默认 `"full"`，已有数据自动填充

## Phase 2: 状态机扩展

### `opd/engine/state_machine.py`
- `VALID_TRANSITIONS` 中 `preparing` 增加 `coding` 为合法目标：
  ```python
  StoryStatus.preparing: [StoryStatus.clarifying, StoryStatus.coding],
  ```
- 新增 `MODE_NEXT_STATUS` 字典：
  ```python
  MODE_NEXT_STATUS = {
      "full": {
          "preparing": "clarifying",
          "clarifying": "planning",
          "planning": "designing",
          "designing": "coding",
          "verifying": "done",
      },
      "light": {
          "preparing": "coding",
          "verifying": "done",
      },
  }
  ```
- 新增 `get_next_status(current, mode)` 辅助函数

## Phase 3: API 层改造

### `opd/models/schemas.py`
- `CreateStoryRequest` 新增 `mode: str = "full"`，带 validator 校验 full/light

### `opd/api/stories.py`
- `create_story`：传入 `mode` 到 Story 构造
- `get_story`：返回 `mode` 字段
- `confirm_stage`：用 `get_next_status(status, story.mode)` 替换硬编码 `next_status_map`
- `confirm_stage`：`ai_stages` 改为模式感知（light 下只有 `coding`）
- `chat_message`：light 模式下 `chat_stages` 只有 `("preparing",)`

### `opd/api/stories_actions.py`
- `restart_story`：light 模式下回退到 `preparing` 而非 `designing`
- `rollback_story`：light 模式下 `doc_stages` 只有 `["preparing"]`

## Phase 4: 提示词构建

### `opd/engine/context.py`
- 新增 `build_light_preparing_prompt(story, project)`：
  - 角色：资深开发者（非产品经理）
  - 输出：简洁编码指引（改动目标、涉及文件、具体改动点、验收标准，~500字）
- 新增 `build_light_coding_prompt(story, project, round_)`：
  - 输入：`prd`（编码指引）而非 `detailed_design`
  - 支持 iterate 轮次的 review 意见注入

## Phase 5: 阶段处理器改造

### `opd/engine/stages/preparing.py`
- `execute()` 检查 `ctx.story.mode`：light 用 `build_light_preparing_prompt`，full 保持不变

### `opd/engine/stages/coding.py`
- `validate_preconditions()`：light 要求 `prd` 而非 `detailed_design`
- `execute()`：light 用 `build_light_coding_prompt`

## Phase 6: 输入哈希

### `opd/engine/hashing.py`
- 新增 light 模式的 coding 输入映射：`prd` / `prd.md` → `coding_input_hash` → `coding_report`
- `compute_stage_input_hash` 和 `should_skip_ai` 接受可选 `mode` 参数

### `opd/api/stories_tasks.py`
- 调用 hashing 时传入 `story.mode`

## Phase 7: 前端改造

### `web/src/types.ts`
- Story 接口新增 `mode: "full" | "light"`
- 新增 `LIGHT_STAGE_ORDER = ["preparing", "coding", "verifying", "done"] as const`

### `web/src/components/StageStepper.tsx`
- 接受 `mode` prop，根据模式渲染不同阶段列表

### `web/src/pages/StoryForm.tsx`
- 新增 Ant Design `Segmented` 模式选择器（完整流程 / 轻量模式）
- 选中后显示描述文字
- `createStory` 调用传入 `mode`

### `web/src/api/stories.ts`
- `createStory` 参数新增 `mode`

### `web/src/pages/StoryDetail.tsx`
- 传 `mode` 给 `StageStepper`
- `DOC_CHAT_STAGES`：light 下只有 `["preparing"]`
- `AI_STAGES`：light 下为 `["preparing", "coding"]`
- 回退目标：light 下 verifying 只能回退到 `preparing`
- 迭代/重启：light 下只显示「迭代」按钮（无 restart）
- 标题旁显示模式 Tag（"轻量" / "完整"）

---

## 修改文件清单（16 个文件）

| 文件 | 改动 |
|------|------|
| `opd/db/models.py` | +StoryMode 枚举, +mode 字段 |
| `migrations/versions/xxx.py` | 新迁移 |
| `opd/engine/state_machine.py` | +MODE_NEXT_STATUS, 扩展 VALID_TRANSITIONS |
| `opd/engine/context.py` | +build_light_preparing_prompt, +build_light_coding_prompt |
| `opd/engine/stages/preparing.py` | 模式感知 prompt 选择 |
| `opd/engine/stages/coding.py` | 模式感知前置条件和 prompt |
| `opd/engine/hashing.py` | 模式感知输入映射 |
| `opd/models/schemas.py` | CreateStoryRequest +mode |
| `opd/api/stories.py` | 模式感知 confirm/create/get/chat |
| `opd/api/stories_actions.py` | 模式感知 restart/rollback |
| `opd/api/stories_tasks.py` | 传递 mode 到 hashing |
| `web/src/types.ts` | +mode, +LIGHT_STAGE_ORDER |
| `web/src/components/StageStepper.tsx` | +mode prop |
| `web/src/pages/StoryForm.tsx` | +Segmented 模式选择器 |
| `web/src/pages/StoryDetail.tsx` | 全面模式感知 |
| `web/src/api/stories.ts` | createStory +mode |

## 实施顺序

1. DB 模型 + 迁移（Phase 1）
2. 状态机（Phase 2）
3. 提示词（Phase 4）
4. 阶段处理器（Phase 5）
5. 哈希（Phase 6）
6. Schema + API（Phase 3）
7. 前端（Phase 7）

## 验证

1. 创建 light story → 确认只有 4 个阶段
2. preparing 生成编码指引 → 确认 → 直接进入 coding
3. coding 完成 → 自动 PR → verifying
4. 迭代 → 回到 coding 带反馈
5. 确认 → done
6. 已有 full story 不受影响
