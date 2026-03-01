#!/usr/bin/env python3
"""Generate daily work report from git commits."""

import argparse
import subprocess
from datetime import datetime
from pathlib import Path


def get_git_commits(date: str, author: str | None = None) -> list[dict]:
    """Get git commits for a specific date."""
    start = f"{date} 00:00:00"
    end = f"{date} 23:59:59"

    cmd = [
        "git", "log",
        f"--since={start}",
        f"--until={end}",
        "--no-merges",  # Skip merge commits
        "--pretty=format:%H|||%s|||%b|||%an|||%ar",
    ]

    if author:
        cmd.append(f"--author={author}")

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    commits = []
    current_commit = None

    for line in result.stdout.split("\n"):
        if "|||" in line:
            # Save previous commit if exists
            if current_commit and current_commit["subject"]:
                commits.append(current_commit)

            # Start new commit
            parts = line.split("|||", 4)
            current_commit = {
                "hash": parts[0][:7],  # Short hash
                "subject": parts[1].strip() if len(parts) > 1 else "",
                "body": parts[2].strip() if len(parts) > 2 else "",
                "author": parts[3].strip() if len(parts) > 3 else "",
                "time": parts[4].strip() if len(parts) > 4 else "",
            }
        elif current_commit and line.strip():
            # Continuation of body
            current_commit["body"] += "\n" + line

    # Don't forget the last commit
    if current_commit and current_commit["subject"]:
        commits.append(current_commit)

    return commits


def get_git_stats(date: str) -> dict:
    """Get git statistics for a specific date."""
    start = f"{date} 00:00:00"
    end = f"{date} 23:59:59"

    cmd = [
        "git", "log",
        f"--since={start}",
        f"--until={end}",
        "--numstat",
        "--pretty=format:",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    files_changed = set()
    insertions = 0
    deletions = 0

    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            try:
                insertions += int(parts[0]) if parts[0] != "-" else 0
                deletions += int(parts[1]) if parts[1] != "-" else 0
                files_changed.add(parts[2])
            except ValueError:
                pass

    return {
        "files_changed": len(files_changed),
        "insertions": insertions,
        "deletions": deletions,
    }


def generate_report(date: str, author: str | None = None) -> str:
    """Generate markdown report for a specific date."""
    commits = get_git_commits(date, author)
    stats = get_git_stats(date)

    if not commits:
        return f"# 工作日报 - {date}\n\n今日无提交记录。\n"

    # Group commits by type
    features = []
    fixes = []
    chores = []
    others = []

    for commit in commits:
        subject = commit["subject"]
        if subject.startswith("feat"):
            features.append(commit)
        elif subject.startswith("fix"):
            fixes.append(commit)
        elif subject.startswith(("chore", "refactor", "perf", "docs", "style", "test")):
            chores.append(commit)
        else:
            others.append(commit)

    # Build report
    lines = []
    lines.append(f"# 工作日报 - {date}\n")
    lines.append(f"**提交数**: {len(commits)} | **文件变更**: {stats['files_changed']} | **新增**: +{stats['insertions']} | **删除**: -{stats['deletions']}\n")
    lines.append("---\n")

    if features:
        lines.append("## ✨ 新功能\n")
        for commit in features:
            lines.append(f"### {commit['subject']}\n")
            if commit["body"]:
                # Clean up body
                body = commit["body"].replace("Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>", "").strip()
                if body:
                    lines.append(f"{body}\n")
            lines.append(f"*提交: `{commit['hash']}` - {commit['time']}*\n")

    if fixes:
        lines.append("## 🐛 问题修复\n")
        for commit in fixes:
            lines.append(f"### {commit['subject']}\n")
            if commit["body"]:
                body = commit["body"].replace("Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>", "").strip()
                if body:
                    lines.append(f"{body}\n")
            lines.append(f"*提交: `{commit['hash']}` - {commit['time']}*\n")

    if chores:
        lines.append("## 🔧 其他改进\n")
        for commit in chores:
            lines.append(f"- {commit['subject']} (`{commit['hash']}`)\n")

    if others:
        lines.append("## 📝 其他提交\n")
        for commit in others:
            lines.append(f"- {commit['subject']} (`{commit['hash']}`)\n")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate daily work report from git commits")
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--author",
        help="Filter by author name (default: current git user)",
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: docs/daily-reports/YYYY-MM-DD.md)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing file instead of overwriting",
    )

    args = parser.parse_args()

    # Get current git user if author not specified
    if not args.author:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            check=True,
        )
        args.author = result.stdout.strip()

    # Generate report
    report = generate_report(args.date, args.author)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_dir = Path("docs/daily-reports")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{args.date}.md"

    # Write report
    mode = "a" if args.append else "w"
    output_path.write_text(report, encoding="utf-8")

    print(f"✅ 日报已生成: {output_path}")
    print(f"📊 统计: {len(get_git_commits(args.date, args.author))} 个提交")


if __name__ == "__main__":
    main()
