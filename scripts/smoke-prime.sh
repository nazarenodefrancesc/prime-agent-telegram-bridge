#!/usr/bin/env bash
set -euo pipefail
PRIME_AGENT_BIN="${PRIME_AGENT_BIN:-prime-agent}"

if ! command -v "$PRIME_AGENT_BIN" >/dev/null 2>&1; then
  echo "smoke-prime: NOT RUN - $PRIME_AGENT_BIN not found on PATH" >&2
  exit 2
fi

"$PRIME_AGENT_BIN" --help >/dev/null
"$PRIME_AGENT_BIN" model list >/dev/null

echo "smoke-prime: PASS - CLI and model catalog reachable"
