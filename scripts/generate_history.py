#!/usr/bin/env python3
"""Generate work history from git commits."""

import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


def get_git_commits(start_date: str, end_date: str, author: str | None = None) -> dict[str, list[dict]]:
    """Get git commits grouped by date."""
    start = f"{start_date} 00:00:00"
    end = f"{end_date} 23:59:59"

    cmd = [
        "git", "log",
        f"--since={start}",
        f"--until={end}",
        "--no-merges",
        "--pretty=format:%H|||%s|||%b|||%an|||%ar|||%ad",
        "--date=format:%Y-%m-%d",
    ]

    if author:
        cmd.append(f"--author={author}")

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    # Group commits by date
    commits_by_date = {}
    current_commit = None

    for line in result.stdout.split("\n"):
        if "|||" in line:
            # Save previous commit
            if current_commit and current_commit["subject"]:
                date = current_commit["date"]
                if date not in commits_by_date:
                    commits_by_date[date] = []
                commits_by_date[date].append(current_commit)

            # Start new commit
            parts = line.split("|||", 6)
            current_commit = {
                "hash": parts[0][:7],
                "subject": parts[1].strip() if len(parts) > 1 else "",
                "body": parts[2].strip() if len(parts) > 2 else "",
                "author": parts[3].strip() if len(parts) > 3 else "",
                "time": parts[4].strip() if len(parts) > 4 else "",
                "date": parts[5].strip() if len(parts) > 5 else "",
            }
        elif current_commit and line.strip():
            current_commit["body"] += "\n" + line

    # Don't forget the last commit
    if current_commit and current_commit["subject"]:
        date = current_commit["date"]
        if date not in commits_by_date:
            commits_by_date[date] = []
        commits_by_date[date].append(current_commit)

    return commits_by_date


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


def generate_history(start_date: str, end_date: str, author: str | None = None) -> str:
    """Generate markdown history for a date range."""
    commits_by_date = get_git_commits(start_date, end_date, author)

    if not commits_by_date:
        return f"# 工作历史 ({start_date} ~ {end_date})\n\n无提交记录。\n"

    # Sort dates in descending order (newest first)
    sorted_dates = sorted(commits_by_date.keys(), reverse=True)

    lines = []
    lines.append(f"# 工作历史 ({start_date} ~ {end_date})\n")
    lines.append(f"**总提交数**: {sum(len(commits) for commits in commits_by_date.values())}\n")
    lines.append("---\n")

    for date in sorted_dates:
        commits = commits_by_date[date]
        stats = get_git_stats(date)

        lines.append(f"## {date}\n")
        lines.append(f"**提交**: {len(commits)} | **文件**: {stats['files_changed']} | **+{stats['insertions']}** / **-{stats['deletions']}**\n")

        # Group by type
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

        if features:
            lines.append("\n### ✨ 新功能\n")
            for commit in features:
                lines.append(f"- **{commit['subject']}** (`{commit['hash']}`)\n")
                if commit["body"]:
                    body = commit["body"].replace("Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>", "").strip()
                    if body and len(body) < 200:
                        lines.append(f"  {body}\n")

        if fixes:
            lines.append("\n### 🐛 问题修复\n")
            for commit in fixes:
                lines.append(f"- **{commit['subject']}** (`{commit['hash']}`)\n")
                if commit["body"]:
                    body = commit["body"].replace("Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>", "").strip()
                    if body and len(body) < 200:
                        lines.append(f"  {body}\n")

        if chores:
            lines.append("\n### 🔧 其他\n")
            for commit in chores:
                lines.append(f"- {commit['subject']} (`{commit['hash']}`)\n")

        if others:
            lines.append("\n### 📝 其他\n")
            for commit in others:
                lines.append(f"- {commit['subject']} (`{commit['hash']}`)\n")

        lines.append("\n")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate work history from git commits")
    parser.add_argument(
        "--start",
        default=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        help="Start date in YYYY-MM-DD format (default: 30 days ago)",
    )
    parser.add_argument(
        "--end",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--author",
        help="Filter by author name (default: current git user)",
    )
    parser.add_argument(
        "--output",
        default="docs/HISTORY.md",
        help="Output file path (default: docs/HISTORY.md)",
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

    # Generate history
    history = generate_history(args.start, args.end, args.author)

    # Write to file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(history, encoding="utf-8")

    commits_by_date = get_git_commits(args.start, args.end, args.author)
    total_commits = sum(len(commits) for commits in commits_by_date.values())

    print(f"✅ 工作历史已生成: {output_path}")
    print(f"📊 统计: {len(commits_by_date)} 天，{total_commits} 个提交")


if __name__ == "__main__":
    main()
