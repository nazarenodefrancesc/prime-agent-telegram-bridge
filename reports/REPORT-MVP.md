# REPORT — Prime Telegram Bridge v0.1.0 MVP

## TL;DR

The MVP implements a fail-closed Telegram transport over Prime Agent's structured JSONL RPC interface. Offline behavior is covered by unit/contract tests using a fake Prime RPC subprocess; real-environment validation remains a separate smoke gate because credentials and Prime installation are operator-owned.

## Implemented evidence

- Configuration and bootstrap-only authorization behavior: `tests/test_config.py`.
- Atomic 0600 chat/session mapping: `tests/test_state.py`.
- Telegram parsing and long-message chunking: `tests/test_telegram_api.py`.
- Prime RPC startup/prompt/agent_end/final reply contract: `tests/test_prime_rpc.py` + `tests/fake_prime_rpc.py`.
- Offline quality gate: `scripts/repo-check.sh` (compile/tests/git diff; Ruff when available).
- Real Prime environment gate: `scripts/smoke-prime.sh`.

## Known deferred item

T007: a bridge restart recreates the RPC subprocess and therefore the volatile IPython process state, even though the Prime conversation/session JSONL is resumed. A future resident-daemon adapter can remove this limitation without changing the Telegram transport contract.


## Validation snapshot

Validation executed in the delivery environment:

- `python3 -m pytest -q`: **PASS** — 7 tests.
- `python3 -m compileall -q src tests`: **PASS**.
- `git fsck --full --no-dangling`: **PASS**.
- `git status --short`: **PASS** — clean working tree at packaging time.
- Ruff: **NOT RUN** in the delivery environment because the module is not installed there; `repo-check.sh` runs it automatically when dev extras are installed.
- `scripts/smoke-prime.sh`: **NOT RUN** in the delivery environment because the user's local Prime installation/authentication is not mounted here. This is an explicit operator gate, not silently treated as PASS.
