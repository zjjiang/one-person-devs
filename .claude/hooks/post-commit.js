#!/usr/bin/env node

/**
 * Claude ​Code post-commit hook
 * Reminds to update CLAUDE.md if critical architecture files changed
 */

const { execSync } = require("child_process");
const path = require("path");

const CRITICAL_PATTERNS = [
  "opd/engine/orchestrator.py",
  "opd/engine/state_machine.py",
  "opd/engine/stages/",
  "opd/providers/",
  "opd/capabilities/registry.py",
  "opd/api/stories.py",
  "opd/api/stories_tasks.py",
  "opd/db/models.py",
  "web/src/pages/StoryDetail.tsx",
  "web/src/components/",
  "opd.yaml",
  "pyproject.toml",
  "package.json",
];

try {
  // Get files from last commit
  const output = execSync("git diff-tree --no-commit-id --name-only -r HEAD", {
    encoding: "utf-8",
  });
  const changedFiles = output.trim().split("\n");

  // Check if any critical files changed
  const hasCriticalChanges = changedFiles.some((file) =>
    CRITICAL_PATTERNS.some((pattern) => file.startsWith(pattern))
  );

  // Check if CLAUDE.md was updated
  const claudeMdUpdated = changedFiles.includes("CLAUDE.md");

  // If critical files changed but not CLAUDE.md, suggest update
  if (hasCriticalChanges && !claudeMdUpdated) {
    console.error(
      "[Claude ​Code Hook] Architecture/configuration files changed"
    );
    console.error(
      "[Claude ​Code Hook] Consider updating CLAUDE.md by running: /init"
    );
  }
} catch (err) {
  // Hook errors should not block commits
}
