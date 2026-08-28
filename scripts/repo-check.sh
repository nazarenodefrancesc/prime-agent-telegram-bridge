#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)/src"

"$PYTHON_BIN" -m compileall -q src tests
"$PYTHON_BIN" -m pytest -q

if "$PYTHON_BIN" -c 'import ruff' >/dev/null 2>&1; then
  "$PYTHON_BIN" -m ruff check src tests
else
  echo "ruff: NOT RUN (install dev extras to enable lint)"
fi

git diff --check

echo "repo-check: PASS"
