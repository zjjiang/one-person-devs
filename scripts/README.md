# 工作历史生成工具

基于 git 提交记录生成统一的工作历史文档。

## 使用方法

### 生成最近 30 天的历史

```bash
uv run python scripts/generate_history.py
```

### 指定日期范围

```bash
uv run python scripts/generate_history.py --start 2026-02-01 --end 2026-03-01
```

### 指定作者

```bash
uv run python scripts/generate_history.py --author "Your Name"
```

### 自定义输出路径

```bash
uv run python scripts/generate_history.py --output my-history.md
```

## 输出格式

生成的 `docs/HISTORY.md` 包含：

- **按日期倒序排列**（最新的在前）
- **每天的统计信息**：提交数、文件变更、代码行数
- **按类型分组**：
  - ✨ 新功能 (feat:)
  - 🐛 问题修复 (fix:)
  - 🔧 其他改进 (chore:, refactor:, perf:, docs:, style:, test:)
  - 📝 其他提交

## 示例

查看 `docs/HISTORY.md` 了解输出格式。

## 自动化建议

### 每周更新一次

```bash
# 添加到 ~/.zshrc 或 ~/.bashrc
alias update-history="cd /path/to/one-person-devs && uv run python scripts/generate_history.py --start 2026-02-01"
```

### 使用 cron 定时任务

```bash
# 每周日晚上更新
0 20 * * 0 cd /path/to/one-person-devs && uv run python scripts/generate_history.py --start 2026-02-01
```
