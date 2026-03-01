# 工作日报生成工具

基于 git 提交记录自动生成每日工作日报。

## 使用方法

### 生成今天的日报

```bash
uv run python scripts/generate_daily_report.py
```

### 生成指定日期的日报

```bash
uv run python scripts/generate_daily_report.py --date 2026-02-28
```

### 指定作者

```bash
uv run python scripts/generate_daily_report.py --author "Your Name"
```

### 自定义输出路径

```bash
uv run python scripts/generate_daily_report.py --output my-report.md
```

### 追加到现有文件

```bash
uv run python scripts/generate_daily_report.py --append
```

## 日报格式

日报会自动按照提交类型分组：

- ✨ **新功能** (feat:)
- 🐛 **问题修复** (fix:)
- 🔧 **其他改进** (chore:, refactor:, perf:, docs:, style:, test:)
- 📝 **其他提交**

每个提交包含：
- 提交标题
- 提交详情（如果有）
- 提交哈希和时间

## 统计信息

日报顶部会显示：
- 提交数量
- 文件变更数量
- 新增行数
- 删除行数

## 自动化建议

### 方案 1：每天下班前手动运行

```bash
# 添加到 ~/.zshrc 或 ~/.bashrc
alias daily-report="cd /path/to/one-person-devs && uv run python scripts/generate_daily_report.py"
```

### 方案 2：使用 cron 定时任务

```bash
# 每天晚上 6 点自动生成
0 18 * * * cd /path/to/one-person-devs && uv run python scripts/generate_daily_report.py
```

### 方案 3：Git Hook（每次提交后更新）

```bash
# .git/hooks/post-commit
#!/bin/bash
cd /path/to/one-person-devs
uv run python scripts/generate_daily_report.py
```

## 输出位置

默认输出到 `docs/daily-reports/YYYY-MM-DD.md`

## 示例

查看 `docs/daily-reports/` 目录下的日报示例。
