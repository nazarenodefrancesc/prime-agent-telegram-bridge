# Agent Instructions

## Mission

Maintain a thin Telegram transport around Prime Agent. Do not reimplement Prime's agent runtime, model routing, recursive subagents, IPython control plane, session semantics, compaction or continual harness.

## Required workflow

1. Read `PRD.md` and the relevant `prd/Txxx-*.md` before editing.
2. Update only the matching `progress/PROGRESS-Txxx.md` while work is active.
3. Use TDD for behavior changes: failing test first, minimal implementation, refactor, full gate.
4. Run `./scripts/repo-check.sh` before marking a task complete.
5. Completion means acceptance criteria **and** required verification pass. `DEFERRED` is never equivalent to `COMPLETE`.
6. Inspect `git status --short` before handoff. Load deeper history only when needed.

## Architectural constraints

- Telegram is a transport, not an agent runtime.
- One Telegram chat maps to one Prime session.
- Prime integration uses the documented JSONL RPC protocol, not terminal scraping.
- Access must fail closed. Never remove the user allowlist requirement without an explicit PRD change.
- Never log or persist Telegram bot tokens or Prime API keys.
- No shell interpolation for Telegram/user-controlled data.
- Local attachment filenames must be sanitized and kept under the bridge-owned inbox.
- Keep Prime-specific assumptions isolated in `prime_rpc.py` and documented in `docs/PRIME-COMPATIBILITY.md`.
