# T006 — Verification & operations

**Status:** COMPLETE

## Objective
Provide deterministic offline gates plus explicit real-environment smoke checks and service docs.

## Acceptance criteria
- `scripts/repo-check.sh` runs compile/tests/git-whitespace checks and runs Ruff when dev extras are installed.
- `scripts/smoke-prime.sh` verifies a real Prime binary and RPC startup preconditions without modifying source.
- systemd user service example is present.
- Operations, architecture, security and Prime-compatibility docs exist.
- Repository has meaningful git history and release tag.
