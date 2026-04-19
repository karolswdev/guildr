#!/usr/bin/env bash
# Install `guildr` as a global CLI.
#
# Prefers `uv tool install` (fast, isolated). Falls back to `pipx`,
# then to `pip install --user`. After this, `guildr run --config ...`
# works from anywhere on PATH.
#
# Usage:
#   ./install.sh           # install
#   ./install.sh --upgrade # reinstall from current source
set -euo pipefail

cd "$(dirname "$0")"

mode="install"
if [[ "${1:-}" == "--upgrade" ]]; then
  mode="upgrade"
fi

# Build the PWA bundle so `guildr` can serve the web UI out of the box.
if [[ -x web/frontend/build.sh ]]; then
  echo ">> Building PWA bundle"
  web/frontend/build.sh
fi

if command -v uv >/dev/null 2>&1; then
  echo ">> Installing via uv tool"
  if [[ "$mode" == "upgrade" ]]; then
    uv tool install --reinstall --editable .
  else
    uv tool install --editable .
  fi
elif command -v pipx >/dev/null 2>&1; then
  echo ">> Installing via pipx"
  if [[ "$mode" == "upgrade" ]]; then
    pipx install --force --editable .
  else
    pipx install --editable .
  fi
else
  echo ">> uv and pipx not found — falling back to pip --user"
  python3 -m pip install --user --editable .
fi

echo
echo "Installed. Try:"
echo "  guildr --help"
echo "  guildr run --from-env --dry-run --project /tmp/test-project"
