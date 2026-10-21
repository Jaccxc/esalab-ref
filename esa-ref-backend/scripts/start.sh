#!/usr/bin/env bash
# Starts opencode serve (reads ./opencode.json) and the FastAPI server. Works in Docker or on any Linux box.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.opencode/bin:$HOME/.local/bin:$PATH"
PORT="${PORT:-8000}"
OC_PORT="${OPENCODE_PORT:-4096}"
opencode serve --port "$OC_PORT" --hostname 127.0.0.1 &
for _ in $(seq 1 30); do curl -sf -m 2 "http://127.0.0.1:$OC_PORT/global/health" >/dev/null && break; sleep 1; done
export OPENCODE_URL="${OPENCODE_URL:-http://127.0.0.1:$OC_PORT}"
exec uv run --no-sync uvicorn esalab.app:app --host 0.0.0.0 --port "$PORT"
