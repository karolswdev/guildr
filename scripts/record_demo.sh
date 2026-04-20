#!/usr/bin/env bash
# Record a demo gif of the guildr PWA.
#
# 1. Start uvicorn on a high port pointed at a temp project store.
# 2. Run the Playwright script (scripts/demo.mjs) which writes a webm.
# 3. Convert the webm to a palette-optimised gif via ffmpeg.
# 4. Stop uvicorn.
#
# Output: docs/screenshots/demo.gif
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${PORT:-8765}"
STORE_DIR="$(mktemp -d -t guildr-demo-XXXXXX)"
OUT_DIR="docs/screenshots"
RAW_DIR="$OUT_DIR/_raw"
GIF="${GIF:-$OUT_DIR/demo.gif}"

mkdir -p "$RAW_DIR"
rm -f "$RAW_DIR"/*.webm 2>/dev/null || true

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg required but not found." >&2
  exit 1
fi

# Boot the backend. ORCHESTRATOR_PROJECTS_DIR keeps demo state out of
# whatever directory you usually use.
echo ">> Starting backend on port $PORT (store=$STORE_DIR)"
ORCHESTRATOR_PROJECTS_DIR="$STORE_DIR" \
  .venv/bin/python -m uvicorn web.backend.app:app \
    --host 127.0.0.1 --port "$PORT" --log-level warning &
UVICORN_PID=$!
trap 'kill $UVICORN_PID 2>/dev/null || true; rm -rf "$STORE_DIR"' EXIT

# Wait for /healthz
for i in {1..30}; do
  if curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done
if ! curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null; then
  echo "Backend never came up." >&2
  exit 1
fi
echo ">> Backend healthy"

# Make sure playwright is installed locally
if [[ ! -d scripts/node_modules/playwright ]]; then
  echo ">> Installing playwright locally"
  (cd scripts && npm install --silent --no-fund --no-audit)
fi

# Make sure the frontend bundle is fresh
if [[ ! -f web/frontend/dist/app.js ]] || [[ web/frontend/src/app.ts -nt web/frontend/dist/app.js ]]; then
  echo ">> Rebuilding frontend bundle"
  web/frontend/build.sh
fi

# Run the playwright script
echo ">> Recording with Playwright"
BASE_URL="http://127.0.0.1:$PORT" node scripts/demo.mjs

WEBM=$(ls -1t "$RAW_DIR"/*.webm | head -1)
if [[ -z "$WEBM" ]]; then
  echo "No webm produced." >&2
  exit 1
fi
echo ">> Captured $WEBM ($(wc -c < "$WEBM") bytes)"

# Convert webm → high-quality gif using two-pass palette
PALETTE="$RAW_DIR/palette.png"
ffmpeg -y -i "$WEBM" -vf "fps=15,scale=393:-1:flags=lanczos,palettegen=stats_mode=diff" "$PALETTE" -loglevel warning
ffmpeg -y -i "$WEBM" -i "$PALETTE" -lavfi "fps=15,scale=393:-1:flags=lanczos [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5" "$GIF" -loglevel warning

echo
echo "Wrote $GIF ($(wc -c < "$GIF") bytes)"
