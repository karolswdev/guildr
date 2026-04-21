#!/usr/bin/env bash
# Bundle the PWA TypeScript sources into dist/app.js.
#
# Uses esbuild via npx (no package.json or local node_modules needed).
# The backend serves dist/ as a static mount; index.html references
# /dist/app.js, not /src/app.ts.
set -euo pipefail

cd "$(dirname "$0")"

mkdir -p dist

if [ ! -d node_modules/three ]; then
  npm install --no-package-lock --no-save >/dev/null
fi

npx --yes esbuild@0.24.0 \
  src/app.ts \
  --bundle \
  --format=esm \
  --target=es2020 \
  --sourcemap \
  --outfile=dist/app.js \
  --log-level=warning

echo "Built dist/app.js ($(wc -c < dist/app.js) bytes)"
