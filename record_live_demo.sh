#!/usr/bin/env bash
# Run the live-LLM demo recording OUTSIDE Claude Code's sandbox.
#
# Why a separate script: Claude Code's bash sandbox blocks Python's LAN
# egress (httpx → "No route to host") while curl works. The orchestrator
# uses the OpenAI SDK over httpx, so live runs from inside the sandbox
# can never reach the llama-server. Run this from a normal terminal.
#
# Output: docs/screenshots/live.gif
#
# Usage (from this directory):
#   ./record_live_demo.sh              # uses ALIEN (192.168.1.70)
#   LLAMA_HOST=192.168.1.13 ./record_live_demo.sh   # PRIMARY
#   WAIT_MS=180000 ./record_live_demo.sh            # longer capture
set -euo pipefail

cd "$(dirname "$0")"

LLAMA_PORT="${LLAMA_PORT:-8080}"
WAIT_MS="${WAIT_MS:-150000}"
PORT="${PORT:-8768}"

# Try PRIMARY first, fall back to ALIEN. Override with HOSTS="a b c".
HOSTS="${HOSTS:-192.168.1.13 192.168.1.70 127.0.0.1}"

LLAMA_URL=""
for h in $HOSTS; do
  url="http://${h}:${LLAMA_PORT}"
  printf ">> Probing %s/health ... " "$url"
  if curl -sf -m 3 "${url}/health" >/dev/null; then
    echo "ok"
    LLAMA_URL="$url"
    break
  fi
  echo "down"
done

if [[ -z "$LLAMA_URL" ]]; then
  echo "!! No llama-server reachable on: $HOSTS" >&2
  exit 1
fi
echo ">> Using $LLAMA_URL"

LLAMA_SERVER_URL="${LLAMA_URL}" \
  DEMO_RUN_WAIT_MS="${WAIT_MS}" \
  GIF="docs/screenshots/live.gif" \
  PORT="${PORT}" \
  bash scripts/record_demo.sh
