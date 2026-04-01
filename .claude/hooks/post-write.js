#!/usr/bin/env node

/**
 * Post-tool-use hook for OPD project
 * Automatically runs code formatting after file edits
 */

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

// Get the tool result from stdin
let hookData = "";
process.stdin.on("data", (chunk) => {
  hookData += chunk;
});

process.stdin.on("end", () => {
  try {
    const data = JSON.parse(hookData);

    // Only process successful file writes
    if (data.toolName !== "Write" || !data.successful) {
      process.exit(0);
    }

    const filePath = data.params?.file_path;
    if (!filePath) {
      process.exit(0);
    }

    // Auto-format Python files
    if (filePath.endsWith(".py") && fs.existsSync(filePath)) {
      try {
        console.log(`[hook] Formatting ${path.relative(process.cwd(), filePath)}...`);
        execSync(`uv run ruff format "${filePath}" --quiet`, { stdio: "pipe" });
      } catch (err) {
        // Format errors are non-blocking
        console.warn(`[hook] Format warning:`, err.message);
      }
    }

    // Auto-format TypeScript/React files
    if ((filePath.endsWith(".ts") || filePath.endsWith(".tsx")) && fs.existsSync(filePath)) {
      try {
        console.log(`[hook] Checking ${path.relative(process.cwd(), filePath)}...`);
        // Just do a syntax check, don't auto-format (requires prettier config)
        execSync(`cd web && npx tsc --noEmit "${filePath}" 2>/dev/null || true`, {
          stdio: "pipe",
        });
      } catch (err) {
        // Type check errors are non-blocking
      }
    }

    process.exit(0);
  } catch (err) {
    // Hook errors should not block the user
    console.error("[hook error]", err.message);
    process.exit(0);
  }
});
