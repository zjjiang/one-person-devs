#!/bin/bash
# Restart OPD frontend & backend
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "==> Stopping existing processes..."
lsof -ti :8765 | xargs kill -9 2>/dev/null || true
lsof -ti :5173 | xargs kill -9 2>/dev/null || true
sleep 1

echo "==> Starting backend (port 8765)..."
nohup uv run opd serve --reload > /tmp/opd-backend.log 2>&1 &
echo "    Backend PID: $!"

echo "==> Starting frontend (port 5173)..."
cd "$PROJECT_DIR/web"
nohup npx vite --host > /tmp/opd-frontend.log 2>&1 &
echo "    Frontend PID: $!"

sleep 3
echo ""
echo "==> Status:"
tail -1 /tmp/opd-backend.log
tail -1 /tmp/opd-frontend.log
echo ""
echo "Frontend: http://localhost:5173/"
echo "Backend:  http://localhost:8765/"
